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

		self.provider_name = 'test_provider'
		self.provider_token = access.make_token()

		self.worker_name = 'test_worker'
		self.worker_token = access.make_token()

		access.add_provider(self.provider_name, self.provider_token, self.db)
		access.add_worker(self.worker_name, self.worker_token, make_token(), self.db)

		self.provider_key = authorization_key(self.provider_token)
		self.worker_key = authorization_key(self.worker_token)

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

def insert_tasks(self, tasks, expected_codes=None, id_list=None):
	for i, task in enumerate(tasks):
		resp = post(task, self.entry, self.cred.provider_key, 'tasks')

		if not expected_codes:
			self.assertEqual(resp.status_code, requests.codes.created)
		else:
			self.assertEqual(resp.status_code, expected_codes[i])

		if id_list is not None:
			id_list.append(resp.json()['_id'])

def add_continuations(self, child_ids, parent_id):
	return post(child_ids, self.entry, self.cred.provider_key, 'tasks', parent_id,
		'add_continuations')

class TestAuthorization(unittest.TestCase):
	"""
	Tests that unauthorized requests to all endpoints fail.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def _test_endpoint_access_impl(self, endpoint, keys_without_write_access):
		resp = get(self.entry, None, endpoint)
		self.assertEqual(resp.status_code, requests.codes.unauthorized)

		for key in keys_without_write_access:
			resp = post({}, self.entry, key, endpoint)
			self.assertEqual(resp.status_code in [401, 405], True)

	def test_endpoint_access(self):
		pk = self.cred.provider_key
		wk = self.cred.worker_key

		self._test_endpoint_access_impl('tasks', [None, wk])
		self._test_endpoint_access_impl('execution_info', [None, wk, pk])

class TestTaskCreation(unittest.TestCase):
	"""
	Tests that creation of tasks and updates to inactive tasks work as expected.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def test_creation(self):
		self._test_creation_without_continuations()
		self._test_creation_with_continuations()

	def _test_creation_without_continuations(self):
		drop_tasks(self.db)

		tasks = [
			{'name': 'test 1'},
			{'command': 'test'},
			{'name': 'test 3', 'command': 'test'},
			{
				'name': 'test 4',
				'command': 'test',
				'requested_resources': {
					'cpu_memory_bytes': 64 * 2**30
				}
			},
			{
				'name': 'test 5',
				'command': 'test',
				'requested_resources': {
					'cpu_memory_bytes': 64 * 2**30,
					'cpu_cores': {'count': 8}
				}
			},
			{
				'name': 'test 6',
				'command': 'test',
				'requested_resources': {
					'cpu_memory_bytes': 64 * 2**30,
					'cpu_cores': {'count': 8},

					'gpu_count': 1,
					'gpu_memory_bytes': 8 * 2**30,
					'gpu_compute_capability_major': 5,
					'gpu_compute_capability_minor': 0
				}
			}
		]

		expected_codes = [
			requests.codes.created,
			requests.codes.unprocessable_entity,
			requests.codes.unprocessable_entity,
			requests.codes.created,
			requests.codes.created,
			requests.codes.created
		]

		insert_tasks(self, tasks, expected_codes=expected_codes)

	def _test_creation_with_continuations(self):
		drop_tasks(self.db)

		parents = []
		children = [
			{'name': 'child 1'},
			{'name': 'child 2', 'state': 'available'}
		]

		child_ids = []
		insert_tasks(self, children, id_list=child_ids)

		for i, child_id in enumerate(child_ids):
			parents.append({
				'name': 'parent {}'.format(i),
				'continuations': [child_id]
			})

		expected_codes = [requests.codes.created, requests.codes.unprocessable_entity]
		insert_tasks(self, parents, expected_codes=expected_codes)

		resp = get(self.entry, self.cred.provider_key, 'tasks', child_ids[0])
		self.assertEqual(resp.json()['pending_dependency_count'], 1)

	def test_updates(self):
		self._test_state_updates()
		self._test_resource_updates()
		self._test_continuation_updates()
		self._test_simultaneous_addition_and_removal()

	def _test_state_updates(self):
		drop_tasks(self.db)

		resp = post({'name': 'test'}, self.entry, self.cred.provider_key, 'tasks')
		self.assertEqual(resp.status_code, requests.codes.created)

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			resp.json()['_id'])
		self.assertEqual(resp.status_code, requests.codes.ok)

	def _test_resource_updates(self):
		"""
		Here, we verify that the behavior when attempting to change various fields of a task
		is as expected. In particular:
		1. Setting any field to its current value (e.g. a no-op) should work if the task is
		   in the ``inactive`` state.
		2. While a task is in the `inactive` state, modifying any field that is not marked
		   ``readonly`` should work.
		3. If a task is not in the `inactive` state, then any attempt to modify the value of
		   a ``readonly`` or ``createonly`` field should fail.
		"""

		changes = [
			(
				{'estimated_runtime_milliseconds': 10 * 60 * 1000},
				{'estimated_runtime_milliseconds': 20 * 60 * 1000}
			),
			(
				# The 'cores' field is already set to 1 by default, so if we don't
				# include it in the PATCH request, we would essentially be asking
				# the server to delete it. This will result in response of 422.
				{
					'requested_resources': {
						'cpu_memory_bytes': 1 * 2 ** 30,
						'cpu_cores': {'count': 1}
					}
				},
				{
					'requested_resources': {
						'cpu_memory_bytes': 2 * 2 ** 30,
						'cpu_cores': {'count': 1}
					}
				}
			),
			(
				{'max_shutdown_time_milliseconds': 10 * 60 * 1000},
				{'max_shutdown_time_milliseconds': 20 * 60 * 1000}
			),
			(
				{'max_attempt_count': 1},
				{'max_attempt_count': 2}
			)
		]

		basic_task = {
			'command': 'test',
			'requested_resources': {'cpu_memory_bytes': 1 * 2 ** 30}
		}

		# Case (1).
		for change in changes:
			drop_tasks(self.db)
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
			drop_tasks(self.db)
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
			drop_tasks(self.db)
			init, final = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **dict(init, **{'state': 'available'}))
			resp = post(task, self.entry, self.cred.provider_key, 'tasks')
			self.assertEqual(resp.status_code, requests.codes.created)

			resp = patch(final, self.entry, self.cred.provider_key, 'tasks',
				resp.json()['_id'])
			self.assertEqual(resp.status_code, requests.codes.unprocessable_entity)

	def _test_continuation_updates(self):
		drop_tasks(self.db)

		"""
		The tasks below can't be empty; otherwise, they will automatically be terminated
		when they are set to 'available', and our tests won't work. So we provide bogus
		commands.
		"""

		parents = [
			{
				'name': 'parent 1',
				'command': 'ls',
				'requested_resources': {}
			},
			{
				'name': 'parent 2',
				'command': 'ls',
				'requested_resources': {}
			},
			{
				'name': 'parent 3',
				'command': 'ls',
				'state': 'available',
				'requested_resources': {}
			}
		]

		children = [
			{
				'name': 'child 1',
				'command': 'ls',
				'requested_resources': {}
			},
			{
				'name': 'child 2',
				'command': 'ls',
				'requested_resources': {}
			},
			{
				'name': 'child 3',
				'command': 'ls',
				'state': 'available',
				'requested_resources': {}
			}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)

		def add_cont_1(child_ids, parent_id, key):
			return post(child_ids, self.entry, key, 'tasks', parent_id,
				'add_continuations')

		def add_cont_2(child_ids, parent_id, key):
			return patch({'add_continuations': child_ids}, self.entry, key, 'tasks',
				parent_id)

		def add_cont_3(child_ids, parent_id, key):
			return post([{'targets': [parent_id], 'values': child_ids}], self.entry,
				key, 'tasks', 'add_continuations')

		def remove_cont_1(child_ids, parent_id, key):
			return post(child_ids, self.entry, key, 'tasks', parent_id,
				'remove_continuations')

		def remove_cont_2(child_ids, parent_id, key):
			return patch({'remove_continuations': child_ids}, self.entry, key, 'tasks',
				parent_id)

		def remove_cont_3(child_ids, parent_id, key):
			return post([{'targets': [parent_id], 'values': child_ids}], self.entry,
				key, 'tasks', 'remove_continuations')

		# Check that adding continuations to a parent in the 'available' state fails.
		for child_id in child_ids:
			for method in [add_cont_1, add_cont_2, add_cont_3]:
				resp = method([child_id], parent_ids[2], self.cred.provider_key)
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity)

		# Check that adding an 'available' continuations to any parent task fails.
		for parent_id in parent_ids:
			for method in [add_cont_1, add_cont_2, add_cont_3]:
				resp = method([child_ids[2]], parent_id, self.cred.provider_key)
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity)

		"""
		Check that no continuations were added, even if the above operations failed as
		expected.
		"""
		for parent_id in parent_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(resp.json()['continuations'], [])

		"""
		Check that adding continuations works when performed correctly.
		"""

		for parent_id in parent_ids[:2]:
			resp = add_cont_1(child_ids[:2], parent_id, self.cred.provider_key)
			self.assertEqual(resp.status_code, requests.codes.ok)

			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(len(resp.json()['continuations']), 2)

		for child_id in child_ids[:2]:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['pending_dependency_count'], 2)

		# Check that removing a nonexistent continuations fails.
		for parent_id in parent_ids:
			for method in [remove_cont_1, remove_cont_2, remove_cont_3]:
				resp = method([child_ids[2]], parent_id, self.cred.provider_key)
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity)

		"""
		Check that removing a continuation from a task in the 'available' state fails.
		"""

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[1])
		self.assertEqual(resp.status_code, requests.codes.ok)

		for child_id in child_ids[:2]:
			for method in [remove_cont_1, remove_cont_2, remove_cont_3]:
				resp = method([child_ids[2]], parent_ids[1], self.cred.provider_key)
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity)

		"""
		Check that removing continuations works when performed correctly.
		"""

		resp = remove_cont_1(child_ids[:2], parent_ids[0], self.cred.provider_key)
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
		self.assertEqual(len(resp.json()['continuations']), 0)

		for child_id in child_ids[:2]:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['pending_dependency_count'], 1)

	def _test_simultaneous_addition_and_removal(self):
		drop_tasks(self.db)

		parents = [
			{
				'name': 'parent 1',
				'command': 'ls',
				'requested_resources': {}
			}
		]

		children = [
			{
				'name': 'child 1',
				'command': 'ls',
				'requested_resources': {}
			},
			{
				'name': 'child 2',
				'command': 'ls',
				'requested_resources': {}
			}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)

		def add_remove_cont(child_ids, parent_id, key):
			return patch({
				'add_continuations': child_ids,
				'remove_continuations': child_ids
			}, self.entry, key, 'tasks', parent_id)

		for parent_id in parent_ids:
			resp = add_remove_cont(child_ids, parent_id, self.cred.provider_key)
			self.assertEqual(resp.status_code, requests.codes.ok)

			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(len(resp.json()['continuations']), 0)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'inactive')
			self.assertEqual(resp.json()['pending_dependency_count'], 0)

