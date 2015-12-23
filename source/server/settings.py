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

time_regex = r'[1-9][0-9]*(.[0-9]*)? (second|minute|hour)s?'
max_time_string_length = 32

# Dependents can either be jobs or groups. To allow for both possibilities, we
# define a variant type that is used in the schemas for both objects.
job_or_group = {
	'type': 'dict',
	'schema': {
		'resource': {
			'type': 'string',
			'allowed': ['job', 'group'],
			'required': True
		},
		'id': {
			'type': 'objectid',
			'required': True
		}
	}
}

groups = {
	'item_title': 'group',

	'additional_lookup': {
		'url': 'regex("[\w]+")',
		'field': 'name'
	},

	'schema': {
		# Set by the user.

		'name': {
			'type': 'string',
			'maxlength': max_name_length,
			'required': True,
			'unique': True
		},
		'dependents': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': job_or_group
		},

		# Maintained by the server.

		'members': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': job_or_group
		},
		'pending_members': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': job_or_group
		}
	}
}

jobs = {
	'item_title': 'job',

	'schema': {
		# Note: MongoDB already provides us with an object ID and record
		# creation datetime, so we don't need to specify these
		# explicitly.

		#
		# This information is provided by the client.
		#

		'command': {
			'type': 'string',
			'maxlength': 32768,
			'required': True
		},
		'state': {
			'type': 'string',
			'default': 'inactive',
			'allowed': [
				# Not available to be claimed yet. If this job
				# has dependencies, then the last dependency to
				# finish will set the state of this job to
				# `available` after it successfully terminates.
				'inactive',
				# Waiting to be claimed by a worker.
				'available',
				# Currently running on a worker.
				'running',
				# Finished executing (either successfully or
				# unsuccessfully).
				'terminated',
				# Either cancelled by the user, or one of the
				# dependencies was cancelled or terminated
				# unsuccessfully, making this job ineligible
				# for execution.
				'cancelled',
				# The server puts a job in this state when it
				# is cancelled while a worker is currently
				# executing it. The status will be changed once
				# the worker responds with an update to the job
				# state.
				'unknown'
			]
		},
		# The number of times we will put a job back on the queue if we
		# find that it terminates with a status code indicating failure.
		'max_retries': {
			'type': 'integer',
			'min': 0,
			'default': 0
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
		'dependents': {
			'type': 'list',
			'maxlength': max_job_list_length,
			'default': [],
			'schema': job_or_group
		},
		'requested_resources': {
			'type': 'dict',
			'required': True,
			'schema': {
				# The purpose of this field is to be able to
				# provide the user with time estimates for
				# the completion of jobs and groups. It is not
				# required, and we don't enforce that the job
				# terminates within the requested amount of
				# time.
				'time': {
					'type': 'string',
                                        'regex': time_regex,
					'maxlength': max_time_string_length
				},
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
				},
				'max_termination_time': {
					'type': 'string',
                                        'regex': time_regex,
					'maxlength': max_time_string_length,
					# Be generous with the default
					# cancellation time, in case we are
					# saving a large model to a slow disk.
					'default': '10 minutes'
				}
			}
		},

		#
		# This information is managed by the server.
		#

		# In order to create a job with dependencies, the following
		# steps must be followed in the given order (to avoid race
		# conditions):
		# - Create the child job (in the default `inactive` states).
		# - Create the parent jobs (in the default `inactive` states),
		# using the ID of the child job to specify the dependency.
		# - Set the states of the the parent jobs to `available`.
		#
		# In the case where there is only one parent job, the parent
		# job can be created in the `available` state directly. Note
		# that it is the responsibility of each parent to increment
		# this counter.
		'pending_dependency_count': {
			'type': 'integer',
			'min': 0,
			'default': 0
		},

		#
		# This information is managed by the worker.
		#

		'worker': {
			'type': 'string',
			'maxlength': max_name_length
		},
		'exit_status': {
			'type': 'integer',
			'dependencies': {'state': ['terminated', 'cancelled']}
		},
		'time_terminated': {
			'type': 'datetime',
			'dependencies': {'state': ['terminated', 'cancelled']},
		},
		'time_started': {
			'type': 'datetime',
			'dependencies': {'state': ['running', 'terminated', 'cancelled']},
		},
		# The identity of the failed or cancelled dependency that
		# invalidated this job.
		'invalidator': {
			'type': 'dict',
			'dependencies': {'state': 'cancelled'},
			'schema': {
				'resource': {
					'type': 'string',
					'allowed': ['job', 'group'],
					'required': True
				},
				'id': {
					'type': 'objectid',
					'required': True
				}
			}
		},

		# Contains execution metrics about the process.
		'metrics': {
			'type': 'dict',
			'dependencies': {'state': ['running', 'terminated', 'cancelled']},
			'schema': {
				'memory_usage': {
					'type': 'list',
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'usage_bytes': {
								'type': 'integer',
								'min': 0,
								'required': True
							}
						}
					}
				},
				'cpu_utilization': {
					'type': 'list',
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'core': {
								'type': 'integer',
								'min': 0,
								'required': True
							},
							'utilization_ratio': {
								'type': 'float',
								'min': 0,
								'max': 1,
								'required': True
							}
						}
					}
				},
				'gpu_usage': {
					'type': 'list',
					'schema': {
						'type': 'dict',
						'schema': {
							'time': {
								'type': 'datetime',
								'required': True
							},
							'gpu': {
								'type': 'integer',
								'min': 0,
								'required': True
							},
							'usage_bytes': {
								'type': 'integer',
								'min': 0,
								'required': True
							},
							'utilization_ratio': {
								'type': 'float',
								'min': 0,
								'max': 1,
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
