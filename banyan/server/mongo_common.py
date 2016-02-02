# -*- coding: utf-8 -*-

"""
Database utility functions used by many modules.
"""

from bson import ObjectId
from eve.utils import config

def find_by_id(resource, targets, db, projection=None):
	assert isinstance(targets, ObjectId) or isinstance(targets, list)

	if isinstance(targets, ObjectId):
		doc = db[resource].find_one({config.ID_FIELD: targets}, projection=projection)
		assert doc != None
		return doc
	else:
		cursor = db[resource].find({config.ID_FIELD: {'$in': targets}}, \
			projection=projection)
		assert cursor.count() == len(targets)
		return cursor

def update_by_id(resource, targets, db, update):
	assert isinstance(targets, ObjectId) or isinstance(targets, list)

	if isinstance(targets, ObjectId):
		res = db[resource].update_one({config.ID_FIELD: targets}, update)
		assert res.matched_count == 1
	else:
		res = db[resource].update_many({config.ID_FIELD: {'$in': targets}}, update)
		assert res.matched_count == len(targets)
