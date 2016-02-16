# -*- coding: utf-8 -*-

"""
banyan.common
-------------

Definitions used by several Banyan modules.
"""

import json
import socket
import requests
import unittest

from banyan.settings import banyan_port

class EntryPoint:
	def __init__(self):
		self.ip = socket.gethostbyname(socket.gethostname())
		self.base_url = 'http://' + self.ip + ':' + str(banyan_port)

def make_url(entry_point, resource, item=None, virtual_subresource=None):
	if item is None:
		return '/'.join([entry_point.base_url, resource])
	if virtual_subresource is None:
		return '/'.join([entry_point.base_url, resource, item])
	return '/'.join([entry_point.base_url, resource, item, virtual_subresource])

def get(entry_point, key, resource, item=None, **kwargs):
	url = make_url(entry_point, resource, item)
	url += ''.join(['?' + k + '=' + json.dumps(v) for k, v in kwargs.items()])

	headers = {'Content-Type': 'application/json'}
	if key:
		headers['Authorization'] = 'Basic ' + key

	return requests.get(url, headers=headers)

def post(doc, entry_point, key, resource, item=None, virtual_subresource=None):
	url = make_url(entry_point, resource, item, virtual_subresource)
	headers = {'Content-Type': 'application/json'}
	if key:
		headers['Authorization'] = 'Basic ' + key

	# If we try to format the request without converting the JSON to a
	# string first, the requests API will pass the parameters as part of
	# the URL. As a result, nested JSON will not get encoded correctly.
	return requests.post(url, headers=headers, data=json.dumps(doc))

def patch(update, entry_point, key, resource, item):
	url = make_url(entry_point, resource, item)
	headers = {'Content-Type': 'application/json'}
	if key:
		headers['Authorization'] = 'Basic ' + key

	return requests.patch(url, headers=headers, data=json.dumps(update))

def make_suite(testcase_klass, *args, **kwargs):
	"""
	Adapted from Eli Bendersky's blog post here_.

	.. _here:
	http://eli.thegreenplace.net/2011/08/02/python-unit-testing-parametrized-test-cases
	"""

	testloader = unittest.TestLoader()
	testnames = testloader.getTestCaseNames(testcase_klass)
	suite = unittest.TestSuite()

	for name in testnames:
		suite.addTest(testcase_klass(methodName=name, *args, **kwargs))
	return suite
