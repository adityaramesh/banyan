# -*- coding: utf-8 -*-

"""
Utilities for updating the execution history associated with a task.
"""

from mongo_common import find_by_id, update_by_id

"""
Called after validation in order to append a new `execution_info` item to the execution history list
of a task.
"""
def process_addition(updates, db):
	assert len(updates) == 1
	targets = updates[0]['targets']
	values = updates[0]['values']

	assert len(targets) == 1
	assert isinstance(values, dict)
	update_by_id(targets[0], db, {'$push': {'execution_history': values}})
