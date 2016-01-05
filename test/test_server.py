# -*- coding: utf-8 -*-

"""
Tests the server.
"""

import socket
import requests
import json
import unittest

from itertools import product
from pymongo import Connection

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
		super().__init__(*args, **kwargs)

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
			response = post(self.entry_point, 'tasks', doc)
			message = "Input: {}. Response: {}.".format(doc, response.json())
			self.assertEqual(response.status_code, expected_status, msg=message)

	# TODO for the test, use a task with no command and two continuations.
	# after the parent is put in the available state, check that both continuations
	# are run.
	# TODO check for failure if either of the continuations is active when added.
	def _test_creation_with_continuations(self):
		#drop_tasks()
		pass

	def test_updates(self):
		self._test_command_updates()
		self._test_state_updates()
		self._test_resource_updates()
		self._test_continuation_updates()

	# TODO: test that making changes while the task is available fails
	# TODO: test that changing the command after the task was created with
	# the no command or requested resources fails.
	def _test_command_updates(self):
		#self.drop_tasks()
		pass

	def _test_state_updates(self):
		post_msg = "Unexpected response to POST request. Input: {}. Response: {}."
		patch_msg = "Unexpected result when changing state from '{}' to '{}'. Input: {}. " \
			"Response: {}."

		initial_states = ['inactive', 'available']
		terminal_states = ['inactive', 'available', 'running', 'pending_cancellation',
			'cancelled', 'terminated']

		for si, sf in product(initial_states, terminal_states):
			self.drop_tasks()

			task = {'name': 'test'}
			resp = post(self.entry_point, 'tasks', task)
			resp_json = resp.json()
			fail_msg = post_msg.format(task, resp_json)
			self.assertEqual(resp.status_code, requests.codes.created, msg=fail_msg)

			update = {'state': sf}
			resp = patch(self.entry_point, 'tasks', resp_json['_id'], update)
			resp_json = resp.json()
			fail_msg = patch_msg.format(si, sf, update, resp_json)

			if si == sf or sf == 'cancelled' or (si == 'inactive' and sf == 'available'):
				self.assertEqual(resp.status_code,
					requests.codes.ok,
					msg=fail_msg)
			else:
				self.assertEqual(resp.status_code,
					requests.codes.unprocessable_entity,
					msg=fail_msg)

	# TODO check that updates to the fields listed in the readme when the
	# task is in the `available` state fail.
	def _test_resource_updates(self):
		#self.drop_tasks()
		pass

	# TODO same as continuation test for task creation, except now we
	# create the task with no continuations initially.
	def _test_continuation_updates(self):
		#self.drop_tasks()
		pass

if __name__ == '__main__':
	unittest.main()
