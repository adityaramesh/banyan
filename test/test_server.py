# -*- coding: utf-8 -*-

"""
Tests the server.
"""

from pymongo import Connection
import requests
import json
from urllib.parse import urljoin

# Drop the banyan database so that the test is idempotent.
def drop_database():
	Connection().drop_database('banyan')

def post(resource, data):
	entry_point = 'http://127.0.0.1:5000'
	url = urljoin(entry_point, resource) if resource else entry_point
	return requests.post(url, data=data)

def test_group_creation():
	groups = [
		{'name': 'group_1'},
		{},
		{'name': 'group_3', 'foo': 'bar'}
	]

	print("Testing group creation.")
	for doc in groups:
		print(post('groups', doc).json())

def test_job_creation():
	#'gpus': [{'memory': '8 Gb', 'min_compute_capability': '5.0'}]
	basic_job = {
		'command': 'ls',
		'requested_resources': {'memory': '64 Gb'}
	}

	jobs = [
		basic_job
	]

	print("Testing job creation.")
	for doc in jobs:
		print(post('jobs', doc).raw)

def test_schema():
	test_group_creation()
	test_job_creation()

if __name__ == '__main__':
	drop_database()
	test_schema()
