# -*- coding: utf-8 -*-

"""
banyan.worker.schema
--------------------

Schema for dictionaries like the ones used for configuration.
"""

"""
By default, Banyan will attempt to consume all resources available on the system. The dict validated
using this schema is used to place restrictions on resource consumption.
"""
usage_limits_schema = {
	'memory': {
		'type': 'dict',
		'schema': {
			# Restricts percentage of total memory that can be used.
			'min_unused_percent': {
				'type': 'float',
				'min': 0,
				'max': 100
			},

			# Amount of memory that should be left available for others to use.
			'min_unused_bytes': {
				'type': 'integer',
				'min': 0
			}
		}
	},

	'cores': {
		'type': 'dict',
		'schema': {
			# Number of cores that should be left available for others to use.
			'min_unused_count': {
				'type': 'integer',
				'min': 0
			}
		}
	},

	'gpus': {
		'type': 'dict',
		'schema': {
			# Number of cores that should be left available for others to use.
			'min_unused_count': {
				'type': 'integer',
				'min': 0
			}
		}
	}
}
