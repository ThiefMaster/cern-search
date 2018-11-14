#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Custom UPDATE REST API for CERN Search to support _update_by_query.
Limitation: The query fails when the _version value (version_id in invenio-records) is 0 (<1).
"""

from __future__ import absolute_import, print_function

import logging
from copy import deepcopy
from functools import partial

from elasticsearch_dsl.query import QueryString
from flask_sqlalchemy import SQLAlchemy
from invenio_db import db
from invenio_records_rest import current_records_rest
from sqlalchemy import MetaData, util
from invenio_records_rest.errors import UnsupportedMediaRESTError, InvalidDataRESTError
from invenio_records_rest.utils import obj_or_import_string
from invenio_records_rest.views import create_error_handlers as records_rest_error_handlers
from flask import Blueprint, Response, json, url_for, request, make_response, current_app
from invenio_records_rest.views import need_record_permission, pass_record
from invenio_rest import ContentNegotiatedMethodView
from invenio_search import current_search_client

from cern_search_rest_api.modules.cernsearch.search import RecordCERNSearch
from cern_search_rest_api.modules.cernsearch.utils import get_index_from_request


def create_error_handlers(blueprint):
    """Create error handlers on blueprint."""
    records_rest_error_handlers(blueprint)


def build_url_action_for_pid(pid, action):
    """."""
    return url_for(
        'cernsearch_ubq.{0}'.format(pid.pid_type),
        pid_value=pid.pid_value,
        action=action,
        _external=True
    )


def build_blueprint(app):
    """."""
    blueprint = Blueprint(
        'ubq',
        __name__,
        url_prefix='',
    )

    create_error_handlers(blueprint)

    endpoints = app.config.get('RECORDS_REST_ENDPOINTS', [])
    pid_type = 'docid'
    endpoint = 'ubq'
    options = endpoints.get(pid_type, {})
    if options:
        options = deepcopy(options)
        # Note that the '/api/' part is added transparently since this is an api_blueprint
        options['list_route'] = '/{endpoint}/bulk/'.format(endpoint=endpoint)
        options['item_route'] = '/{endpoint}/<pid(recid):pid_value>'.format(endpoint=endpoint)

        update_permission_factory = obj_or_import_string(
            options['update_permission_factory_imp']
        )

        search_class = obj_or_import_string(
            options['search_class'], default=RecordCERNSearch
        )

        search_class_kwargs = {}
        if options.get('search_index'):
            search_class_kwargs['index'] = options['search_index']

        if options.get('search_type'):
            search_class_kwargs['doc_type'] = options['search_type']

        if search_class_kwargs:
            search_class = partial(search_class, **search_class_kwargs)

        links_factory = obj_or_import_string(
            options['links_factory_imp']
        )

        record_loaders = None
        if options.get('record_loaders'):
            record_loaders = {mime: obj_or_import_string(func)
                              for mime, func in options['record_loaders'].items()}

        record_serializers = None
        if options.get('record_serializers'):
            record_serializers = {mime: obj_or_import_string(func)
                                  for mime, func in options['record_serializers'].items()}

        # UBQRecord
        ubq_view = UBQRecordResource.as_view(
            UBQRecordResource.view_name.format(pid_type),
            update_permission_factory=update_permission_factory,
            default_media_type=options['default_media_type'],
            search_class=search_class,
            loaders=record_loaders,
            links_factory=links_factory,
            record_serializers=record_serializers
        )


        blueprint.add_url_rule(
            options['item_route'],
            view_func=ubq_view,
            methods=['PUT'],
        )

    return blueprint


class UBQRecordResource(ContentNegotiatedMethodView):
    """Resource for _update_by_query items."""

    view_name = '{0}_item'

    def __init__(self,
                 update_permission_factory=None,
                 default_media_type=None,
                 search_class=None,
                 record_loaders=None,
                 links_factory=None,
                 record_serializers=None,
                 **kwargs):
        """Constructor.
        :param resolver: Persistent identifier resolver instance.
        """
        super(UBQRecordResource, self).__init__(
            method_serializers={
                'PUT': record_serializers,
            },
            default_method_media_type={
                'PUT': default_media_type
            },
            default_media_type=default_media_type,
            )
        self.update_permission_factory = update_permission_factory
        self.search_class = search_class
        self.loaders = record_loaders or current_records_rest.loaders
        self.links_factory = links_factory

    @pass_record
    @need_record_permission('update_permission_factory')
    def put(self, pid, record):
        """Custom UPDATE REST API endpoint."""
        if request.mimetype not in self.loaders:
            raise UnsupportedMediaRESTError(request.mimetype)

        data = self.loaders[request.mimetype]()
        if data is None:
            raise InvalidDataRESTError()

        # Make query with record 'control_number'
        self.check_etag(str(record.revision_id))

        # Perform ES API _updated_by_query
        control_num_query = 'control_number:"{recid}"'.format(recid=record['control_number'])
        script = data["ubq"]
        index, doc = get_index_from_request(data)

        es_response = current_search_client.update_by_query(
            index=index,
            q=control_num_query,
            doc_type=doc,
            body=script)

        # Check that the query has only updated one record
        print(es_response['updated'])
        print(es_response['total'])
        if es_response['updated'] == 1 and es_response['updated'] == es_response['total']:
            # Get record from ES
            search_obj = self.search_class()
            search = search_obj.get_record(str(record.id))
            # Execute search
            search_result = search.execute().to_dict()

            if search_result["hits"]["total"] == 1:
                # Update record in DB
                record.clear()
                record.update(search_result["hits"]["hits"][0]["_source"])
                record.commit()
                db.session.commit()
                # Close DB session

                # Return success
                return self.make_response(
                    pid, record, links_factory=self.links_factory)


        # If more than one record was updated return error and the querystring
        # so the user can handle the issue
        return make_response((
            json.dumps({
                'message': 'Something went wrong, the provided script might have caused inconsistency.'
                           'More than one value was updated or the amount of updated values do not '
                           'match the total modified',
                'elasticsearch_response': es_response
            }),
            503)
        )


"""
This endpoint might lead to inconsistencies between DB and ES, use at your own risk.
Prefered options are to handle relationships at application level or perform DELETE-POST operations.
The list operation over _update_by_query might have an impact on performance since it is a heavy operation.
"""


class UBQRecordListResource(ContentNegotiatedMethodView):
    """Resource for _update_by_query items."""

    view_name = '{0}_list_item'

    def __init__(self, update_permission_factory=None, default_media_type=None,
                 search_class=None, **kwargs):
        """Constructor.
        :param resolver: Persistent identifier resolver instance.
        """
        super(UBQRecordListResource, self).__init__(
            default_method_media_type={
                'PUT': default_media_type
            },
            default_media_type=default_media_type,
            **kwargs)

        # TODO: check ownership?
        self.update_permission_factory = update_permission_factory

    @need_record_permission('update_permission_factory')
    def put(self):
        """Custom UPDATE REST API endpoint."""
        # Make query to get all records

        # Get DB session

        # Perform ES API _updated_by_query

        # Check that the query updated the same amount of records than the ones in the query
        # (or less, if update is not needed)

        # If more than the specified amount of records was updated return error and the query string
        # so the user can handle the issue

        # Get records from ES

        # Update records in DB

        # Close DB session

        # Return success
        return Response(
            json.dumps({'status': 200}),
            mimetype='application/json',
        )


def build_health_blueprint():

    blueprint = Blueprint('health_check', __name__)

    @blueprint.route('/health/uwsgi')
    def uwsgi():
        """Load balancer ping view."""
        return 'OK'

    @blueprint.route('/health/elasticsearch')
    def elasticsearch():
        """Load balancer ping view."""
        if current_search_client.ping():
            return 'OK'
        else:
            current_app.logger.error('Health Check: Elasticsearch connection is not available')
            return make_response((
                json.dumps({
                    'Elasticsearch is unavailable'
                }),
                503)
            )

    @blueprint.route('/health/database')
    def database():
        """Load balancer ping view."""
        if db.engine.execute('SELECT 1;').scalar() == 1:
            return 'OK'
        else:
            current_app.logger.error('Health Check: Database connection is not available')
            return make_response((
                json.dumps({
                    'Database connection is unavailable'
                }),
                503)
            )

    # Allow HTTP connections
    uwsgi.talisman_view_options = {'force_https': False}
    elasticsearch.talisman_view_options = {'force_https': False}
    database.talisman_view_options = {'force_https': False}

    return blueprint
