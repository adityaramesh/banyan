from pymongo import Connection
from eve.io.mongo import Validator

class Validator(Validator):
	def __init__(self, schema=None, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		#self.db_conn = Connection()
		#self.db = self.db_conn['banyan']

		super().__init__(
			schema=schema,
			resource=resource,
			allow_unknown=allow_unknown,
			transparent_schema_rules=transparent_schema_rules
		)

	"""
	Called after each POST request, e.g. when a new task is created.
	"""
	def validate(self, document, schema=None, update=False, context=None):
		# See https://github.com/nicolaiarocci/eve/issues/796 for more
		# information about this.
		assert not update, "Expected 'validate_update' to be called for updates " \
			"instead of 'validate' with 'update=True'."

		if 'command' in document and 'requested_resources' not in document:
			self._error('command', "'command' should be provided iff " \
				"'requested_resources' is provided.")
			return False

		if 'state' in document and document['state'] not in ['inactive', 'available']:
			self._error('state', "Tasks can only be created in the 'inactive' and " \
				"'available' states.")
			return False

		return super().validate(document, schema, update, context)

	"""
	Called after each PATCH request, e.g. when a task is updated in some way.
	"""
	def validate_update(self, document, _id, original_document=None):
		has_command = 'command' in original_document or 'command' in document
		has_resources = 'requested_resources' in original_document or \
			'requested_resources' in document
		
		if has_command and not has_resources:
			self._error('command', "'command' should be provided iff " \
				"'requested_resources' is provided.")
			return False

		if 'state' in document:
			si = original_document['state']
			sf = document['state']

			if not (si == sf or sf == 'cancelled' or (si == 'inactive' and \
				sf == 'available')):

				self._error('state', "Illegal state transition from '{}' to '{}'.". \
					format(si, sf))
				return False

		# TODO disallow mutation of fields listed in README

		return super().validate_update(document, _id, original_document)
