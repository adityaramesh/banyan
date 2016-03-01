# -*- coding: utf-8 -*-

"""
banyan.server.schema
--------------------

Resource schema definitions.
"""

from eve.utils import config

import banyan.server.continuations as continuations
import banyan.server.execution_data as execution_data_

from banyan.server.locks import task_lock
from banyan.server.constants import *
from banyan.server.authentication import TokenAuth, RestrictCreationToProviders

"""
XXX: Don't use multiline strings to write comments inside of dicts, because the
strings will be prepended to the keys!
"""

"""
Used by the user to indicate the resources that are expected to be consumed by a task over the
course of its execution.
"""
resource_info = {
	'cpu_memory_bytes': {
		'type': 'integer',
		'min': 0,
		'default': 128 * 2 ** 20
	},

	# The scheduler on the worker will only run the associated task if
	# 	max(count, percent / 100 * available_cores)
	# cores are available. If both values are zero, then the scheduler will run the job under
	# the following constraints are met:
	# 	1. There is at least one core not reserved by any task.
	# 	2. The other constraints are met.
	'cpu_cores': {
		'type': 'dict',
		'schema': {
			'count': {
				'type': 'integer',
				'min': 0,
				'default': 0
			},

			'percent': {
				'type': 'float',
				'min': 0,
				'max': 100,
				'default': 0
			}
		}
	},

	# The abstraction for GPUs below is techincally wrong, because the same system can have two
	# different kinds of GPUs. But this is rare in computing environments, and accounting for
	# this would complicate the logic in many parts of both the server and the worker.

	'gpu_count': {
		'type': 'integer',
		'min': 0,
		'default': 0
	},

	'gpu_memory_bytes': {
		'type': 'integer',
		'min': 0
	},

	'gpu_compute_capability_major': {
		'type': 'integer',
		'min': 1
	},

	'gpu_compute_capability_minor': {
		'type': 'integer',
		'min': 0
	}
}

"""
All fields are marked 'readonly`, because they can only be modified via the 'update_execution_info'
virtual resource of the 'tasks' endpoint.
"""
execution_data = {
	'task_id': {
		'type': 'objectid',
		'data_relation': {'resource': 'tasks'},
		'readonly': True
	},

	# Describes which execution attempt that this record is associated with.
	'attempt_count': {
		'type': 'integer',
		'min': 1,
		'readonly': True
	},

	# Used to ensure that a worker cannot make an update to a job it has not claimed, or update
	# a job that it has previously claimed but is now assigned to another worker.
	'token': {
		'type': 'string',
		'minlength': 16,
		'maxlength': 16,
		'readonly': True
	},

	'worker_id': {
		'type': 'objectid',
		'data_relation': {'resource': 'users', 'field': config.ID_FIELD},
		'required': True,
		'createonly': True
	},

	'exit_status': {
		'type': 'string',
		'maxlength': max_name_string_length,
		'empty': False,
		'createonly': True
	},

	'time_started': {'type': 'datetime', 'createonly': True},
	'time_terminated': {'type': 'datetime', 'createonly': True},

	# Resource usage statistics.

	'last_update': {'type': 'datetime'},

	'memory': {
		'type': 'dict',
		'schema': {
			'resident_memory_bytes': {
				'type': 'integer',
				'required': True,
				'min': 0
			},

			'virtual_memory_bytes': {
				'type': 'integer',
				'required': True,
				'min': 0
			}
		}
	},

	'cpu_usage': {
		'type': 'dict',
		'schema': {
			# It would be nice to have per-core CPU usage, but ``psutil`` does
			# not provide a function for this as of the time of writing.
			'utilization_percent': {
				'type': 'float',
				'required': True,
				'min': 0
			}

			# It would be nice to have a list of cores on which the process is
			# running, but obtaining this information is not trivial (even htop
			# does not provide this).

			# TODO: support for NUMA topologies using ``libnuma``?
		}
	},

	# This can only be obtained from Tesla GPUs.
	'gpu_usage': {
		'type': 'list',
		'schema': {
			'type': 'dict',
			'schema': {
				'ordinal': {
					'type': 'integer',
					'required': True,
					'min': 0
				},

				# Obtained from ``nvmlDeviceGetComputeRunningProcesses``.
				'used_memory_bytes': {
					'type': 'integer',
					'required': True,
					'min': 0
				}
			}
		}
	}
}

