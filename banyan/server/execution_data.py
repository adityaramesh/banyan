# -*- coding: utf-8 -*-

"""
banyan.server.execution_data
----------------------------

Utilities for updating the execution data associated with a task.
"""

from flask import current_app as app
from eve.utils import config
from mongo_common import find_by_id, update_by_id

from validation import BulkUpdateValidator

class ExecutionDataValidator(BulkUpdateValidator):
	def __init__(self, schema, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		super().__init__(schema, resource)

	def validate_update(self, updates):
		if not self.validate_update_format(updates):
			return False

		assert len(updates) == 1
		update = updates[0]

		# Ensure that `update_execution_data` is used only at the item level.
		assert len(update['targets']) == 1
		assert isinstance(update['values'], dict)

		db = app.data.driver.db
		task_id = update['targets'][0]
		task = find_by_id('tasks', task_id, db)
		
		assert task[config.ID_FIELD] == task_id
		assert task is not None
		state = task['state']

		if state in ['inactive', 'cancelled', 'terminated']:
			self._error('target', "Cannot update execution data of task in '{}' state.". \
				format(state))
			return False

		assert 'execution_data_id' in task
		target_id = task['execution_data_id']
		target = find_by_id('execution_info', target_id, db)

		return super().validate_update_content(updates, original_ids=[target_id],
			original_documents=[target])

def make_update(updates, db):
	"""
	Called after validation in order to append a new ``execution_data`` item to the execution
	history list of a task.
	"""

	assert len(updates) == 1
	update = updates[0]

	assert len(update['targets']) == 1
	assert isinstance(update['values'], dict)

	db = app.data.driver.db
	task_id = update['targets'][0]
	task = find_by_id('tasks', task_id, db)

	assert task[config.ID_FIELD] == task_id
	assert task is not None

	state = task['state']
	assert state not in ['inactive', 'cancelled', 'terminated']

	task_id = task['execution_data_id']
	update_by_id('execution_info', task_id, db, {'$set': update['values']})
