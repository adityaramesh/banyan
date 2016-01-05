from eve.io.mongo import Validator

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

		if 'command' in document and 'requested_resources' not in document:
			self._error('command', "'requested_resources' should be provided if " \
				"'command' is provided.")
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
		has_resources = ('requested_resources' in original_document and \
			'memory' in original_document['requested_resources']) or \
			'requested_resources' in document
		
		if has_command and not has_resources:
			self._error('command', "'requested_resources' should be provided if "
				"'command' is provided.")
			return False

		if 'state' in document:
			si = original_document['state']
			sf = document['state']

			# TODO: incorporate legal_worker_transitions once
			# workers can be authenticated.
			if sf not in LEGAL_USER_STATE_TRANSITIONS[si]:
				self._error('state', "Illegal state transition from '{}' to '{}'.". \
					format(si, sf))
				return False

		return super().validate_update(document, _id, original_document)

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
