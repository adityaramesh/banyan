# -*- coding: utf-8 -*-

"""
banyan.server.settings
----------------------

Configuration settings for Eve.
"""

import os
from schema import tasks, memory_usage, cpu_usage, gpu_usage

# XXX: remove after testing.
DEBUG = True

"""
We assume that MongoDB is set up with no access control, so we don't need to
use any credentials.
"""
MONGO_HOST   = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT   = os.environ.get('MONGO_PORT', 27017)
MONGO_DBNAME = os.environ.get('MONGO_DBNAME', 'banyan')

# Disable etag concurrency control.
IF_MATCH = False
HATEOAS  = False

DOMAIN = {
	'tasks': tasks,
	'memory_usage': memory_usage,
	'cpu_usage': cpu_usage,
	'gpu_usage': gpu_usage
}
