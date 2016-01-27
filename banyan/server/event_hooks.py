# -*- coding: utf-8 -*-

"""
Provides the event hooks that implement the server-side functionality not
falling under the purview of REST.
"""

import json

from bson import ObjectId
from base64 import b64decode
from flask import abort, current_app as app
from eve.utils import config
from eve.methods.patch import patch_internal

import continuations
from physical_schema import tasks
from validation import legal_user_state_transitions, legal_worker_state_transitions
from virtual_resources import virtual_resources

class EventHooks:
	def __init__(self):
		self.db = app.data.driver.db
		app.on_insert_tasks    += self.terminate_empty_tasks
		app.on_inserted_tasks  += self.acquire_continuations
		app.on_pre_PATCH_tasks += self.handle_virtual_resources

		# Set up the handlers for the virtual resources defined in `virtual_schema.py`.
		self.item_level_virtual_resources = set()
		for parent_res, virtuals in virtual_resources.items():
			for virtual_res, schema in virtuals.items():
				if 'item' in schema['granularity']:
					self.item_level_virtual_resources.add(virtual_res)

	def terminate_empty_tasks(self, items):
		for item in items:
			if 'command' not in item and item['state'] == 'available':
				item['state'] = 'terminated'

	def acquire_continuations(self, items):
		for item in items:
			if item['state'] == 'terminated':
				assert 'command' not in item, "This branch should be entered iff " \
					"the user creates a task with no command directly in the " \
					"'available' state."

				for cont_id in item['continuations']:
					continuations.try_make_available(cont_id, self.db)
			else:
				for cont_id in item['continuations']:
					continuations.acquire(cont_id, self.db)

	def handle_virtual_resources(self, request, lookup):
		self.authenticate_task_patch(request, lookup)
		update = request.json

		"""
		XXX: I'm probably abusing Flask's `abort` function to hack this pre-request hook
		into performing all of the work. But I can't think of a better way to do this.
		"""
		for key, value in update.items():
			if key in self.item_level_virtual_resources:
				handler = virtual_resources['tasks'][key]['handlers']['item_level']
				response = handler(lookup[config.ID_FIELD], value)
				if response.status_code != 200:
					abort(response.status_code, response.get_data())

		"""
		Remove the virtual resources from the request data, so that Eve doesn't error out
		later.
		"""
		for key in self.item_level_virtual_resources:
			update.pop(key, None)

	def authenticate_task_patch(self, request, lookup):
		def auth_failed(msg):
			abort(401, description=msg)

		auth = request.headers.get('Authorization')
		try:
			token = b64decode(auth.split()[1].encode()).decode('utf-8')[:-1]
		except:
			auth_failed("Please provide proper authentication credentials.")

		"""
		The authenticator should have been run before this callback was invoked, so the
		token should always be valid.
		"""
		role = self.db.users.find_one({'token': token}, {'role': True})['role']

		"""
		If the lookup is invalid, let Eve issue the error message.
		"""

		revised_lookup = dict(lookup)
		revised_lookup[config.ID_FIELD] = ObjectId(revised_lookup[config.ID_FIELD])

		task = self.db.tasks.find_one(revised_lookup)
		if not task:
			return

		if not request.json:
			abort(400, description="Request has invalid content type.")

		if 'state' in request.json:
			si, sf = task['state'], request.json['state']
			legal_trans = legal_user_state_transitions if role == 'user' else \
				legal_worker_state_transitions
			if sf not in legal_trans[si]:
				auth_failed("{} cannot make change state from '{}' to '{}'.". \
					format(role, si, sf))

		if 'add_history' in request.json and role != 'worker':
			auth_failed("Only workers can use 'add_history'.")
