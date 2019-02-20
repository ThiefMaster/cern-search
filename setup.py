#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) 2018, CERN
# This software is distributed under the terms of the GNU General Public
# Licence version 3 (GPL Version 3), copied verbatim in the file "COPYING".
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as Intergovernmental Organization
# or submit itself to any jurisdiction.


import os

from setuptools import find_packages, setup

readme = open('README.md').read()
history = open('CHANGES.md').read()


# Get the version string. Cannot be done with import!
g = {}
with open(os.path.join("cern_search_rest_api", "version.py"), "rt") as fp:
    exec(fp.read(), g)
    version = g["__version__"]

setup(
    name='cern-search-rest-api',
    version=version,
    description='CERN Search as a Service',
    long_description=readme + '\n\n' + history,
    license='GPLv3',
    author='CERN',
    author_email='cernsearch.support@cern.ch',
    url='http://search.cern.ch/',
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    entry_points={
        'invenio_config.module': [
            'cern_search_rest_api = cern_search_rest_api.config'
        ],
        'invenio_search.mappings': [
            'cernsearch-test = cern_search_rest_api.modules.cernsearch.mappings.test',
            'cernsearch-indico = cern_search_rest_api.modules.cernsearch.mappings.indico',
            'cernsearch-webservices = cern_search_rest_api.modules.cernsearch.mappings.webservices',
            'cernsearch-edms = cern_search_rest_api.modules.cernsearch.mappings.edms'
        ],
        'invenio_jsonschemas.schemas': [
            'cernsearch-test = cern_search_rest_api.modules.cernsearch.jsonschemas.test',
            'cernsearch-indico = cern_search_rest_api.modules.cernsearch.jsonschemas.indico',
            'cernsearch-webservices = cern_search_rest_api.modules.cernsearch.jsonschemas.webservices',
            'cernsearch-edms = cern_search_rest_api.modules.cernsearch.jsonschemas.edms'
        ],
        'invenio_base.apps': [
            'cern-search = cern_search_rest_api.modules.cernsearch.ext:CERNSearch'
        ],
        'invenio_base.api_apps': [
            'cern-search = cern_search_rest_api.modules.cernsearch.ext:CERNSearch'
        ],
        'invenio_base.blueprints': [
            'health_check = cern_search_rest_api.modules.cernsearch.views:build_health_blueprint'
        ]
    },
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Development Status :: 1 - Pre-Alpha',
    ],
)
