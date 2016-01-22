# -*- coding: utf-8 -*-

"""
Provides the event hooks that implement the server-side functionality not
falling under the purview of REST.
"""

import continuations
from flask import current_app as app

class EventHooks:
	def __init__(self):
		self.db = app.data.driver.db
		app.on_insert_tasks   += self.task_insert
		app.on_inserted_tasks += self.task_inserted

	def task_insert(self, items):
		"""
		Tasks with no command are handled completely by the server. The
		`task_inserted` function takes care of calling `acquire`.
		"""

		for item in items:
			if 'command' not in item and item['state'] == 'available':
				item['state'] = 'terminated'

	def task_inserted(self, items):
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
