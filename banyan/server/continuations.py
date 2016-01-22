# -*- coding: utf-8 -*-

"""
Implements the bookkeeping to manage dependency chains.
"""

from bson import ObjectId
from eve.utils import config

def find_by_id(targets, db, projection=None):
	assert isinstance(targets, ObjectId) or isinstance(targets, list)

	if isinstance(targets, ObjectId):
		doc = db.tasks.find_one({config.ID_FIELD: targets}, projection=projection)
		assert doc != None
		return doc
	else:
		cursor = db.tasks.find({config.ID_FIELD: {'$in': targets}}, projection=projection)
		assert cursor.count() == len(targets)
		return cursor

def update_by_id(targets, db, update):
	assert isinstance(targets, ObjectId) or isinstance(targets, list)

	if isinstance(targets, ObjectId):
		res = db.tasks.update_one({config.ID_FIELD: targets}, update)
		assert res.matched_count == 1
	else:
		res = db.tasks.update_many({config.ID_FIELD: {'$in': targets}}, update)
		assert res.matched_count == len(targets)

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
	targets = [child_id] if isinstance(child_id, ObjectId) else child_id
	query = {config.ID_FIELD: {'$in': targets}}
	cursor = db.tasks.find(query)

	assert cursor.count() == len(targets)

	for child in db.tasks.find(query):
		assert child['state'] == 'inactive'
		assert child['pending_dependency_count'] >= 1
	
	update_by_id(child_id, db, {
			'$inc': {'pending_dependency_count': -1},
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

"""
Called when bulk addition of continuations is performed. Checks to ensure that
a task does not attempt to add itself as a continuation. We don't perform a
full cyclic dependency check, so it's possible that things can go horribly
wrong if the user does something stupid.
"""
def validate_update(update, log_issue):
	targets = update['targets']
	values = update['values']

	if len(set(values) - set(targets)) != len(values):
		log_issue("Field 'values' contains ids from 'targets'. This would cause self-loops.")

"""
Called after validation in order to perform bulk addition of continuations. If
validation was successful, this operation should not fail. However, the
implementation is not atomic.
"""
def process_additions(updates, db):
	for update in updates:
		for parent in update['targets']:
			cur = find_by_id(parent, db, ['continuations'])['continuations']
			new = list(set(update['values']) - set(cur))

			if len(new) != 0:
				update_by_id(parent, db, {'$push': {'continuations': {'$each': new}}})
				acquire(new, db)

"""
Called after validation in order to perform bulk removal of continuations. Note
that if removing a continuation causes its dependency count to go to zero, it
is not put in the 'available' state automatically. This would complicate the
design by introducing synchronization issues. Instead, we make it the user's
responsibility to check whether the dependency count of a continuation reaches
zero when it is removed.

If validation was successful, this operation should not fail. However, the
implementation is not atomic.
"""
def process_removals(updates, db):
	print("UPDATES:")
	print(updates)

	for update in updates:
		for parent in update['targets']:
			cur = find_by_id(parent, db, ['continuations'])['continuations']
			rm = list(set(update['values']) & set(cur))
			print("REMOVED:")
			print(rm)
			print(cur)
			print(update['values'])

			if len(rm) != 0:
				update_by_id(parent, db, {'$pull': {'continuations': {'$in': rm}}})
				release_keep_inactive(rm, db)
