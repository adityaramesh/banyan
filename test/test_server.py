# -*- coding: utf-8 -*-

"""
Tests the server.
"""

import socket
import requests
import json
import unittest

from pymongo import Connection
from urllib.parse import urljoin

# Drop the banyan database so that the test is idempotent.
def drop_database():
	Connection().drop_database('banyan')

def get_ip():
	return socket.gethostbyname(socket.gethostname())

def post(resource, data):
	entry_point = 'http://' + get_ip() + ':5000'
	url = urljoin(entry_point, resource) if resource else entry_point
	headers = {'Content-Type': 'application/json'}

	# If we try to format the request without converting the JSON to a
	# string first, the requests API will pass the parameters as part of
	# the URL. As a result, nested JSON will not get encoded correctly.
	return requests.post(url, headers=headers, data=json.dumps(data))

class TestTaskCreation(unittest.TestCase):
	def test_creation_without_continuations(self):
		drop_database()

		tasks = [
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

		for doc, code in tasks:
			response = post('tasks', doc)
			message = "Input: {}. Response: {}.".format(doc, response.json())
			self.assertEqual(response.status_code, code, msg=message)

	# TODO: things like adding an active task as a continuation to another
	# should fail.
	def test_creation_with_continuations(self):
		#drop_database()
		pass

	# TODO: test changes to info of inactive tasks.
	def test_updates(self):
		#drop_database()
		pass

if __name__ == '__main__':
	unittest.main()
