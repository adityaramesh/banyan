# -*- coding: utf-8 -*-

"""
test.test_server
----------------

Tests functionality that is implemented completely on the server-side.
"""

import itertools
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
		self.worker_key = access.authorization_key(self.worker_token)

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

	def _endpoint_access_impl(self, endpoint, keys_without_write_access):
		resp = get(self.entry, None, endpoint)
		self.assertEqual(resp.status_code, requests.codes.unauthorized)

		for key in keys_without_write_access:
			resp = post({}, self.entry, key, endpoint)
			self.assertEqual(resp.status_code, requests.codes.unauthorized)

	def test_endpoint_access(self):
		pk = self.cred.provider_key
		wk = self.cred.worker_key

		self._endpoint_access_impl('tasks', [None, wk])
		self._endpoint_access_impl('execution_info', [None, pk])
		self._endpoint_access_impl('execution_info', [None, wk, pk])

class TestTaskCreation(unittest.TestCase):
	"""
	Tests that creation of tasks and updates to inactive tasks work as expected.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	# Used to drop the 'tasks' collection so that each test is independent.
	def drop_tasks(self):
		self.db.drop_collection('tasks')

	def test_creation(self):
		self._test_creation_without_continuations()
		self._test_creation_with_continuations()

	def _test_creation_without_continuations(self):
		self.drop_tasks()

		ops = [
			(
				{'name': 'test 1'},
				requests.codes.created
			),
			(
				{'command': 'test'},
				# Because ``requested_resources`` is required.
				requests.codes.unprocessable_entity
			),
			(
				{'name': 'test 3', 'command': 'test'},
				requests.codes.unprocessable_entity
			),
			(
				{
					'name': 'test 4',
					'command': 'test',
					'requested_resources': {
						'memory': '64 GiB'
					}
				},
				requests.codes.created
			),
			(
				{
					'name': 'test 5',
					'command': 'test',
					'requested_resources': {
						'memory': '64 GiB',
						'cpu_cores': {'count': 8}
					}
				},
				requests.codes.created
			),
			(
				{
					'name': 'test 6',
					'command': 'test',
					'requested_resources': {
						'memory': '64 GiB',
						'cpu_cores': {'count': 8},
						'gpus': [{
							'memory': '8 GiB',
							'min_compute_capability': '5.0'
						}]
					}
				},
				requests.codes.created
			)
		]

		for task, expected_status in ops:
			resp = post(task, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, expected_status)

	def _test_creation_with_continuations(self):
		self.drop_tasks()

		parents = []
		children = [
			{'name': 'child 1'},
			{'name': 'child 2', 'state': 'available'}
		]

		for i, child in enumerate(children):
			resp = post(child, self.entry, self.cred.provider_key, 'tasks')
			json = resp.json()
			self.assertEqual(resp.status_code, requests.codes.created)

			if i == 0:
				child_id = json['_id']

			parents.append({
				'name': 'parent {}'.format(i),
				'continuations': [json['_id']]
			})

		expected_codes = [requests.codes.created, requests.codes.unprocessable_entity]
		for parent, code in zip(parents, expected_codes):
			resp = post(parent, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, code)

		resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
		self.assertEqual(resp.json()['pending_dependency_count'], 1)

	def test_updates(self):
		self._test_state_updates()
		self._test_resource_updates()
		self._test_continuation_updates()

	def _test_state_updates(self):
		self.drop_tasks()
		
		resp = post({'name': 'test'}, self.entry, self.cred.provider_key, 'tasks')
		self.assertEqual(resp.status_code, requests.codes.created)

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			resp.json()['_id'])
		self.assertEqual(resp.status_code, requests.codes.ok)	

	def _test_resource_updates(self):
		"""
		Here, we verify that the behavior when attempting to change various fields of a task
		is as expected. In particular:
		1. Setting any field to its current value (e.g. a no-op) should work if the task is in                   the ``inactive`` state.
		2. While a task is in the `inactive` state, modifying any field that is not marked
		   ``readonly`` should work.
		3. If a task is not in the `inactive` state, then any attempt to modify the value of
		   a ``readonly`` or ``createonly`` field should fail.
		"""

		states = ['inactive', 'available']

		changes = [
			(
				{'estimated_runtime': '10 minutes'},
				{'estimated_runtime': '20 minutes'}
			),
			(
				# The 'cores' field is already set to 1 by default, so if we don't
				# include it in the PATCH request, we would essentially be asking
				# the server to delete it. This will result in response of 422.
				{'requested_resources': {'memory': '1 GiB',
					'cpu_cores': {'count': 1}}},
				{'requested_resources': {'memory': '2 GiB',
					'cpu_cores': {'count': 1}}}
			),
			(
				{'max_termination_time': '10 minutes'},
				{'max_termination_time': '20 minutes'}
			),
			(
				{'max_retry_count': 1},
				{'max_retry_count': 2}
			)
		]

		basic_task = {
			'command': 'test',
			'requested_resources': {'memory': '1 GiB'}
		}

		# Case (1).
		for change in changes:
			self.drop_tasks()
			init, _ = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **dict(init, **{'state': 'inactive'}))
			resp = post(task, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, requests.codes.created)
			
			resp = patch(init, self.entry, self.cred.provider_key, 'tasks',
				resp.json()['_id'])
			self.assertEqual(resp.status_code, requests.codes.ok)

		# Case (2).
		for change in changes:
			self.drop_tasks()
			init, final = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **init)
			resp = post(task, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, requests.codes.created)
			
			resp = patch(final, self.entry, self.cred.provider_key, 'tasks',
				resp.json()['_id'])
			self.assertEqual(resp.status_code, requests.codes.ok)

		# Case (3).
		for change in changes:
			self.drop_tasks()
			init, final = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **dict(init, **{'state': 'available'}))
			resp = post(task, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, requests.codes.created)
			
			resp = patch(final, self.entry, self.cred.provider_key, 'tasks',
				resp.json()['_id'])
			self.assertEqual(resp.status_code, requests.codes.unprocessable_entity)

	def _test_continuation_updates(self):
		pass
		#self.drop_tasks()

		#parents = [
		#	{'name': 'parent 1'},
		#	{'name': 'parent 2'},
		#	{'name': 'parent 3', 'state': 'available'}
		#]
		#children = [
		#	{'name': 'child 1'},
		#	{'name': 'child 2'},
		#	{'name': 'child 3', 'state': 'available'}
		#]

		#parent_ids = []
		#child_ids = []

		#for i, parent in enumerate(parents):
		#	resp = post(parent, self.entry, self.cred.provider_key, 'tasks')
		#	json = resp.json()
		#	self.assertEqual(resp.status_code, requests.codes.created)
		#	parent_ids.append(json['_id'])

		#for i, child in enumerate(children):
		#	resp = post(child, self.entry, self.cred.provider_key, 'tasks')
		#	json = resp.json()
		#	self.assertEqual(resp.status_code, requests.codes.created)
		#	child_ids.append(json['_id'])

		#

		# TODO check all three forms of add/remove continuations virtual resource (ie both
		# granularities)
		# TODO check that attempting to add/remove continuations to/from a task in the
		# 'available' state fails.

if __name__ == '__main__':
	entry = EntryPoint()
	db = MongoClient()['banyan']
	suite = unittest.TestSuite()

	with scoped_credentials(db) as cred:
		suite.addTest(make_suite(TestAuthorization, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestTaskCreation, entry=entry, cred=cred, db=db))
		unittest.TextTestRunner().run(suite)
