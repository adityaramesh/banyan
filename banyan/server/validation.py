# -*- coding: utf-8 -*-

"""
Validator with additional constraints that are not covered by Eve.
"""

from flask import current_app as app
from eve.io.mongo import Validator

"""
See `notes/specification.md` for more information about state transitions.
"""

legal_user_state_transitions = {
	'inactive':             ['cancelled', 'available'],

	# Note: when a user attempts to change the state of a task to `cancelled`, the server first
	# puts the task in the `pending_cancellation` state, and then goes through the procedures
	# described in the specification.
	'available':            ['cancelled'],
	'running':              ['cancelled'],

	'pending_cancellation': [],
	'cancelled':            [],
	'terminated':           []
}

legal_worker_state_transitions = {
	'inactive':             [],
	'available':            ['running'],
	'running':              ['terminated'],
	'pending_cancellation': ['cancelled', 'terminated'],
	'cancelled':            [],
	'terminated':           []
}

"""
Note: this dictionary is **not** the union of the two dictionaries above. The dictionaries above
describe the transitions that an API user is allowed to make. But a state transition requested by a
user may not necessarily result in the same transition actually being made by the server. For
example, when the user cancels a task while it is running, the task is actually put in the
'pending_cancellation' state.

The dictionary below describes the permissible transitions that the *server* is allowed to make. By
the time the validator is applied to an update, the state transition requested by the user is
converted into the actual transition that the server must make (see `event_hooks.py` for details).
This dictionary is used to verify transitions of the latter kind, i.e. the transitions that are
actually applied to the documents in the database.
"""
legal_state_transitions = {
	'inactive':             ['cancelled', 'available'],
	'available':            ['cancelled', 'running'],
	'running':              ['pending_cancellation', 'terminated'],
	'pending_cancellation': ['cancelled', 'terminated'],
	'cancelled':            [],
	'terminated':           []
}

class Validator(Validator):
	def __init__(self, schema=None, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		self.db = app.data.driver.db

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
			children = [self.db['tasks'].find_one({'_id': _id}) for _id in \
				document['continuations']]

			# It's not practical to check for cyclic dependencies,
			# but we do perform a basic sanity check.
			if '_id' in document:
				if document['_id'] in children:
					self._error('continuations', "Task cannot have itself " \
						"as a continuation.")
					return False

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

			if sf not in legal_state_transitions[si]:
				self._error('state', "Illegal state transition from '{}' to '{}'.". \
					format(si, sf))
				return False

		# We call the parent's `validate_update` function now, so that
		# we can ensure that all ObjectIds for continuations are valid.
		if not super().validate_update(document, _id, original_document):
			return False

		return self.validate_continuations(document)

	"""
	Extends the 'empty' rule so that it can also be applied to lists. Taken
	from Nicola Iarocci's answer [here](http://stackoverflow.com/a/23708110).
	"""
	def _validate_empty(self, empty, field, value):
		super()._validate_empty(empty, field, value)

		if isinstance(field, list) and not empty and len(value) == 0:
			self._error(field, "list cannot be empty")

	def _validate_allows_duplicates(self, allows_duplicates, field, value):
		if not isinstance(value, list):
			self._error(field, "Value must be a list.")
			return False

		if not allows_duplicates and len(set(value)) != len(value):
			self._error(field, "Field contains duplicates.")
			return False

		return True

	"""
	In the schema defined in `settings.py`, a field that is marked `createonly_iff_inactive` may
	only be initialized if no value is already associated with it for the given document.
	"""
	def _validate_createonly(self, createonly, field, value):
		if not createonly or not self._original_document:
			return True

		if field in self._original_document:
			self._error(field, "Cannot modify field '{}' once it has been set.". \
				format(field))
			return False

		return True

	"""
	Like `createonly`, but with the additional restriction that the task must also be in the
	`inactive` state in order for the field to be set.
	"""
	def _validate_creatable_iff_inactive(self, createonly, field, value):
		if not createonly or not self._original_document:
			return True

		if self._original_document['state'] != 'inactive':
			self._error(field, "Cannot set field '{}' when task is no longer in " \
				"'inactive' state.".format(field))
			return False
		
		return self._validate_createonly(createonly, field, value)

	"""
	In the schema defined in `settings.py`, a field that is marked
	`mutable_iff_inactive` may only be changed while the task is still in
	the `inactive` state. This function enforces this.
	"""
	def _validate_mutable_iff_inactive(self, mutable, field, value):
		if not mutable or not self._original_document or \
			self._original_document['state'] == 'inactive':
			return True

		if field in self._original_document and value != self._original_document[field]:
			self._error(field, "Cannot change value of field '{}' when task is no " \
				"longer in 'inactive' state.".format(field))
			return False

		return True
