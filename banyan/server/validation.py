from eve.io.mongo import Validator

class Validator(Validator):
	def __init__(self, schema=None, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		super().__init__(
			schema=schema,
			resource=resource,
			allow_unknown=allow_unknown,
			transparent_schema_rules=transparent_schema_rules
		)

	def validate(self, document, schema=None, update=False, context=None):
		if (not update and not self.check_creation_constraints(document)) or \
		   (update and not self.check_update_constraints(document)):
			return False

		return super().validate(document, schema, update, context)

	"""
	Checks constaints that should hold when a task is created.
	"""
	def check_creation_constraints(self, document):
		if bool('command' in document) != bool('requested_resources' in document):
			self._error('command', "'command' should be provided iff " \
				"'requested_resources' is provided.")
			return False

		if 'state' in document and document['state'] not in ['inactive', 'available']:
			self._error("Tasks can only be created in the 'inactive' and 'available'" \
				"states.")
			return False

		# TODO implement acquire/release for continuations
		# TODO validate continuations

		return True

	"""
	Checks constraints that should hold when a task is updated.
	"""
	def check_update_constraints(self, document):
		# XXX we need to modify the code below so that we check if
		# 'command' is already defined for the document
		# 
		#if 'command' in document and 'requested_resources' not in document:
		#	self._error('command', "'requested_resources' must be provided if " \
		#		"'command' is provided.")
		#	return False

		# TODO disallow illegal state transitions
		# TODO disallow mutation of fields listed in README
		return True
