# -*- coding: utf-8 -*-

"""
Utilities for updating the execution data associated with a task.
"""

from flask import current_app as app
from eve.utils import config
from mongo_common import find_by_id, update_by_id

"""
Used by `virtual_resources.py` to validate the data sent to `update_execution_data`. Returns the id
and value of the `execution_data` instance that is currently associated with the target task.
"""
def get_target(update, log_issue):
	# Ensure that `update_execution_data` is used only at the itme level.
	assert len(update['targets']) == 1
	assert isinstance(update['values'], dict)

	db = app.data.driver.db
	task_id = update['targets'][0]
	task = find_by_id('tasks', task_id, db)
	
	assert task[config.ID_FIELD] == task_id
	assert task != None
	state = task['state']

	if state in ['inactive', 'cancelled', 'terminated']:
		log_issue("Cannot update execution data of task that is in '{}' state.".format(state))
		return None, None

	assert 'execution_data_id' in task
	target_id = task['execution_data_id']
	target = find_by_id('execution_info', target_id, db)
	return target_id, target

"""
Called after validation in order to append a new `execution_data` item to the execution history list
of a task.
"""
def process_update(updates, db):
	assert len(updates) == 1
	update = updates[0]

	assert len(update['targets']) == 1
	assert isinstance(update['values'], dict)

	db = app.data.driver.db
	task_id = update['targets'][0]
	task = find_by_id('tasks', task_id, db)
	
	assert task[config.ID_FIELD] == task_id
	assert task != None

	state = task['state']
	assert state not in ['inactive', 'cancelled', 'terminated']

	task_id = task['execution_data_id']
	res = update_by_id('execution_info', task_id, db, {'$set': update['values']})
