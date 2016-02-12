# -*- coding: utf-8 -*-

"""
banyan.server.schema
--------------------

Resource schema definitions.
"""

from eve.utils import config

import banyan.server.continuations as continuations
import banyan.server.execution_data as execution_data_

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
	'memory': {
		'type': 'string',
		'regex': memory_regex,
		'maxlength': max_memory_string_length,
		'default': '128 MiB'
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

	'gpus': {
		'type': 'list',
		'default': [],
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
TODO: if we add a schema for overall resource usage reported by workers, then include the following
comments for each GPU: ::

	# The following two fields are obtained from ``nvmlDeviceGetutilizationRates``.

	'utilization_percent': {
		'type': 'float',
		'required': True,
		'min': 0,
		'max': 100
	},

	'memory_access_percent': {
		'type': 'float',
		'required': True,
		'min': 0,
		'max': 100
	}
"""

execution_data = {
	'task': {
		'type': 'objectid',
		'data_relation': {'resource': 'tasks'},
		'readonly': True
	},

	# Note that the retry count must be a positive integer.
	'retry_count': {
		'type': 'integer',
		'min': 1,
		'readonly': True
	},

	'worker': {
		'type': 'string',
		'maxlength': max_name_string_length,
		'createonly': True
	},

	'exit_status': {'type': 'integer', 'createonly': True},
	'time_started': {'type': 'datetime', 'createonly': True},
	'time_terminated': {'type': 'datetime', 'createonly': True}
}

tasks = {
	'item_title': 'task',
	'resource_methods': ['GET', 'POST'],
	'item_methods': ['GET', 'PATCH'],
	'authentication': RestrictCreationToProviders,
	'allowed_read_roles': ['user', 'worker'],
	'allowed_write_roles': ['user', 'worker'],

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
				'data_relation': {'resource': 'tasks'}
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
		'estimated_runtime': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,
			'mutable_iff_inactive': True,

			# If this task is being used as a task group (i.e. it has one or more
			# continuations but no command), then it makes no sense for the user to
			# provide a value for this field.
			'dependencies': ['command']
		},

		# The amount of time a worker will wait for a task to terminate after sending it
		# SIGTERM before resorting to using SIGKILL.
		'max_termination_time': {
			'type': 'string',
			'regex': time_regex,
			'maxlength': max_time_string_length,
			'dependencies': ['command'],
			'mutable_iff_inactive': True,

			# We are generous with the default cancellation time, in case the woker
			# must write a large amount of information to a slow disk.
			'default': '10 minutes'
		},

		# The number of times we will put a task back on the queue if we find that it
		# terminates unsuccessfully.
		'max_retry_count': {
			'type': 'integer',
			'min': 0,
			'default': default_max_retry_count,
			'dependencies': ['command'],
			'mutable_iff_inactive': True
		},

		# Information managed by the server.

		# The number of times this task has been rerun after terminating unsuccessfully.
		# Once this counter reaches `max_retry_count`, # this task will no longer be rerun.
		'retry_count': {
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
			'data_relation': {'resource': 'execution_info'},
			'readonly': True
		}
	}
}

execution_info = {
	'authentication': TokenAuth,
	'resource_methods': ['GET', 'POST'],
	'item_methods': ['GET', 'PATCH'],
	'allowed_read_roles': ['user', 'worker'],
	'allowed_write_roles': ['worker'],
	'schema': execution_data
}

resource_usage = {
	'authentication': TokenAuth,
	'resource_methods': ['GET', 'POST'],
	'item_methods': ['GET'],
	'allowed_read_roles': ['user', 'worker'],
	'allowed_write_roles': ['worker'],

	'schema': {
		'task': {
			'type': 'objectid',
			'data_relation': {'resource': 'tasks'}
		},

		'time': {
			'type': 'datetime',
			'required': True
		},

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
			'synchronize': True,

			'value_schema': {
				'type': 'list',
				'maxlength': max_item_list_length,
				'allows_duplicates': False,
				'schema': {
					'type': 'objectid',
					'data_relation': {
						'resource': 'tasks',
						'field': '_id'
					}
				}
			}
		},

		'remove_continuations': {
			'granularity': ['resource', 'item'],
			'on_update': continuations.make_removals,
			'synchronize': True,

			'value_schema': {
				'type': 'list',
				'maxlength': max_item_list_length,
				'allows_duplicates': False,
				'schema': {
					'type': 'objectid',
					'data_relation': {
						'resource': 'tasks',
						'field': '_id'
					}
				}
			}
		},

		'update_execution_data': {
			'granularity': ['item'],
			'validator': execution_data_.ExecutionDataValidator,
			'on_update': execution_data_.make_update,
			'synchronize': True,

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
