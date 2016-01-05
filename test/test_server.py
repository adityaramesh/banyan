# -*- coding: utf-8 -*-

"""
Tests the server.
"""

import socket
import requests
import json
import unittest

# Allows us to import the 'banyan' module.
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from copy import deepcopy
from itertools import product
from pymongo import Connection
from banyan.server.validation import LEGAL_USER_STATE_TRANSITIONS

class EntryPoint:
	def __init__(self):
		self.ip = socket.gethostbyname(socket.gethostname())
		self.base_url = 'http://' + self.ip + ':5000'

def resource_url(entry_point, resource):
	return '/'.join([entry_point.base_url, resource])

def item_url(entry_point, resource, item):
	return '/'.join([entry_point.base_url, resource, item])

def post(entry_point, resource, item):
	url = resource_url(entry_point, resource)
	headers = {'Content-Type': 'application/json'}

	# If we try to format the request without converting the JSON to a
	# string first, the requests API will pass the parameters as part of
	# the URL. As a result, nested JSON will not get encoded correctly.
	return requests.post(url, headers=headers, data=json.dumps(item))

def patch(entry_point, resource, item, update):
	url = item_url(entry_point, resource, item)
	headers = {'Content-Type': 'application/json'}
	return requests.patch(url, headers=headers, data=json.dumps(update))

class TestTaskCreation(unittest.TestCase):
	def __init__(self, *args, **kwargs):
		self.db_conn = Connection()
		self.db = self.db_conn['banyan']
		self.entry_point = EntryPoint()

		self.post_fail_msg = "Unexpected response to POST request. Input: {}. Response: {}."
		self.patch_fail_msg = "Unexpected response to PATCH request to change '{}' from " \
			"'{}' to '{}'. Input: {}. Response: {}."
		super().__init__(*args, **kwargs)

	# Used to drop the 'tasks' collection so that each test is independent.
	def drop_tasks(self):
		self.db.drop_collection('tasks')

	def test_creation(self):
		pass
		#self._test_creation_without_continuations()
		#self._test_creation_with_continuations()

	def _test_creation_without_continuations(self):
		self.drop_tasks()

		ops = [
			(
				{'name': 'test 1'},
				requests.codes.created
			),
			(
				{'command': 'test'},
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
						'cores': 8
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
						'cores': 8,
						'gpus': [{
							'memory': '8 GiB',
							'min_compute_capability': '5.0'
						}]
					}
				},
				requests.codes.created
			)
		]

		for doc, expected_status in ops:
			resp = post(self.entry_point, 'tasks', doc)
			fail_msg = self.post_fail_msg.format(doc, resp.json())
			self.assertEqual(resp.status_code, expected_status, msg=fail_msg)

	# TODO for the test, use a task with no command and two continuations.
	# after the parent is put in the available state, check that both continuations
	# are run.
	# TODO check for failure if either of the continuations is active when added.
	def _test_creation_with_continuations(self):
		#drop_tasks()
		pass

	def test_updates(self):
		#self._test_command_updates()
		#self._test_state_updates()
		self._test_resource_updates()
		#self._test_continuation_updates()

	# TODO: test that making changes while the task is available fails
	# TODO: test that changing the command after the task was created with
	# the no command or requested resources fails.
	def _test_command_updates(self):
		#self.drop_tasks()
		pass

	def _test_state_updates(self):
		initial_states = ['inactive', 'available']
		terminal_states = ['inactive', 'available', 'running', 'pending_cancellation',
			'cancelled', 'terminated']

		for si, sf in product(initial_states, terminal_states):
			self.drop_tasks()

			task = {'name': 'test', 'state': si}
			resp = post(self.entry_point, 'tasks', task)
			resp_json = resp.json()
			fail_msg = self.post_fail_msg.format(task, resp_json)
			self.assertEqual(resp.status_code, requests.codes.created, msg=fail_msg)

			update = {'state': sf}
			resp = patch(self.entry_point, 'tasks', resp_json['_id'], update)
			fail_msg = self.patch_fail_msg.format('state', si, sf, update, resp.json())

			if sf in LEGAL_USER_STATE_TRANSITIONS[si]:
				self.assertEqual(resp.status_code,
					requests.codes.ok,
					msg=fail_msg)
			else:
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity,
					msg=fail_msg)

	def _test_resource_updates(self):
		"""
		Here, we verify that the behavior when attempting to change
		various fields of a task is as expected. In particular:
		1. Setting any field to its current value (e.g. a no-op) should
		   always work.
		2. While a task is in the `inactive` state, modifying any field
		   that is not marked `readonly` should work.
		3. If a task is not in the `inactive` state, then any attempt to
		   modify the value of a `readonly` or `createonly` field should
		   fail.
		"""

		states = ['inactive', 'available']

		changes = [
			(
				{'estimated_runtime': '10 minutes'},
				{'estimated_runtime': '20 minutes'}
			),
			(
				# The 'cores' field is already set to 1 by
				# default, so if we don't include it in the
				# PATCH request, we would essentially be asking
				# the server to delete it. This will result in
				# response of 422.
				{'requested_resources': {'memory': '1 GiB', 'cores': 1}},
				{'requested_resources': {'memory': '2 GiB', 'cores': 1}}
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
		for state, change in product(states, changes):
			self.drop_tasks()
			init, _ = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **dict(init, **{'state': state}))
			resp = post(self.entry_point, 'tasks', task)
			resp_json = resp.json()
			fail_msg = self.post_fail_msg.format(task, resp_json)
			self.assertEqual(resp.status_code, requests.codes.created, msg=fail_msg)
			
			resp = patch(self.entry_point, 'tasks', resp_json['_id'], init)
			key, value = next(iter(init.items()))
			fail_msg = self.patch_fail_msg.format(key, value, value, init, resp.json())
			self.assertEqual(resp.status_code, requests.codes.ok, msg=fail_msg)

		## Case (2).
		for change in changes:
			self.drop_tasks()
			init, final = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **init)
			resp = post(self.entry_point, 'tasks', task)
			resp_json = resp.json()
			fail_msg = self.post_fail_msg.format(task, resp_json)
			self.assertEqual(resp.status_code, requests.codes.created, msg=fail_msg)
			
			resp = patch(self.entry_point, 'tasks', resp_json['_id'], final)
			key, vi = next(iter(init.items()))
			vf = next(iter(final.values()))

			fail_msg = self.patch_fail_msg.format(key, vi, vf, final, resp.json())
			self.assertEqual(resp.status_code, requests.codes.ok, msg=fail_msg)

		# Case (3).
		for change in changes:
			self.drop_tasks()
			init, final = change

			# The RHS is the union of the arguments.
			task = dict(basic_task, **dict(init, **{'state': 'available'}))
			resp = post(self.entry_point, 'tasks', task)
			resp_json = resp.json()
			fail_msg = self.post_fail_msg.format(task, resp_json)
			self.assertEqual(resp.status_code, requests.codes.created, msg=fail_msg)
			
			resp = patch(self.entry_point, 'tasks', resp_json['_id'], final)
			key, vi = next(iter(init.items()))
			vf = next(iter(final.values()))

			fail_msg = self.patch_fail_msg.format(key, vi, vf, final, resp.json())
			self.assertEqual(resp.status_code, requests.codes.unprocessable_entity, \
				msg=fail_msg)

	# TODO same as continuation test for task creation, except now we
	# create the task with no continuations initially.
	def _test_continuation_updates(self):
		#self.drop_tasks()
		pass

if __name__ == '__main__':
	unittest.main()
