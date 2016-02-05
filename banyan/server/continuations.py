# -*- coding: utf-8 -*-

"""
banyan.server.continuations
---------------------------

Implements the bookkeeping to manage dependency chains.

**Note that none of the functions in this file is thread-safe.** It is the responsibility of the
request handlers to ensure that access to resources is synchronized as needed. See
`specification.md` for details about when synchronization is necessary.
"""

from bson import ObjectId
from eve.utils import config
from mongo_common import find_by_id, update_by_id

from validation import BulkUpdateValidator

class AddContinuationValidator(BulkUpdateValidator):
	def __init__(self, schema, resource=None, allow_unknown=False, \
		transparent_schema_rules=False):

		super().__init__(schema, resource)

	def validate_update(self, updates):
		if not super().validate_update(updates):
			return False

		"""
		We don't perform a full cyclic dependency check, because doing so while holding a
		lock could cause severe performance degradations. But even in the case that a cyclic
		dependency occurs, data corruption should not occur.
		"""
		for i, update in enumerate(updates):
			targets, values = update['targets'], update['values']
			if len(set(values) - set(targets)) != len(values):
				self._error('update {}'.format(i), "Field 'values' contains ids " \
					"from 'targets'. This would cause self-loops.")

		return len(self._errors) == 0

def acquire(child_id, db):
	"""
	Invoked each time a continuation is added to a parent task.

	Args:
		child_id: ``ObjectId`` of the continuation.
		db: Handle to the `banyan` database.
	"""

	update_by_id('tasks', child_id, db, {
		'$inc': {'pending_dependency_count': 1},
		'$currentDate': {config.LAST_UPDATED: True}
	})

def release(child_id, db):
	"""
	Invoked for each child continuation when a parent task is terminated.

	Args:
		child_id: ``ObjectId`` of the continuation.
		db: Handle to the `banyan` database.
	"""

	child = find_by_id('tasks', child_id, db, {
		'state': True,
		'pending_dependency_count': True
	})

	assert child['state'] == 'inactive'
	assert child['pending_dependency_count'] >= 1

	if child['pending_dependency_count'] == 1:
		update_by_id('tasks', child_id, db, {
			'$set': {
				'state': 'available',
				'pending_dependency_count': 0
			}#,
			#'$currentDate': {config.LAST_UPDATED: True}
		})
	else:
		update_by_id('tasks', child_id, db, {
			'$dec': {'pending_dependency_count': 1},
			'$currentDate': {config.LAST_UPDATED: True}
		})

def release_keep_inactive(child_id, db):
	"""
	The parent task should call this function when a continuation is removed from it.

	Args:
		child_id`: ``ObjectId`` of the continuation.
		db: Handle to the Banyan database.
	"""

	cursor = find_by_id('tasks', child_id, db, {
		'state': True,
		'pending_dependency_count': True
	})

	for child in cursor:
		assert child['state'] == 'inactive'
		assert child['pending_dependency_count'] >= 1
	
	update_by_id('tasks', child_id, db, {
			'$inc': {'pending_dependency_count': -1},
			'$currentDate': {config.LAST_UPDATED: True}
		}
	)

def try_make_available(child_id, db):
	"""
	Called only when the parent task is created with no command, directly in the 'available'
	state. In this case, the server immediately puts the task in the 'terminated' state, and
	attempts to run all of continuations (without modifying the dependency counts).

	Args:
		child_id: ``ObjectId`` of the continuation.
		db: Handle to the `banyan` database.
	"""

	child = find_by_id('tasks', child_id, db, {
		'state': True,
		'pending_dependency_count': True
	})

	assert child['state'] == 'inactive'

	if child['pending_dependency_count'] == 0:
		update_by_id('tasks', child_id, db, {'$set': {'state': 'available'}})

def cancel(task_id, db, assert_inactive=False):
	"""
	Cancels a task, and recursively cancels all its continuations.
	
	Args:
		task_id: ID of the task to be cancelled.
		db: Handle to the `banyan` database.
		assert_inactive: Flag used to ensure that continuations further down the tree are
			inactive.
	"""

	update_by_id('tasks', task_id, db, {'$set': {'state': 'cancelled'}})

	if assert_inactive:
		task = find_by_id('tasks', task_id, db, {'continuations': True, 'state': True})
		assert task['state'] == 'inactive'
	else:
		task = find_by_id('tasks', task_id, db, {'continuations': True})

	for child in task['continuations']:
		cancel(child, db, assert_inactive=True)

	# Remove the continuation from all tasks that mention it.
	res = db.tasks.update({'continuations': {'$in': [task_id]}},
		{'$pull': {'continuations': {'$in': [task_id]}}}, multi=True)

def make_additions(updates, db):
	"""
	Called after validation in order to perform bulk addition of continuations. If validation
	was successful, this operation should not fail.
	"""

	for update in updates:
		for parent in update['targets']:
			cur = find_by_id('tasks', parent, db, ['continuations'])['continuations']
			new = list(set(update['values']) - set(cur))

			if len(new) != 0:
				update_by_id('tasks', parent, db, \
					{'$push': {'continuations': {'$each': new}}})
				acquire(new, db)

def make_removals(updates, db):
	"""
	Called after validation in order to perform bulk removal of continuations. If validation was
	successful, this operation should not fail.

	Note that if removing a continuation causes a child's dependency count to go to zero, the
	child is **not** put in the 'available' state automatically. This would complicate the
	design, because we would need to protect against the child task being made available
	inadvertently by the user. 
	"""

	for update in updates:
		for parent in update['targets']:
			cur = find_by_id('tasks', parent, db, ['continuations'])['continuations']
			rm = list(set(update['values']) & set(cur))

			if len(rm) != 0:
				update_by_id('tasks', parent, db, \
					{'$pull': {'continuations': {'$in': rm}}})
				release_keep_inactive(rm, db)
