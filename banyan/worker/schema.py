# -*- coding: utf-8 -*-

"""
banyan.worker.schema
--------------------

Schema for dictionaries like the ones used for configuration.
"""

"""
By default, Banyan will attempt to consume all resources available on the system. Restrictions on
resource usage depend on accurate information being supplied by the user in the
``requested_resources`` field for each task.
"""
settings_schema = {
	'cpu_utilization': {
		'type': 'dict',
		'schema': {
			# We can view CPU utilization as a resource, where the total amount
			# available is given by 100 times the number of available GPUs. This field
			# restricts the cumulative CPU utilization of our processes on this worker.
			'max_usage_percent': {
				'type': 'float',
				'min': 0,
				'max': 100,
				'default': 100
			},

			# Percentage of CPU cycles that should be left available for others.
			'min_reserved_percent': {
				'type': 'float',
				'min': 0,
				'default': 0
			}
		}
	},

	'memory': {
		'type': 'dict',
		'schema': {
			# Restricts percentage of total memory that can be used.
			'max_usage_percent': {
				'type': 'float',
				'min': 0,
				'max': 100,
				'default': 100
			},

			# How much memory should be left available for others.
			'min_reserved_bytes': {
				'type': 'integer',
				'min': 0,
				'default': 0
			}
		}
	},

	'gpus': {
		'type': 'dict',
		'schema': {
			# Specifies how many GPUs should be left for others to use.
			'min_reserved': {
				'type': 'integer',
				'min': 0,
				'default': 0
			}
		}
	}
}