tasks = {
	'item_title': 'task',
	'resource_methods': ['GET', 'POST'],
	'item_methods': ['GET', 'PATCH'],
	'authentication': RestrictCreationToProviders,
	'allowed_read_roles': ['provider', 'worker'],
	'allowed_write_roles': ['provider', 'worker'],

	'schema': {
		# Information provided by the client.

		'name': {
			'type': 'string',
			'maxlength': max_name_string_length,
			'unique': True,
			'mutable_iff_inactive': True
		},

		'command': {
			'type': 'string',
			'maxlength': max_command_string_length,
			'empty': False,
			'mutable_iff_inactive': True,
			'dependencies': ['requested_resources']
		},

		# If a task has no parents, the user can optionally create it in the `available`
		# state directly.
		'state': {
			'type': 'string',
			'default': 'inactive',
			'allowed': [
				# Not available to be claimed yet. If this task has dependencies,
				# then the last dependency to finish will set the state of this task
				# to `available` after it successfully terminates.
				'inactive',

				# Waiting to be claimed by a worker.
				'available',

				# Currently being run by a worker.
				'running',

				# The server puts a task in this state when it is cancelled while in
				# the `running` state. The state will be changed to `cancelled` or
				# `terminated` once the worker delivers an update.
				'pending_cancellation',

				# Either cancelled directly by the user or invalidated as a result
				# of one of the parent tasks being cancelled or terminating
				# unsuccessfully.
				'cancelled',

				# Finished executing (either successfully or unsuccessfully).
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
				'data_relation': {'resource': 'tasks', 'field': config.ID_FIELD}
			}
		},

		'requested_resources': {
			'type': 'dict',
			'dependencies': ['command'],
			'mutable_iff_inactive': True,
			'schema': resource_info
		},

		# This field is not required, and we don't enforce that the task terminates within
		# the amount of time given below. Its purpose is to allow the user to compute time
		# estimates for task chains.
		'estimated_runtime_milliseconds': {
			'type': 'integer',
			'mutable_iff_inactive': True,

			# If this task is being used as a task group (i.e. it has one or more
			# continuations but no command), then it makes no sense for the user to
			# provide a value for this field.
			'dependencies': ['command']
		},

		# The amount of time a worker will wait for a task to terminate after sending it
		# SIGTERM before resorting to using SIGKILL.
		'max_shutdown_time_milliseconds': {
			'type': 'integer',
			'min': 0,
			'dependencies': ['command'],
			'mutable_iff_inactive': True,

			# We are generous with the default cancellation time (10 minutes), in case
			# the woker must write a large amount of information to a slow disk.
			'default': 10 * 60 * 1000
		},

		# The number of times we will put a task back on the queue if we find that it
		# terminates unsuccessfully.
		'max_attempt_count': {
			'type': 'integer',
			'min': 1,
			'default': default_max_attempts,
			'dependencies': ['command'],
			'mutable_iff_inactive': True
		},

		# Information managed by the server.

		# The number of times a worker has attempted to run this task.
		'attempt_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		# If this counter is greater than zero, then the state of the task should be
		# `inactive`. Once the count reaches zero, the state of the task should be changed
		# to `available`.
		'pending_dependency_count': {
			'type': 'integer',
			'min': 0,
			'default': 0,
			'readonly': True
		},

		# Id of the `execution_data` instance that describes the most recent attempt by a
		# worker to run this task. This field is used by the server to implement the
		# `update_execution_data` virtual resource.
		'execution_data_id': {
			'type': 'objectid',
			'data_relation': {'resource': 'execution_info', 'field': config.ID_FIELD},
			'readonly': True
		}
	}
}

execution_info = {
	'authentication': TokenAuth,
	'resource_methods': ['GET'],
	'item_methods': ['GET'],
	'allowed_read_roles': ['provider'],
	'allowed_write_roles': [],
	'schema': execution_data
}

