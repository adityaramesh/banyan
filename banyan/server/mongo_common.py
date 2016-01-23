# -*- coding: utf-8 -*-

"""
Database utility functions used by many modules.
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
