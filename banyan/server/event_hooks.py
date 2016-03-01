# -*- coding: utf-8 -*-

"""
banyan.server.event_hooks
-------------------------

Provides the event hooks that implement the server-side functionality.
"""

import json
from bson import ObjectId
from werkzeug.exceptions import HTTPException
from flask import g, current_app as app
from eve.utils import config

from banyan.common import make_token
from banyan.server.locks import task_lock, registered_workers_lock
from banyan.server.state import legal_provider_transitions
from banyan.server.schema import virtual_resources
from banyan.server.mongo_common import find_by_id, update_by_id
from banyan.server.execution_data import is_exit_success
import banyan.server.continuations as continuations

item_level_virtual_resources = set()
for parent_res, virtuals in virtual_resources.items():
	for virtual_res, schema in virtuals.items():
		if 'item' in schema['granularity']:
			item_level_virtual_resources.add(virtual_res)

def acquire_lock(lock):
	def impl(request, lookup=None):
		lock.acquire()
		g.lock_owner = True

	return impl

def release_lock_if_necessary(lock):
	def impl(request, payload):
		if hasattr(g, 'lock_owner') and g.lock_owner:
			assert lock.locked()
			lock.release()

	return impl

def acquire_task_lock_if_necessary(request, lookup):
	if not request.json:
		return

	synchronized_fields = ['state', 'add_continuations', 'remove_continuations']

	for field in synchronized_fields:
		if field in request.json:
			task_lock.acquire()
			g.lock_owner = True
			return

	g.lock_owner = False

def modify_state_changes(request, lookup):
	"""
	Converts task state changes requested by users to the actual changes that need to be made.
	Also appends the task ID to the ``g`` object, so that ``append_execution_data_token`` can
	run the database query to obtain the token.
	"""

	assert g.token is not None
	assert g.user is not None
	updates = request.json

	"""
	``config.ID_FIELD`` should be in ``lookup`` if a state change is being made, but we will let
	the validator take care of diagnosing and reporting this error.
	"""
	if 'state' not in updates or config.ID_FIELD not in lookup:
		return
	if updates['state'] == 'running':
		g.task_id = lookup[config.ID_FIELD]
		return
	if g.user['role'] != 'provider' or updates['state'] != 'cancelled':
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
		if 'execution_data_id' in original:
			execution_data = g.virtual_resource_updates['update_execution_data']
			exit_status    = execution_data['exit_status']

			if is_exit_success(exit_status):
				for x in cont_list:
					continuations.release(x, db)
				return

			attempt_count     = original['attempt_count']
			max_attempt_count = original['max_attempt_count']
			assert attempt_count <= max_attempt_count

			if attempt_count < max_attempt_count:
				return
			else:
				for x in cont_list:
					continuations.cancel(x, db, assert_inactive=True)
		else:
			"""
			If this branch is taken, then it means that the terminated task had no
			command (i.e. its purpose was only to group together a set of
			continuations). In this case, termination is always considered successful,
			and we release all of the continuations.
			"""
			for x in cont_list:
				continuations.release(x, db)

def update_execution_data(updates, original):
	"""
	If a task is set to 'running' *for the first time*, then the following changes are made:

	- The attempt count is incremented.
	- A new instance of execution data is inserted into `execution_info`,
	  along with the fields specified in `update_execution_data`.

	If a task is set to 'terminated' and its attempt count is less than its maximum attempt
	count, then the following changes are made:

	- The attempt count is incremented.
	- The state of the task is set to `available`.
	- A new instance of execution data is inserted into `execution_info`.

	Otherwise, the changes given in `update_execution_data` are applied independently.
	"""

	db = app.data.driver.db
	id_ = original[config.ID_FIELD]
	data_updates = g.virtual_resource_updates.get('update_execution_data')

	if 'state' in updates:
		attempt_count = original['attempt_count']
		max_attempt_count = original['max_attempt_count']

		if updates['state'] == 'running':
			if attempt_count == 0:
				assert data_updates is not None
				new_data = {
					'task_id': id_,
					'attempt_count': 1,
					'token': make_token()
				}

				new_data.update(data_updates)
				data_id = db.execution_info.insert(new_data)

				update_by_id('tasks', id_, db, {
					'$set': {'attempt_count': 1, 'execution_data_id': data_id}
				})
			return

		if updates['state'] == 'terminated' and attempt_count < max_attempt_count:
			if data_updates is None or is_exit_success(data_updates['exit_status']):
				pass
			else:
				update_by_id('execution_info', original['execution_data_id'], db,
					{'$set': data_updates})
				new_data = {
					'task_id': id_,
					'attempt_count': attempt_count + 1,
					'token': make_token()
				}

				data_id = db.execution_info.insert(new_data)
				update_by_id('tasks', id_, db, {
					'$inc': {'attempt_count': 1},
					'$set': {'state': 'available', 'execution_data_id': data_id}
				})
				return

	if data_updates:
		data_updates.pop('token')
		data_id = original['execution_data_id']
		update_by_id('execution_info', data_id, db, {'$set': data_updates})

def append_execution_data_token(request, payload):
	if not hasattr(g, 'task_id') or payload.status_code != 200:
		return

	db = app.data.driver.db
	task = find_by_id('tasks', ObjectId(g.task_id), db, {'execution_data_id': True})
	data = find_by_id('execution_info', task['execution_data_id'], db, {'token': True})

	parsed_payload = json.loads(payload.get_data().decode('utf-8'))
	parsed_payload['token'] = data['token']
	payload.set_data(json.dumps(parsed_payload))

def register(app):
	app.on_pre_POST_tasks  += acquire_lock(task_lock)
	app.on_post_POST_tasks += release_lock_if_necessary(task_lock)

	"""
	We also need to synchronize registration/unregistration of workers, since this could
	potentially trigger races with authentication or validation when checking worker
	permissions.
	"""
	app.on_pre_POST_registered_workers    += acquire_lock(registered_workers_lock)
	app.on_post_POST_registered_workers   += release_lock_if_necessary(registered_workers_lock)
	app.on_pre_DELETE_registered_workers  += acquire_lock(registered_workers_lock)
	app.on_post_DELETE_registered_workers += release_lock_if_necessary(registered_workers_lock)

	app.on_pre_PATCH_tasks  += acquire_task_lock_if_necessary
	app.on_pre_PATCH_tasks  += modify_state_changes
	app.on_post_PATCH_tasks += append_execution_data_token
	app.on_post_PATCH_tasks += release_lock_if_necessary(task_lock)

	app.on_insert_tasks   += terminate_empty_tasks
	app.on_inserted_tasks += acquire_continuations

	app.on_update_tasks  += terminate_empty_tasks
	app.on_update_tasks  += filter_virtual_resources
	app.on_updated_tasks += process_continuations
	app.on_updated_tasks += update_execution_data

	"""
	When this flag is false (the default value), exceptions which are instances of
	``HTTPException`` are handled by functions decorated with ``errorhandler(n)``, where ``n``
	is the HTTP error code. When this flag is true, instances of ``HTTPException`` can be
	handled by the regular error handlers. See `this SO answer`_ for more information.

	.. _this SO answer: http://stackoverflow.com/a/33711404/414271
	"""
	app.config['TRAP_HTTP_EXCEPTIONS'] = True

	@app.errorhandler(Exception)
	def handle_error(error):
		release_lock_if_necessary(task_lock)(None, None)
		release_lock_if_necessary(registered_workers_lock)(None, None)

		if isinstance(error, HTTPException):
			return error
		else:
			raise