"""
This resource is not intended for access by users; it is a read-only version of the database managed
by ``access.py``. This database is exposed as a resource solely so that we can validate the
``worker_id`` field of the ``registered_users`` resource.
"""
users = {
	'schema': {
		'name': {
			'type': 'string',
			'empty': False,
			'unique': True,
			'required': True,
			'readonly': True
		},

		'role': {
			'type': 'list',
			'allowed': ['provider', 'worker'],
			'required': True,
			'readonly': True
		},

		'response_token': {
			'type': 'string',
			'dependencies': {'role': 'worker'},
			'required': True,
			'readonly': True
		},

		'request_token': {
			'type': 'string',
			'required': True,
			'readonly': True
		}
	}
}

registered_workers = {
	'authentication': TokenAuth,
	'resource_methods': ['GET', 'POST'],
	'item_methods': ['GET', 'DELETE'],
	'allowed_roles': ['provider'],
	'allowed_read_roles': ['provider'],
	'allowed_write_roles': ['provider'],

	'schema': {
		'worker_id': {
			'type': 'objectid',
			'data_relation': {'resource': 'users', 'field': config.ID_FIELD},
			'required': True,
			'createonly': True
		},

		'address': {
			'type': 'dict',
			'required': True,
			'createonly': True,

			'schema': {
				# TODO regex validation for IPv4 and IPv6. Not too important,
				# because even if the regex is valid, we still have to attempt to
				# connect to the address.
				'ip': {
					'type': 'string',
					'required': True
				},

				'port': {
					'type': 'integer',
					'min': 1,
					'max': 2 ** 16 - 1,
					'required': True
				}
			}
		},

		'permissions': {
			'type': 'list',
			'default': ['claim', 'report'],
			'allowed': ['claim', 'report'],
			'readonly': True
		}
	}
}

"""
Virtual resource definitions.

When the user performs updates on a virtual resource that has resource-level granularity (e.g.
``/tasks/add_continuations``), the payload of the update should have the following form: ::

	[
		{'targets': <target list 1>, 'values': <value list 1>},
		...
		{'targets': <target list n>, 'values': <value list n>}
	]

Below, we define the schema for the 'targets' key. In order to construct the final schema to
validate the payload sent to a virtual resource, we also need the schema for the values array. This
schema is different for each virtual resource.
"""

target_schema = {
	'targets': {
		'type': 'list',
		'maxlength': max_item_list_length,
		'allows_duplicates': False,
		'schema': {
			'type': 'objectid',
			'data_relation': {
				'resource': 'tasks',

				# The key 'field' defaults to _id, so normally, we would not need to
				# provide it explicitly. These default values for schema are set in
				# flaskapp.py. However, it's easier to provide the default value
				# manually than to apply the existing code to do it for us.
				'field': config.ID_FIELD
			}
		}
	}
}

"""
XXX: If adding or removing virtual resources, don't forget to update the corresponding stubs in the
physical resource definitions.
"""
virtual_resources = {
	'tasks': {
		'add_continuations': {
			'granularity': ['resource', 'item'],
			'validator': continuations.AddContinuationValidator,
			'on_update': continuations.make_additions,
			'lock': task_lock,

			'value_schema': {
				'type': 'list',
				'maxlength': max_item_list_length,
				'allows_duplicates': False,
				'schema': {
					'type': 'objectid',
					'data_relation': {
						'resource': 'tasks',
						'field': config.ID_FIELD
					}
				}
			}
		},

		'remove_continuations': {
			'granularity': ['resource', 'item'],
			'validator': continuations.RemoveContinuationValidator,
			'on_update': continuations.make_removals,
			'lock': task_lock,

			'value_schema': {
				'type': 'list',
				'maxlength': max_item_list_length,
				'allows_duplicates': False,
				'schema': {
					'type': 'objectid',
					'data_relation': {
						'resource': 'tasks',
						'field': config.ID_FIELD
					}
				}
			}
		},

		'update_execution_data': {
			'granularity': ['item'],
			'validator': execution_data_.ExecutionDataValidator,
			'on_update': execution_data_.make_update,
			'lock': task_lock,

			'value_schema': {
				'type': 'dict',
				'schema': execution_data
			}
		}
	}
}

for parent_res, virtuals in virtual_resources.items():
	for virtual_res, schema in virtuals.items():
		schema['schema'] = dict(target_schema)
		schema['schema']['values'] = schema['value_schema']
		globals()[parent_res]['schema'][virtual_res] = {'virtual_resource': True}
