# -*- coding: utf-8 -*-

"""
Starts a server that maintains a shared job queue.
"""

import os
import sys
import socket
from eve import Eve
from eve.io.mongo import Validator

def get_ip():
	return socket.gethostbyname(socket.gethostname())

class TaskValidator(Validator):
	def __init__(self, schema=None, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		super().__init__(
			schema=schema,
			resource=resource,
			allow_unknown=allow_unknown,
			transparent_schema_rules=transparent_schema_rules
		)

	def validate(self, document, schema=None, update=False, context=None):
		if not update and not self.validate_new_task(document):
			return False
		elif not self.validate_task_update(document):
			return False
		return super().validate(document, schema, update, context)

	def validate_new_task(self, document):
		if 'state' in document and document['state'] not in ['inactive', 'available']:
			self._error("Tasks can only be created in the " \
				"'inactive' and 'available' states.")
			return False

		if 'command' in document and not 'requested_resources' in document:
			self._error('command', "'requested_resources' must " \
				"be provided if 'command' is provided.")
			return False

		# TODO refactor this into another file
		# TODO implement acquire/release for continuations
		# TODO validate continuations

		return True

	def validate_task_update(self, document):
		# TODO disallow illegal state transitions
		# TODO disallow mutation of fields listed in README
		return True

if __name__ == '__main__':
	app = Eve(validator=TaskValidator)
	app.run(host=get_ip(), port=5000)
