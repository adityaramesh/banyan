# -*- coding: utf-8 -*-

"""
banyan.server.settings
----------------------

Configuration settings for Eve.
"""

import os
from banyan.server.schema import tasks, execution_info, registered_workers
from config.settings import mongo_port, max_task_set_size

# XXX: remove after testing.
DEBUG = True

"""
We assume that MongoDB is set up with no access control, so we don't need to
use any credentials.
"""
MONGO_HOST         = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT         = os.environ.get('MONGO_PORT', mongo_port)
MONGO_DBNAME       = os.environ.get('MONGO_DBNAME', 'banyan')
PAGINATION_LIMIT   = max_task_set_size
PAGINATION_DEFAULT = max_task_set_size

# Disable etag concurrency control.
IF_MATCH = False
HATEOAS  = False

DOMAIN = {
	'tasks': tasks,
	'execution_info': execution_info,
	'registered_workers': registered_workers
}
