# -*- coding: utf-8 -*-

"""
banyan.server.event_hooks
-------------------------

Provides the event hooks that implement the server-side functionality.
"""

from bson import ObjectId
from flask import g, current_app as app
from eve.utils import config

from banyan.server.lock import lock
from banyan.server.state import legal_provider_transitions
from banyan.server.schema import virtual_resources
from banyan.server.mongo_common import find_by_id, update_by_id
import banyan.server.continuations as continuations

item_level_virtual_resources = set()
for parent_res, virtuals in virtual_resources.items():
	for virtual_res, schema in virtuals.items():
		if 'item' in schema['granularity']:
			item_level_virtual_resources.add(virtual_res)

def acquire_lock(request):
	lock.acquire()

def release_lock(request, payload):
	lock.release()

def acquire_lock_if_necessary(request, lookup):
	if not request.json:
		return

	synchronized_fields = ['state', 'add_continuations', 'remove_continuations']

	for field in synchronized_fields:
		if field in request.json:
			lock.acquire()
			g.lock_owner = True
			return

	g.lock_owner = False

def release_lock_if_necessary(request, payload):
	if g.lock_owner:
		assert lock.locked()
		lock.release()

def modify_state_changes(request, lookup):
	"""
	Converts task state changes requested by users to the actual changes that need to be made.
	"""

	assert g.token is not None
	assert g.user is not None
	updates = request.json

	if 'state' not in updates:
		return
	if not (g.user['role'] == 'provider' and updates['state'] == 'cancelled'):
		return
	if config.ID_FIELD not in lookup:
		return

	db = app.data.driver.db
	task = find_by_id('tasks', ObjectId(lookup[config.ID_FIELD]), db, {'state': True})

	if not task:
		return
	if 'cancelled' in legal_provider_transitions[task['state']]:
		return

	updates['state'] = 'pending_cancellation'

def terminate_empty_tasks(items, original=None):
	"""
	The second argument is set to ``None`` by default so that this function can be registered
	with both ``on_insert_tasks`` and ``on_update_tasks``.
	"""

	# If this function is called by ``on_update_tasks``, then ``items`` will be a dict.
	if isinstance(items, dict):
		if 'command' not in items and 'command' not in original and \
			items['state'] == 'available':
			items['state'] = 'terminated'
		return

	for item in items:
		if 'command' not in item and item['state'] == 'available':
			item['state'] = 'terminated'

def acquire_continuations(items):
	db = app.data.driver.db

	for item in items:
		if item['state'] == 'terminated':
			assert 'command' not in item, "This branch should be entered iff " \
				"the user creates a task with no command directly in the " \
				"'available' state."

			for cont_id in item['continuations']:
				continuations.try_make_available(cont_id, db)
		else:
			for cont_id in item['continuations']:
				continuations.acquire(cont_id, db)

def filter_virtual_resources(updates, original):
	"""
	Filters out updates to virtual resources and moves them to an external dictionary that is
	used after Eve performs the updates to the physical resources.
	"""

	g.virtual_resource_updates = {}

	for virtual_resource in item_level_virtual_resources:
		if virtual_resource in updates:
			g.virtual_resource_updates[virtual_resource] = updates[virtual_resource]
			updates.pop(virtual_resource)

def process_continuations(updates, original):
	"""
	Does the following two things:

	- Applies updates for ``add_continuations`` and ``remove_continuations`` virtual resources.
	- Releases and cancels child continuations of task after it is terminated or cancelled.
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

	if 'state' not in updates:
		return

	cont_list = original['continuations']

	if updates['state'] == 'cancelled':
		for x in cont_list:
			continuations.cancel(x, db)
	elif updates['state'] == 'terminated':
		# This branch won't be taken if the task is empty (i.e. has no command).
		if 'execution_data_id' in original:
			"""
			We don't cancel the continuations on unsuccessful termination, because this
			would defeat the purpose of the retry count.
			"""
			if g.virtual_resource_updates['update_execution_data']['exit_status'] != 0:
				return

		for x in cont_list:
			continuations.release(x, db)

def update_execution_data(updates, original):
	"""
	If a task is set to 'running' *for the first time*, then the following changes are made:

	- The retry count is incremented.
	- A new instance of execution data is inserted into `execution_info`,
	  along with the fields specified in `update_execution_data`.

	If a task is set to 'terminated' and its retry count is less than its maximum retry count,
	then the following changes are made:

	- The retry count is incremented.
	- The state of the task is set to `available`.
	- A new instance of execution data is inserted into `execution_info`.

	Otherwise, the changes given in `update_execution_data` are applied independently.
	"""

	db = app.data.driver.db
	id_ = original[config.ID_FIELD]
	data_updates = g.virtual_resource_updates.get('update_execution_data')

	if 'state' in updates:
		retry_count = original['retry_count']
		max_retry_count = original['max_retry_count']

		if updates['state'] == 'running' and retry_count == 0:
			assert data_updates is not None
			new_data = {'task': id_, 'retry_count': 1}
			new_data.update(data_updates)
			data_id = db.execution_info.insert(new_data)

			update_by_id('tasks', id_, db, {
				'$set': {'retry_count': 1, 'execution_data_id': data_id}
			})
			return

		if updates['state'] == 'terminated' and retry_count <= max_retry_count:
			if data_updates is None or data_updates['exit_status'] == 0:
				pass
			else:
				update_by_id('execution_info', original['execution_data_id'], db,
					{'$set': data_updates})
				new_data = {'task': id_, 'retry_count': retry_count + 1}
				data_id = db.execution_info.insert(new_data)

				update_by_id('tasks', id_, db, {
					'$inc': {'retry_count': 1},
					'$set': {'state': 'available', 'execution_data_id': data_id}
				})
				return

	if data_updates:
		data_id = original['execution_data_id']
		update_by_id('execution_info', data_id, db, {'$set': data_updates})

def register(app):
	app.on_pre_POST_tasks  += acquire_lock
	app.on_post_POST_tasks += release_lock

	app.on_pre_PATCH_tasks  += acquire_lock_if_necessary
	app.on_pre_PATCH_tasks  += modify_state_changes
	app.on_post_PATCH_tasks += release_lock_if_necessary

	app.on_insert_tasks   += terminate_empty_tasks
	app.on_inserted_tasks += acquire_continuations

	app.on_update_tasks  += terminate_empty_tasks
	app.on_update_tasks  += filter_virtual_resources
	app.on_updated_tasks += process_continuations
	app.on_updated_tasks += update_execution_data
