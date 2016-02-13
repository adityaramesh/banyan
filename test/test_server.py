# -*- coding: utf-8 -*-

"""
test.test_server
----------------

Tests functionality that is implemented completely on the server-side.
"""

import unittest
from contextlib import contextmanager
from pymongo import MongoClient

# Allows us to import the 'banyan' module.
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from banyan.common import *
import banyan.auth.access as access

class Credentials():
	def __init__(self, db):
		self.db = db
		self.revoke()

		self.provider_token = access.make_token()
		self.worker_token = access.make_token()

		access.add_user('test_provider', self.provider_token, 'provider', self.db)
		access.add_user('test_worker', self.worker_token, 'worker', self.db)

		self.provider_key = access.authorization_key(self.provider_token)
		self.worker_key = access.authorization_key(self.provider_token)

	def revoke(self):
		access.remove_user('test_provider', self.db)
		access.remove_user('test_worker', self.db)

	def __str__(self):
		return str([
			self.db.users.find_one({'name': 'test_provider'}),
			self.db.users.find_one({'name': 'test_worker'})
		])

@contextmanager
def scoped_credentials(db):
	c = Credentials(db)
	yield c
	c.revoke()

def drop_tasks(db):
	db.drop_collection('tasks')

class TestAuthorization(unittest.TestCase):
	"""
	Tests that unauthorized requests to all endpoints fail.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def test_get_from_tasks(self):
		drop_tasks(db)
		resp = post(self.entry, cred.provider_key, 'tasks', {'name': 'dummy'})
		print(resp)

	def test_post_to_tasks(self):
		pass

	def test_get_from_resource_usage(self):
		pass

	def test_post_to_resource_usage(self):
		pass

	def test_get_from_execution_info(self):
		pass

	def test_post_to_execution_info(self):
		pass

#class TestTaskCreation(unittest.TestCase):
#	"""
#	Tests that creation of tasks and updates to inactive tasks work as expected.
#	"""
#
#	def __init__(self, *args, **kwargs):
#		self.db_client = MongoClient()
#		self.db = self.db_client['banyan']
#		self.entry_point = EntryPoint()
#
#		self.post_fail_msg = "Unexpected response to POST request. Input: {}. Response: {}."
#		self.patch_fail_msg = "Unexpected response to PATCH request to change '{}' from " \
#			"'{}' to '{}'. Input: {}. Response: {}."
#		super().__init__(*args, **kwargs)
#
#	# Used to drop the 'tasks' collection so that each test is independent.
#	def drop_tasks(self):
#		self.db.drop_collection('tasks')
#
#	def test_creation(self):
#		self._test_creation_without_continuations()
#		self._test_creation_with_continuations()
#
#	def _test_creation_without_continuations(self):
#		pass
#
#	def _test_creation_with_continuations(self):
#		pass
#
#	def test_updates(self):
#		self._test_resources_updates()
#		self._test_continuation_updates()
#
#	def _test_continuation_updates(self):
#		self._test_continuation_addition()
#		self._test_continuation_removal()
#
#	def _test_continuation_addition(self):
#		pass
#
#	def _test_continuation_removal(self):
#		pass

if __name__ == '__main__':
	entry = EntryPoint()
	db = MongoClient()['banyan']
	suite = unittest.TestSuite()

	with scoped_credentials(db) as cred:
		suite.addTest(make_suite(TestAuthorization, entry=entry, cred=cred, db=db))

	unittest.TextTestRunner().run(suite)
