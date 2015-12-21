# -*- coding: utf-8 -*-

"""
Configuration settings for the server.
"""

import os

# We assume that MongoDB is set up with no access control, so we don't use a
# username or password.
MONGO_HOST   = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT   = os.environ.get('MONGO_PORT', 27017)
MONGO_DBNAME = os.environ.get('MONGO_DBNAME', 'banyan')

HATEOAS          = False
RESOURCE_METHODS = ['GET', 'POST', 'DELETE']
ITEM_METHODS     = ['GET', 'PATCH', 'DELETE']

# We don't want caching by default, since the server program essentially
# functions as a distributed single-producer, multiple-consumer queue.
# TODO: Support for more than one job queue.

max_name_length = 256
max_job_list_length = 32768
memory_regex = r'^(0|[1-9][0-9]*) (byte|bytes|KiB|MiB|GiB|TiB)'
max_memory_string_length = 32

groups = {
	'item_title': 'group',

	'additional_lookup': {
		'url': 'regex("[\w]+")',
		'field': 'name'
	},

	'schema': {
		'name': {
			'type': 'string',
			'maxlength': max_name_length,
			'required': True,
			'unique': True
		},
		'pending_jobs': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'jobs'}
			}
		},
		'dependents': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'jobs'}
			}
		}
	}
}

jobs = {
	'item_title': 'job',

	'schema': {
		# Note: MongoDB already provides us with an object ID and record
		# creation datetime, so we don't need to specify these
		# explicitly.

		# This information must be provided by the server.
		'command': {
			'type': 'string',
			'maxlength': 32768,
			'required': True
		},
		'retry_on_failure': {
			'type': 'boolean',
			'default': False
		},
		'groups': {
			'type': 'list',
			'maxlength': 8,
			'default': [],
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'groups'}
			}
		},
		# This counter is initialized to the number of dependencies of
		# the job. Each time a parent job terminates successfully, it
		# decrements the counter.
		'pending_dependency_count': {
			'type': 'integer',
			'default': 0
		},
		'dependents': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'jobs'}
			}
		},
		'requested_resources': {
			'type': 'dict',
			'required': True,
			'schema': {
				'memory': {
					'type': 'string',
					'regex': memory_regex,
					'maxlength': max_memory_string_length,
					'required': True
				},
				'cores': {
					'type': 'integer',
					'min': 1,
					'default': 1
				},
				'gpus': {
					'type': 'list',
					'schema': {
						'type': 'dict',
						'schema': {
							'memory': {
								'type': 'string',
								'regex': memory_regex,
								'maxlength': max_memory_string_length,
								'required': True
							},
							'min_compute_capability': {
								'type': 'string',
								'regex': r'\d\.\d',
								'minlength': 3,
								'maxlength': 3,
								'required': True
							}
						}
					}
				}
			}
		},

		# This information is provided by the worker.
		'status': {
			'type': 'string',
			'allowed': [
				# Waiting for dependencies to finish.
				'not ready',
				# Waiting to be claimed by server.
				'not started',
				# Currently running on server.
				'running',
				# Finished executing (either successfully or
				# unsuccessfully).
				'terminated',
				# One of the dependencies terminated
				# unsuccesfully and will not be restarted, so
				# this job cannot run.
				'invalidated'
				# There is no separate status for cancelled
				# jobs. It is the responsibility of the server
				# to remove a cancelled job the lists in which
				# it is mentioned, and to recursively invalidate
				# other jobs that depend on it.
			]
		},
		'return_code': {
			'type': 'integer',
			'dependencies': {'status': 'terminated'}
		},

		# Contains statistics about the process.
		'execution': {
			'type': 'dict',
			'schema': {
				'worker': {
					'type': 'string',
					'maxlength': max_name_length
				},
				'time_started': {
					'type': 'datetime',
					'dependencies': {'status': ['running', 'terminated']},
					'required': True
				},
				'time_terminated': {
					'type': 'datetime',
					'dependencies': {'status': 'terminated'},
					'required': True
				},
				'invalidator': {
					'type': 'dict',
					'dependencies': {'status': 'invalidated'},
					'required': True,
					'schema': {
						# The cancelled dependency could
						# be a group or another job. To
						# allow for both possibilities,
						# we need a variant type.
						'resource': {
							'type': 'string',
							'allowed': ['group', 'job'],
							'required': True
						},
						'id': {
							'type': 'objectid',
							'required': True
						}
					}
				},
				'memory_usage': {
					'type': 'list',
					'dependencies': {'status': ['running', 'terminated']},
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'usage_bytes': {
								'type': 'integer',
								'required': True
							}
						}
					}
				},
				'cpu_utilization': {
					'type': 'list',
					'dependencies': {'status': ['running', 'terminated']},
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'core': {
								'type': 'integer',
								'required': True
							},
							'utilization_ratio': {
								'type': 'float',
								'required': True
							}
						}
					}
				},
				'gpu_usage': {
					'type': 'list',
					'dependencies': {'status': ['running', 'terminated']},
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'gpu': {
								'type': 'integer',
								'required': True
							},
							'usage_bytes': {
								'type': 'integer',
								'required': True
							},
							'utilization_ratio': {
								'type': 'float',
								'required': True
							}
						}
					}
				}
			}
		}
	}
}

DOMAIN = {'groups': groups, 'jobs': jobs}
