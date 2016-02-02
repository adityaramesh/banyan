# -*- coding: utf-8 -*-

"""
Defines the specifications necessary to implement virtual resources.

When the user performs updates on a virtual resource that has resource-level granularity (e.g.
`/tasks/add_continuations`), the payload of the update should have the following form:

	[
		{'targets': <target list 1>, 'values': <value list 1>},
		...
		{'targets': <target list n>, 'values': <value list n>}
	]

Below, we define the schema for the target key. In order to construct the final schema to validate
the payload sent to a virtual resource, we also need the schema for the values array. This schema is
different for each virtual resource.
"""

from constants import *
from physical_schema import execution_data
import continuations
import execution_data as execution_data_

"""
XXX: Don't use multiline strings to write comments inside of dicts, because the
strings will be prepended to the keys!
"""

"""
Note: we could disallow empty lists for targets using `'empty': False`, since
the update would effectively be a no-op. But returning success in this case is
technically the right thing to do.
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
				# provide it explcitly. These default values for schema are set in
				# flaskapp.py. However, it's easier to provide the default value
				# manually than to apply the existing code to do it for us.
				'field': '_id'
			}
		}
	}
}

virtual_resources = {
	'tasks': {
		'add_continuations': {
			'granularity': ['resource', 'item'],
			'validate_func': continuations.validate_update,
			'update_func': continuations.process_additions,

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
			'update_func': continuations.process_removals,

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

			# If defined, it is implied that this virtual resource is used to perform
			# **updates**, and not additions or removals. This means that internally,
			# the `validate_update` function of `Validator` is used in place of
			# `validate`. Since the former requires the id and value of the original
			# document, we need to define a function that returns this information.
			'original_doc_func': execution_data_.get_target,
			'update_func': execution_data_.process_update,
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
