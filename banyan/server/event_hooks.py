# -*- coding: utf-8 -*-

"""
banyan.server.event_hooks
-------------------------

Provides the event hooks that implement the server-side functionality not
falling under the purview of REST.
"""

from flask import g, current_app as app
from eve.utils import config

from schema import virtual_resources
from mongo_common import find_by_id, update_by_id
import continuations

item_level_virtual_resources = set()
for parent_res, virtuals in virtual_resources.items():
	for virtual_res, schema in virtuals.items():
		if 'item' in schema['granularity']:
			item_level_virtual_resources.add(virtual_res)

def terminate_empty_tasks(items):
	for item in items:
		if 'command' not in item and item['state'] == 'available':
			item['state'] = 'terminated'

def acquire_continuations(items):
	for item in items:
		if item['state'] == 'terminated':
			assert 'command' not in item, "This branch should be entered iff " \
				"the user creates a task with no command directly in the " \
				"'available' state."

			for cont_id in item['continuations']:
				continuations.try_make_available(cont_id, self.db)
		else:
			for cont_id in item['continuations']:
				continuations.acquire(cont_id, self.db)

def filter_virtual_resources(updates, original):
	"""
	Filters out updates to virtual resources and moves them to an external
	dictionary that is used after Eve performs the updates to the physical
	resources.
	"""

	g.virtual_resource_updates = {}

	for virtual_resource in item_level_virtual_resources:
		if virtual_resource in updates:
			g.virtual_resource_updates[virtual_resource] = updates[virtual_resource]
			updates.pop(virtual_resource)

def modify_state_changes(updates, original):
	"""
	Converts task state changes requested by users to the actual changes
	that need to be made.
	"""

	assert g.token is not None
	assert g.user is not None

	if 'state' not in updates:
		return

	if g.user['role'] == 'provider' and updates['state'] == 'cancelled':
		updates['state'] = 'pending_cancellation'

def process_continuations(updates, original):
	"""
	Does the following two things:
	- Applies updates for ``add_continuations`` and
	  ``remove_continuations`` virtual resources.
	- Releases and cancels child continuations of task after it is
	  terminated or cancelled.
	"""

	db = app.data.driver.db
	id_ = original[config.ID_FIELD]

	if 'add_continuations' in g.virtual_resource_updates:
		continuations.make_additions([{
			'targets': [id_],
			'values': g.virtual_resource_updates['add_continuations']
		}], db)
	if 'remove_continuations' in g.virtual_resource_updates:
		continuations.make_removals([{
			'targets': [id_],
			'values': g.virtual_resource_updates['remove_continuations'],
		}], db)

	if not 'state' in updates:
		return

	if updates['state'] == 'cancelled':
		continuations.cancel(original[config.ID_FIELD], db)
	elif updates['state'] == 'terminated':
		continuations.release(original[config.ID_FIELD], db)

def update_execution_data(updates, original):
	"""
	If a task is set to 'running' *for the first time*, then the following
	changes are made:
	- The retry count is incremented.
	- A new instance of execution data is inserted into `execution_info`,
	  along with the fields specified in `update_execution_data`.

	If a task is set to 'terminated' and its retry count is less than its
	maximum retry count, then the following changes are made:
	- The retry count is incremented.
	- The state of the task is set to `available`.
	- A new instance of execution data is inserted into `execution_info`.

	Otherwise, the changes given in `update_execution_data` are applied
	independently.
	"""

	db = app.data.driver.db
	id_ = original[config.ID_FIELD]

	retry_count = original['retry_count']
	max_retry_count = original['max_retry_count']
	data_updates = g.virtual_resource_updates.get('update_execution_data')

	if retry_count == 0:
		assert data_updates is not None
		new_data = {'task': id_, 'retry_count': 1}
		new_data.update(data_updates)
		data_id = db.execution_info.insert(new_data)

		update_by_id('tasks', id_, db, {
			'$inc': {'retry_count': 1},
			'$set': {'execution_data_id': data_id}
		})
		return

	if updates['state'] == 'terminated' and retry_count < max_retry_count:
		update_by_id('tasks', id_, db, {'$inc': {'retry_count': 1}})

	if data_updates:
		data_id = original['execution_data_id']
		update_by_id('execution_info', data_id, db, data_updates)

def register(app):
	# TODO acquire/release locks when appropriate

	# Event hooks for insertion.
	app.on_insert_tasks   += terminate_empty_tasks
	app.on_inserted_tasks += acquire_continuations

	# Event hooks for updates.
	app.on_update_tasks  += filter_virtual_resources
	app.on_update_tasks  += modify_state_changes
	app.on_updated_tasks += process_continuations
	app.on_updated_tasks += update_execution_data
