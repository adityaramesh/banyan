from eve.io.mongo import Validator
from pymongo import MongoClient
from bson import ObjectId

"""
See `notes/specification.md` for more information about state transitions.
"""

LEGAL_USER_STATE_TRANSITIONS = {
	'inactive': ['inactive', 'available', 'cancelled'],
	'available': ['available', 'cancelled'],
	'running': ['running', 'cancelled'],
	'pending_cancellation': ['pending_cancellation'],
	'cancelled': ['cancelled'],
	'terminated': ['terminated']
}

LEGAL_WORKER_STATE_TRANSITIONS = {
	'inactive': ['inactive'],
	'available': ['available', 'running'],
	'running': ['running', 'cancelled', 'terminated'],
	'pending_cancellation': ['pending_cancellation', 'cancelled', 'terminated'],
	'cancelled': ['cancelled'],
	'terminated': ['terminated']
}

class Validator(Validator):
	def __init__(self, schema=None, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		self.db_client = MongoClient()
		self.db = self.db_client['banyan']

		super().__init__(
			schema=schema,
			resource=resource,
			allow_unknown=allow_unknown,
			transparent_schema_rules=transparent_schema_rules
		)

	"""
	Called after each POST request, e.g. when a new task is created. Also
	called each time a subfield needs to be validated. In this case,
	`context` will be set to the parent field's value, and `update` may be
	`True`.
	"""
	def validate(self, document, schema=None, update=False, context=None):
		# We don't have any special constraints to enforce for subfields.
		if context:
			return super().validate(document, schema, update, context)

		# See https://github.com/nicolaiarocci/eve/issues/796 for more
		# information about this.
		assert not update, "Expected 'validate_update' to be called for updates " \
			"instead of 'validate' with 'update=True'."

		if 'state' in document and document['state'] not in ['inactive', 'available']:
			self._error('state', "Tasks can only be created in the 'inactive' and " \
				"'available' states.")
			return False

		# We call the parent's `validate` function now, so that we can
		# ensure that all ObjectIDs for continuations are valid.
		if not super().validate(document, schema, update, context):
			return False

		return self.validate_continuations(document)

	def validate_continuations(self, document):
		if 'continuations' in document:
			children = [self.db['tasks'].find_one({'_id': ObjectId(cont_id)}) for \
				cont_id in document['continuations']]
			for child in children:
				if not self.validate_continuation(child):
					return False
		return True

	def validate_continuation(self, child):
		state = child['state']

		if state != 'inactive':
			self._error('continuations', "Continuation '{}' should be 'inactive', but " \
				"is in the '{}' state.".format(child['_id'], state))
			return False

		return True

	"""
	Called after each PATCH request, e.g. when a task is updated in some way.
	"""
	def validate_update(self, document, _id, original_document=None):
		if 'state' in document:
			si = original_document['state']
			sf = document['state']

			# TODO: incorporate legal_worker_transitions once
			# workers can be authenticated. but test this later in
			# test_worker.py.
			if sf not in LEGAL_USER_STATE_TRANSITIONS[si]:
				self._error('state', "Illegal state transition from '{}' to '{}'.". \
					format(si, sf))
				return False

		# We call the parent's `validate_update` function now, so that
		# we can ensure that all ObjectIDs for continuations are valid.
		if not super().validate_update(document, _id, original_document):
			return False

		return self.validate_continuations(document)

	"""
	In the schema defined in `settings.py`, a field that is marked
	`createonly` may only be changed while the task is still in the
	`inactive` state. This function is used to enforce this.
	"""
	def _validate_createonly(self, createonly, field, value):
		if not createonly or not self._original_document or \
			self._original_document['state'] == 'inactive':
			return True

		if field in self._original_document and value != self._original_document[field]:
			self._error(field, "Cannot change value of field '{}' when task is no " \
				"longer in 'inactive' state.".format(field))
			return False

		return True