class TestExecutionInfo(unittest.TestCase):
	"""
	Tests the behavior of the ``execution_data`` endpoint.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def test_updates(self):
		drop_tasks(self.db)

		tasks = [
			{'name': 'task 1', 'command': 'foo', 'requested_resources': {}},
			# Should automatically terminate, so claiming this task should fail.
			{'name': 'task 2', 'state': 'available'},
			{'name': 'task 3', 'command': 'foo', 'state': 'available',
				'requested_resources': {}}
		]

		task_ids = []
		insert_tasks(self, tasks, id_list=task_ids)

		def claim_task(task_id):
			update = {
				'state': 'running',
				'update_execution_data': {
					'worker': self.cred.worker_name
				}
			}
			return patch(update, self.entry, self.cred.worker_key, 'tasks', task_id)

		# Test that claiming a task in the wrong state fails.
		for task_id in task_ids[:2]:
			resp = claim_task(task_id)
			self.assertEqual(resp.status_code, requests.codes.unprocessable_entity)

		# Test that claiming tasks works when performed correctly.
		resp = claim_task(task_ids[2])
		token = resp.json()['token']
		self.assertEqual(resp.status_code, requests.codes.ok)

		"""
		Test that attempting to modify a readonly or createonly field of an instance of
		``execution_data`` fails.
		"""

		good_updates = [
			{'time_started': 'Tue, 02 Apr 2013 10:29:13 GMT', 'token': token}
		]

		bad_updates = [
			{'task': task_ids[0], 'token': token},
			{'attempt_count': 2, 'token': token},
			{'worker': '', 'token': token},
			{'exit_status': 'success', 'token': token},
			{'time_terminated': 'Tue, 02 Apr 2013 10:29:13 GMT', 'token': token}
		]

		def update_execution_data(update):
			return patch({'update_execution_data': update}, self.entry,
				self.cred.worker_key, 'tasks', task_ids[2])

		for update in good_updates:
			resp = update_execution_data(update)
			self.assertEqual(resp.status_code, requests.codes.ok)

		for update in bad_updates:
			resp = update_execution_data(update)
			self.assertEqual(resp.status_code, requests.codes.unprocessable_entity)

class TestCancellation(unittest.TestCase):
	"""
	Verifies that the behavior of task cancellation is as expected.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def _add_continuations(self, child_ids, parent_id):
		return post(child_ids, self.entry, self.cred.provider_key, 'tasks', parent_id,
			'add_continuations')

	def test_cancellation_depth_1(self):
		"""
		Tests cancellation on a dependency tree of depth one (i.e. parents and one level of
		continuations). The purpose of this test is to identify obvious issues in the
		implementation.
		"""

		drop_tasks(self.db)

		parents = [
			{'name': 'parent 1'},
			{'name': 'parent 2'}
		]

		children = [
			{'name': 'child 1'},
			{'name': 'child 2'}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)

		for parent_id in parent_ids:
			resp = self._add_continuations(child_ids, parent_id)
			self.assertEqual(resp.status_code, requests.codes.ok)

		resp = patch({'state': 'cancelled'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'cancelled')
			self.assertEqual(resp.json()['pending_dependency_count'], 2)

		"""
		Check that the cancelled continuations were removed from all lists that mention
		them.
		"""
		for parent_id in parent_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(resp.json()['continuations'], [])

	def test_cancellation_depth_2(self):
		"""
		Tests cancellation on a dependency tree of depth two (i.e. parents and one level of
		continuations). This test is designed to identify more subtle issues in the
		implementation.
		"""

		drop_tasks(self.db)

		parents = [
			{'name': 'parent 1'},
			{'name': 'parent 2'}
		]

		children = [
			{'name': 'child 1'},
			{'name': 'child 2'}
		]

		grandchildren = [
			{'name': 'grandchild 1'},
			{'name': 'grandchild 2'},
			{'name': 'grandchild 3'},
			{'name': 'grandchild 4'}
		]

		parent_ids = []
		child_ids = []
		grandchild_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		insert_tasks(self, grandchildren, id_list=grandchild_ids)

		"""
		Construct the tree of tasks, and verify that the continuation lists and dependency
		counts are as we expect.
		"""

		for parent_id in parent_ids:
			resp = self._add_continuations(child_ids, parent_id)
			self.assertEqual(resp.status_code, requests.codes.ok)

		for child_id in child_ids:
			resp = self._add_continuations(grandchild_ids, child_id)
			self.assertEqual(resp.status_code, requests.codes.ok)

		for parent_id in parent_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(len(resp.json()['continuations']), 2)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(len(resp.json()['continuations']), 4)
			self.assertEqual(resp.json()['pending_dependency_count'], 2)

		for grandchild_id in grandchild_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', grandchild_id)
			self.assertEqual(len(resp.json()['continuations']), 0)
			self.assertEqual(resp.json()['pending_dependency_count'], 2)

		"""
		Now we cancel just one parent, and verify that **all** continuations were cancelled
		and removed from any continuation lists that mention them.
		"""

		resp = patch({'state': 'cancelled'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		for parent_id in parent_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_id)
			self.assertEqual(len(resp.json()['continuations']), 0)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'cancelled')
			self.assertEqual(resp.json()['pending_dependency_count'], 2)
			self.assertEqual(len(resp.json()['continuations']), 0)

		for grandchild_id in grandchild_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', grandchild_id)
			self.assertEqual(resp.json()['state'], 'cancelled')
			self.assertEqual(resp.json()['pending_dependency_count'], 2)
			self.assertEqual(len(resp.json()['continuations']), 0)

class TestTermination(unittest.TestCase):
	"""
	Verifies that the behavior of task termination is as expected.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def test_empty_task_termination(self):
		drop_tasks(self.db)

		parents = [{'name': 'parent 1'}]

		children = [
			{'name': 'child 1', 'command': 'ls', 'requested_resources': {}},
			{'name': 'child 2', 'command': 'ls', 'requested_resources': {}}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		add_continuations(self, child_ids, parent_ids[0])

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.json()['state'], 'terminated')
		self.assertEqual(len(resp.json()['continuations']), 2)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'available')
			self.assertEqual(resp.json()['pending_dependency_count'], 0)

	def test_normal_task_termination(self):
		drop_tasks(self.db)

		parents = [{
			'name': 'parent 1',
			'command': 'ls',
			'requested_resources': {}
		}]

		children = [
			{'name': 'child 1', 'command': 'ls', 'requested_resources': {}},
			{'name': 'child 2', 'command': 'ls', 'requested_resources': {}}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		add_continuations(self, child_ids, parent_ids[0])

		"""
		To terminate the task, we have to have the worker first claim the task, then
		terminate it.
		"""

		claim_update = {
			'state': 'running',
			'update_execution_data': {'worker': self.cred.worker_name}
		}

		term_update = {
			'state': 'terminated',
			'update_execution_data': {
				'exit_status': 'success',
				'time_terminated': 'Tue, 02 Apr 2013 10:29:13 GMT'
			}
		}

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = patch(claim_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)
		term_update['update_execution_data']['token'] = resp.json()['token']

		resp = patch(term_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.json()['state'], 'terminated')
		self.assertEqual(len(resp.json()['continuations']), 2)

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'available')
			self.assertEqual(resp.json()['pending_dependency_count'], 0)

	def test_cancellation_after_max_attempts(self):
		"""
		Verifies that if a task is terminated and has reached the maximum number of
		execution attempts, then is no longer made available, and all of its continuations
		are cancelled.
		"""

		drop_tasks(self.db)

		parents = [{
			'name': 'task',
			'command': 'ls',
			'requested_resources': {}
		}]

		children = [
			{'name': 'child 1'},
			{'name': 'child 2'}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		add_continuations(self, child_ids, parent_ids[0])

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		claim_update = {
			'state': 'running',
			'update_execution_data': {'worker': self.cred.worker_name}
		}

		term_update = {
			'state': 'terminated',
			'update_execution_data': {
				'exit_status': 'failure',
				'time_terminated': 'Tue, 02 Apr 2013 10:29:13 GMT'
			}
		}

		resp = patch(claim_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)
		term_update['update_execution_data']['token'] = resp.json()['token']

		resp = patch(term_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)
		self.assertEqual(resp.json()['state'], 'terminated')

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'cancelled')
			self.assertEqual(resp.json()['pending_dependency_count'], 1)

	def test_retry_on_unsuccessful_termination(self):
		"""
		Verifies that if a task is terminated but has not reached its maximum attempt count,
		then it is made available again without its continuations being cancelled.
		"""

		drop_tasks(self.db)

		parents = [{
			'name': 'task',
			'command': 'ls',
			'requested_resources': {},
			'max_attempt_count': 3
		}]

		children = [
			{'name': 'child 1'},
			{'name': 'child 2'}
		]

		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		add_continuations(self, child_ids, parent_ids[0])

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		claim_update = {
			'state': 'running',
			'update_execution_data': {'worker': self.cred.worker_name}
		}

		term_update = {
			'state': 'terminated',
			'update_execution_data': {
				'exit_status': 'failure',
				'time_terminated': 'Tue, 02 Apr 2013 10:29:13 GMT'
			}
		}

		old_data_id = None

		for _ in range(2):
			resp = patch(claim_update, self.entry, self.cred.worker_key, 'tasks',
				parent_ids[0])
			self.assertEqual(resp.status_code, requests.codes.ok)
			term_update['update_execution_data']['token'] = resp.json()['token']

			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
			self.assertEqual(resp.status_code, requests.codes.ok)

			if old_data_id is not None:
				new_data_id = resp.json()['execution_data_id']
				self.assertNotEqual(old_data_id, new_data_id)
				old_data_id = new_data_id
			else:
				old_data_id = resp.json()['execution_data_id']

			resp = patch(term_update, self.entry, self.cred.worker_key, 'tasks',
				parent_ids[0])
			self.assertEqual(resp.status_code, requests.codes.ok)

			resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
			self.assertEqual(resp.status_code, requests.codes.ok)
			self.assertEqual(resp.json()['state'], 'available')

			for child_id in child_ids:
				resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
				self.assertEqual(resp.json()['state'], 'inactive')
				self.assertEqual(resp.json()['pending_dependency_count'], 1)

		"""
		Ensure that, after the max attempt count is reached, the task will no longer be made
		available on unsuccessful termination.
		"""

		resp = patch(claim_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)
		term_update['update_execution_data']['token'] = resp.json()['token']

		resp = patch(term_update, self.entry, self.cred.worker_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', parent_ids[0])
		self.assertEqual(resp.status_code, requests.codes.ok)
		self.assertEqual(resp.json()['state'], 'terminated')

		for child_id in child_ids:
			resp = get(self.entry, self.cred.provider_key, 'tasks', child_id)
			self.assertEqual(resp.json()['state'], 'cancelled')
			self.assertEqual(resp.json()['pending_dependency_count'], 1)

	def test_dependency_count(self):
		drop_tasks(self.db)

		parents = [{'name': 'parent 1'}, {'name': 'parent 2'}, {'name': 'parent 3'}]
		children = [{'name': 'child 1'}] 
		parent_ids = []
		child_ids = []

		insert_tasks(self, parents, id_list=parent_ids)
		insert_tasks(self, children, id_list=child_ids)
		add_continuations(self, child_ids, parent_ids[0])
		add_continuations(self, child_ids, parent_ids[1])
		add_continuations(self, child_ids, parent_ids[2])

		for parent_id in parent_ids[:2]:
			resp = patch({'state': 'available'}, self.entry, self.cred.provider_key,
				'tasks', parent_id)
			self.assertEqual(resp.status_code, requests.codes.ok)

			resp = get(self.entry, self.cred.provider_key, 'tasks', child_ids[0])
			self.assertEqual(resp.json()['state'], 'inactive')

		resp = patch({'state': 'available'}, self.entry, self.cred.provider_key, 'tasks',
			parent_ids[2])
		self.assertEqual(resp.status_code, requests.codes.ok)

		resp = get(self.entry, self.cred.provider_key, 'tasks', child_ids[0])
		self.assertEqual(resp.json()['state'], 'terminated')

class TestFilterQuery(unittest.TestCase):
	"""
	Tests that queries used to select tasks satisfying certain resource requirements work as
	expected.
	"""

	def __init__(self, entry, db, cred, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.entry = entry
		self.db = db
		self.cred = cred

	def test_memory_filter(self):
		drop_tasks(self.db)

		tasks = [
			{
				'name': 'task 1',
				'command': 'ls',
				'requested_resources': {'cpu_memory_bytes': 1}
			},
			{
				'name': 'task 2',
				'command': 'ls',
				'requested_resources': {'cpu_memory_bytes': 2}
			},
			{
				'name': 'task 3',
				'command': 'ls',
				'requested_resources': {'cpu_memory_bytes': 3}
			}
		]

		task_ids = []
		insert_tasks(self, tasks, id_list=task_ids)

		query = {'requested_resources.cpu_memory_bytes': {'$lte': 2}}
		resp = get(self.entry, self.cred.provider_key, 'tasks', where=query)
		self.assertEqual(len(resp.json()['_items']), 2)

	def test_cores_filter(self):
		drop_tasks(self.db)

		tasks = [
			{
				'name': 'task 1',
				'command': 'ls',
				'requested_resources': {'cpu_cores': {'count': 1}}
			},
			{
				'name': 'task 2',
				'command': 'ls',
				'requested_resources': {'cpu_cores': {'count': 2}}
			},
			{
				'name': 'task 3',
				'command': 'ls',
				'requested_resources': {'cpu_cores': {'count': 3}}
			}
		]

		task_ids = []
		insert_tasks(self, tasks, id_list=task_ids)

		query = {'requested_resources.cpu_cores.count': {'$lte': 2}}
		resp = get(self.entry, self.cred.provider_key, 'tasks', where=query)
		self.assertEqual(len(resp.json()['_items']), 2)

	def test_gpu_filter(self):
		drop_tasks(self.db)

		gpus = 1
		gpu_mem = 10
		cc_major = 2
		cc_minor = 10

		tasks = [
			# Shouldn't match because major CC is too high.
			{
				'name': 'task 1',
				'command': 'ls',
				'requested_resources': {
					'gpu_count': 1,
					'gpu_memory_bytes': 10,
					'gpu_compute_capability_major': 3,
					'gpu_compute_capability_minor': 0
				}
			},

			# Shouldn't match because memory requirement is too high.
			{
				'name': 'task 2',
				'command': 'ls',
				'requested_resources': {
					'gpu_count': 1,
					'gpu_memory_bytes': 15,
					'gpu_compute_capability_major': 2,
					'gpu_compute_capability_minor': 0
				}
			},

			# This one should match.
			{
				'name': 'task 3',
				'command': 'ls',
				'requested_resources': {
					'gpu_count': 1,
					'gpu_memory_bytes': 10,
					'gpu_compute_capability_major': 1,
					'gpu_compute_capability_minor': 100
				}
			}
		]

		task_ids = []
		insert_tasks(self, tasks, id_list=task_ids)

		query = {
			'$and': [
				{'requested_resources.gpu_count': {'$lte': gpus}},
				{'requested_resources.gpu_memory_bytes': {'$lte': gpu_mem}},
				{'$or': [
					{'requested_resources.gpu_compute_capability_major':
						{'$lt': cc_major}},
					{'$and': [
						{'requested_resources.gpu_compute_capability_major':
							{'$eq': cc_major}},
						{'requested_resources.gpu_compute_capability_minor':
							{'$lte': cc_minor}}
					]}
				]}
			]
		}

		resp = get(self.entry, self.cred.provider_key, 'tasks', where=query)
		self.assertEqual(len(resp.json()['_items']), 1)
		
if __name__ == '__main__':
	entry = EntryPoint()
	db = MongoClient()['banyan']
	suite = unittest.TestSuite()

	with scoped_credentials(db) as cred:
		suite.addTest(make_suite(TestAuthorization, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestTaskCreation, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestExecutionInfo, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestCancellation, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestTermination, entry=entry, cred=cred, db=db))
		suite.addTest(make_suite(TestFilterQuery, entry=entry, cred=cred, db=db))
		unittest.TextTestRunner().run(suite)
