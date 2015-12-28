# -*- coding: utf-8 -*-

"""
Configuration settings for the server.
"""

import os

"""
We assume that MongoDB is set up with no access control, so we don't need to
use any credentials.
"""
MONGO_HOST   = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT   = os.environ.get('MONGO_PORT', 27017)
MONGO_DBNAME = os.environ.get('MONGO_DBNAME', 'banyan')

# Disable concurrency control (using etags).
IF_MATCH         = False
HATEOAS          = False
RESOURCE_METHODS = ['GET', 'POST', 'DELETE']
ITEM_METHODS     = ['GET', 'PATCH', 'DELETE']

"""
We don't enable caching by default, since information about tasks is likely to
become out-of-date quickly.
"""

max_task_list_length = 32768
max_name_string_length = 256
max_command_string_length = 32768

memory_regex = r'^(0|[1-9][0-9]*) (byte|bytes|KiB|MiB|GiB|TiB)'
max_memory_string_length = 32

time_regex = r'[1-9][0-9]*(.[0-9]*)? (second|minute|hour)s?'
max_time_string_length = 32

"""
Used by the user to indicate the resources that are expected to be consumed by
a task over the course of its execution.
"""
resource_info = {
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


"""
Stores all information associated with a worker's attempt to complete a task.
"""
execution_info = {
	'type': 'dict',

	'schema': {
		'worker': {
			'type': 'string',
			'maxlength': max_name_length
		},
		'exit_status': {'type': 'integer'},
		'time_started': {'type': 'datetime'},
		'time_terminated': {'type': 'datetime'},

		'memory_usage': {
			'type': 'list',
			'schema': {
				'type': 'dict',
				'schema': {
					'time': {
						'type': 'datetime',
						'required': True
					},
					'resident_memory_bytes': {
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
					'resident_memory_bytes': {
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

tasks = {
	'item_title': 'task',

	'schema': {
		"""
		Information provided by the client.
		"""

		'command': {
			'type': 'string',
			'maxlength': max_command_string_length,
			'empty': False
		},

		'name': {
			'type': 'string',
			'maxlength': max_name_string_length,
			'empty': False,
			'unique': True
		},

		"""
		If a task has no parents, the user can optionally create it in
		the `available` state directly.
		"""
		'state': {
			'type': 'string',
			'default': 'inactive',
			'allowed': [
				"""
				Not available to be claimed yet. If this task
				has dependencies, then the last dependency to
				finish will set the state of this task to
				`available` after it successfully terminates.
				"""
				'inactive',

				"""
				Waiting to be claimed by a worker.
				"""
				'available',

				"""
				Currently being run by a worker.
				"""
				'running',

				"""
				The server puts a task in this state when it is
				cancelled while in the `running` state. The
				state will be changed to `cancelled` or
				`terminated` once the worker delivers an update.
				"""
				'pending_cancellation',

				"""
				Either cancelled directly by the user or
				invalidated as a result of one of the parent
				tasks being cancelled or terminating
				unsuccessfully.
				"""
				'cancelled',

				"""
				Finished executing (either successfully or
				unsuccessfully).
				"""
				'terminated'
			]
		},

		'continuations': {
			'type': 'list',
			'maxlength': max_task_list_length,
			'default': [],
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'tasks'}
			}
		},

		"""
		This field is not required, and we don't enforce that the task
		terminates within the amount of time given below. Its purpose
		is to allow the user to compute time estimates for task chains.
		"""
		'estimated_runtime': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,

			"""
			If this task is being used as a task group (i.e. it has
			one or more continuations but no command), then it
			makes no sense for the user to provide a value for this
			field.
			"""
			'dependencies': ['command']
		},

		'requested_resources': {
			'type': 'dict',
			'required': True,
			'dependencies': ['command'],
			'schema': resource_info
		},

		"""
		The amount of time a worker will wait for a task to terminate
		after sending it SIGTERM before resorting to using SIGKILL.
		"""
		'max_termination_time': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,
			'dependencies': ['command'],

			"""
			We are generous with the default cancellation time, in
			case the woker must write a large amount of information
			to a slow disk.
			"""
			'default': '10 minutes'
		},

		"""
		The number of times we will put a task back on the queue if we
		find that it terminates unsuccessfully.
		"""
		'max_retry_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'dependencies': ['command']
		},

		"""
		Information managed by the server.
		"""

		"""
		The number of times this task has been rerun after terminating
		unsuccessfully. Once this counter reaches `max_retry_count`,
		this task will no longer be rerun.
		"""
		'retry_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		"""
		If this counter is greater than zero, then the state of the
		task should be `inactive`. Once the count reaches zero, the
		state of the task should be changed to `available`.
		"""
		'pending_dependency_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		"""
		Since `max_retry_count` may be set to a positive value, a task
		may be executed more than once. Rather than wiping out the
		prior execution history of a task each time it is rerun, we
		append another instance of `execution_info` to the `history`
		list. This provides the user with more information about why a
		task may have failed.

		This field is set to `readonly`, because workers do not write
		updates to it directly. A worker should not have to be aware of
		the current execution history of a task in order to append more
		information to it. This level of abstraction is implemented by
		having the worker post updates to a virtual subresource of
		`tasks` that models the structure of `execution_info`.
		"""
		'history': {
			'type': 'list',
			'readonly': True,
			'schema': execution_info
		}
	}
}

DOMAIN = {'tasks': tasks}
