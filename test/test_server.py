# -*- coding: utf-8 -*-

"""
Tests the server.
"""

import socket
import requests
import json
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

def test_group_creation():
	groups = [
		{'name': 'group_1'},
		{},
		{'name': 'group_3', 'foo': 'bar'}
	]

	codes = [
		requests.codes.created,
		requests.codes.unprocessable_entity,
		requests.codes.unprocessable_entity
	]

	print("Testing group creation.")
	for doc, code in zip(groups, codes):
		assert post('groups', doc).status_code == code

def test_job_creation():
	jobs = [
		{
			'command': 'ls',
			'requested_resources': {
				'memory': '64 GiB'
			}
		},
		{
			'command': 'ls',
			'requested_resources': {
				'memory': '64 GiB',
				'cores': 8
			}
		},
		{
			'command': 'ls',
			'requested_resources': {
				'memory': '64 GiB',
				'cores': 8,
				'gpus': [{
					'memory': '8 GiB',
					'min_compute_capability': '5.0'
				}]
			}
		}
	]

	codes = [
		requests.codes.created,
		requests.codes.created,
		requests.codes.created
	]

	print("Testing job creation.")
	for doc, code in zip(jobs, codes):
		assert post('jobs', doc).status_code == code

def test_schema():
	test_group_creation()
	test_job_creation()

if __name__ == '__main__':
	drop_database()
	test_schema()
