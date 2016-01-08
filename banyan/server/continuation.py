# -*- coding: utf-8 -*-

"""
Implements the bookkeeping to manage dependency chains.
"""

from eve.utils import config

def update_by_id(child_id, db, update):
	res = db.tasks.update_one({config.ID_FIELD: child_id}, update)
	assert res.modified_count == 1

"""
The parent task should call this function when a new continuation is added to
it. Parameters:
- `child_id`: `ObjectId` of the continuation.
- `db`: Handle to the `banyan` database.
"""
def acquire(child_id, db):
	update_by_id(child_id, db, {
		'$inc': {'pending_dependency_count': 1},
		'$currentDate': {config.LAST_UPDATED: True}
	})

"""
The the parent task terminates, it should invoke this function on each of its
continuations.
- `child_id`: `ObjectId` of the continuation.
- `db`: Handle to the `banyan` database.
"""
def release(child_id, db):
	query = {config.ID_FIELD: child_id}
	child = db.tasks.find_one(query)

	assert child['state'] == 'inactive'
	assert child['pending_dependency_count'] >= 1
	
	if child['pending_dependency_count'] == 1:
		update_by_id(child_id, db,
			{
				'$set': {
					'state': 'available',
					'pending_dependency_count': 0
				},
				'$currentDate': {config.LAST_UPDATED: True}
			}
		)
	else:
		update_by_id(child_id, db,
			{
				'$dec': {'pending_dependency_count': 1},
				'$currentDate': {config.LAST_UPDATED: True}
			}
		)

"""
The parent task should call this function when a continuation is removed from
it.
- `child_id`: `ObjectId` of the continuation.
- `db`: Handle to the `banyan` database.
"""
def release_keep_inactive(child_id, db):
	query = {config.ID_FIELD: child_id}
	child = db.tasks.find_one(query)

	assert child['state'] == 'inactive'
	assert child['pending_dependency_count'] >= 1
	
	update_by_id(child_id, db,
		{
			'$dec': {'pending_dependency_count': 1},
			'$currentDate': {config.LAST_UPDATED: True}
		}
	)

"""
Called only when the parent task is created with no command, directly in the
'available' state. In this case, the server immediately puts the task in the
'terminated' state, and attempts to run all of continuations (without modifying
the dependency counts).
- `child_id`: `ObjectId` of the continuation.
- `db`: Handle to the `banyan` database.
"""
def try_make_available(child_id, db):
	query = {config.ID_FIELD: child_id}
	child = db.tasks.find_one(query)
	assert child['state'] == 'inactive'

	if child['pending_dependency_count'] == 0:
		update_by_id(child_id, db, {'$set': {'state': 'available'}})
