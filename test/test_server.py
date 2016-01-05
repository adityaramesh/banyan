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
		self.base_url = 'http://' + get_ip() + ':5000'

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
	def __init__(self):
		self.db_conn = Connection()
		self.entry_point = EntryPoint()

	# Drop the banyan database so that each test is idempotent.
	def drop_database():
		self.db_conn.drop_database('banyan')

	def test_creation_without_continuations(self):
		self.drop_database()

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
	def test_creation_with_continuations(self):
		#drop_database()
		pass

	def test_updates(self):
		test_command_updates()
		test_state_updates()
		test_resource_updates()
		test_continuation_updates()

	# TODO: test that making changes while the task is available fails
	# TODO: test that changing the command after the task was created with
	# the no command or requested resources fails.
	def test_command_updates():
		#self.drop_database()
		pass

	# TODO: test that for a task with no command, the state change inactive
	# -> available results in the task immediately being put in the
	# terminated state. Don't make tests involving nonempty commands; this
	# involves the client.
	def test_state_updates():
		template = "Option: {}. Input: {}. Response: {}."
		initial_states = ['inactive', 'available']
		terminal_states = ['inactive', 'available', 'running', 'pending_cancellation',
			'cancelled', 'terminated']

		for si, sf in product(initial_states, terminal_states):
			self.drop_database()

			task = {'name': 'test'}
			resp_1 = post('tasks', doc_1)
			json_1 = resp_1.json()
			msg_1 = template.format('post', task, json_1)
			print(json_1)
			#self.assertEqual(resp_1.status_code, requests.codes.created, msg=msg_1)

			update = {'status': sf}
			resp_2 = patch('tasks/{}'.format(json_1['_id']), update)
			msg_2 = template.format('patch', update, resp_2.json())
			print(resp_2.json())
			# TODO some assertion about the state obtained from the response

	# TODO check that updates to the fields listed in the readme when the
	# task is in the `available` state fail.
	def test_resource_updates():
		#self.drop_database()
		pass

	# TODO same as continuation test for task creation, except now we
	# create the task with no continuations initially.
	def test_continuation_updates():
		#self.drop_database()
		pass

if __name__ == '__main__':
	unittest.main()
