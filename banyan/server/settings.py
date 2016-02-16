# -*- coding: utf-8 -*-

"""
banyan.server.settings
----------------------

Configuration settings for Eve.
"""

import os
from banyan.settings import max_task_set_size
from banyan.server.schema import tasks, execution_info, resource_usage

# XXX: remove after testing.
DEBUG = True

"""
We assume that MongoDB is set up with no access control, so we don't need to
use any credentials.
"""
MONGO_HOST         = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT         = os.environ.get('MONGO_PORT', 27017)
MONGO_DBNAME       = os.environ.get('MONGO_DBNAME', 'banyan')

# Disable etag concurrency control.
IF_MATCH = False
HATEOAS  = False

DOMAIN = {
	'tasks': tasks,
	'execution_info': execution_info,
	'resource_usage': resource_usage
}
