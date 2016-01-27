# -*- coding: utf-8 -*-

"""
Schema definitions for physical resources.
"""

from constants import *
from authentication import ValidateToken, RestrictWriteAccess

"""
XXX: Don't use multiline strings to write comments inside of dicts, because the
strings will be prepended to the keys!
"""

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

execution_info = {
	'type': 'dict',
	'schema': {
		'worker': {
			'type': 'string',
			'maxlength': max_name_string_length,
			'required': True
		},

		'exit_status': {'type': 'integer'},
		'time_started': {'type': 'datetime'},
		'time_terminated': {'type': 'datetime'}
	}
}

tasks = {
	'item_title': 'task',
	'authentication': ValidateToken,

	'schema': {
		# Information provided by the client.

		'command': {
			'type': 'string',
			'maxlength': max_command_string_length,
			'empty': False,
			'mutable_iff_inactive': True,
			'dependencies': ['requested_resources']
		},

		'name': {
			'type': 'string',
			'maxlength': max_name_string_length,
			'empty': False,
			'unique': True,
			'mutable_iff_inactive': True
		},

		# If a task has no parents, the user can optionally create it
		# in the `available` state directly.
		'state': {
			'type': 'string',
			'default': 'inactive',
			'allowed': [
				# Not available to be claimed yet. If this task
				# has dependencies, then the last dependency to
				# finish will set the state of this task to
				# `available` after it successfully terminates.
				'inactive',

				# Waiting to be claimed by a worker.
				'available',

				#Currently being run by a worker.
				'running',

				# The server puts a task in this state when it
				# is cancelled while in the `running` state.
				# The state will be changed to `cancelled` or
				# `terminated` once the worker delivers an
				# update.
				'pending_cancellation',

				# Either cancelled directly by the user or
				# invalidated as a result of one of the parent
				# tasks being cancelled or terminating
				# unsuccessfully.
				'cancelled',

				# Finished executing (either successfully or
				# unsuccessfully).
				'terminated'
			]
		},

		'continuations': {
			'type': 'list',
			'maxlength': max_item_list_length,
			'default': [],
			'allows_duplicates': False,
			'creatable_iff_inactive': True,
			'schema': {
				'type': 'objectid',
				'data_relation': {'resource': 'tasks'}
			}
		},

		# This field is not required, and we don't enforce that the task
		# terminates within the amount of time given below. Its purpose
		# is to allow the user to compute time estimates for task
		# chains.
		'estimated_runtime': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,
			'mutable_iff_inactive': True,

			# If this task is being used as a task group (i.e. it
			# has one or more continuations but no command), then it
			# makes no sense for the user to provide a value for
			# this field.
			'dependencies': ['command']
		},

		'requested_resources': {
			'type': 'dict',
			'dependencies': ['command'],
			'mutable_iff_inactive': True,
			'schema': resource_info
		},

		# The amount of time a worker will wait for a task to terminate
		# after sending it SIGTERM before resorting to using SIGKILL.
		'max_termination_time': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,
			'dependencies': ['command'],
			'mutable_iff_inactive': True,

			# We are generous with the default cancellation time, in
			# case the woker must write a large amount of
			# information to a slow disk.
			'default': '10 minutes'
		},

		# The number of times we will put a task back on the queue if we
		# find that it terminates unsuccessfully.
		'max_retry_count': {
			'type': 'integer',
			'min': 0,
			'max': max_supported_retry_count,
			'default': 0,
			'dependencies': ['command'],
			'mutable_iff_inactive': True
		},

		# Information managed by the server.

		# The number of times this task has been rerun after terminating
		# unsuccessfully. Once this counter reaches `max_retry_count`,
		# this task will no longer be rerun.
		'retry_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		# If this counter is greater than zero, then the state of the
		# task should be `inactive`. Once the count reaches zero, the
		# state of the task should be changed to `available`.
		'pending_dependency_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		# Contains information about workers' attempts to run this task.
		'execution_history': {
			'type': 'list',
			'readonly': True,
			'maxlength': max_supported_retry_count,
			'schema': execution_info
		}
	}
}

"""
We don't need to store the retry attempt associated with each entry below; the entries associated
with a given retry attempt can be determined automatically using the start and termination times.
"""

memory_usage = {
	'authentication': RestrictWriteAccess,
	'allowed_roles': ['worker'],

	'schema': {
		'task': {
			'type': 'objectid',
			'data_relation': {'resource': 'tasks'}
		},

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

cpu_usage = {
	'authentication': RestrictWriteAccess,
	'allowed_roles': ['worker'],

	'schema': {
		'task': {
			'type': 'objectid',
			'data_relation': {'resource': 'tasks'}
		},

		'time': {
			'type': 'datetime',
			'required': True
		},

		'usage': {
			'type': 'list',
			'empty': False,
			'schema': {
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
	}
}

gpu_usage = {
	'authentication': RestrictWriteAccess,
	'allowed_roles': ['worker'],

	'schema': {
		'task': {
			'type': 'objectid',
			'data_relation': {'resource': 'tasks'}
		},

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
