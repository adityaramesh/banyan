# -*- coding: utf-8 -*-

"""
banyan.server.validation
------------------------

Defines custom validators for resource schema.
"""

from flask import g, current_app as app
from eve.methods.common import serialize
import eve.io.mongo

from banyan.server.state import legal_provider_transitions, legal_worker_transitions
from banyan.server.constants import *

class ValidatorBase(eve.io.mongo.Validator):
	"""
	Subclass of ``eve.io.mongo.Validator`` with support for the custom validation rules used by
	Banyan. This validator should not be used directly, because it does not support virtual
	resources. Use ``Validator`` instead.

	Support for virtual resources can't be added here, because ``BulkUpdateValidator`` derives
	from this class.
	"""

	def __init__(self, schema, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		"""
		The last two arguments are retained despite the fact that they are unused, in order
		to maintain compatibility with Eve's validator interface.
		"""

		self.db = app.data.driver.db

		"""
		``transparent_schema_rules`` is set to ``True``, so that the additional rules for
		virtual resources will not cause any issues.
		"""
		super().__init__(
			schema=schema,
			resource=resource,
			allow_unknown=False,
			transparent_schema_rules=True
		)

		"""
		This is a hack that is necessary in order to get the base class to pass the
		``resource`` parameter to the constructors of the validators for nested schema and
		virtual resources.
		"""
		self._Validator__config['resource'] = self.resource

	def validate(self, document, schema=None, update=False, context=None):
		"""
		Called after each POST request, e.g. when a new task is created. Also called each
		time a subfield needs to be validated. In this case, ``context`` will be set to the
		parent field's value, and ``update`` may be `True`.
		"""

		# We don't have any special constraints to enforce for subfields.
		if context:
			return super().validate(document, schema, update, context)

		# See https://github.com/nicolaiarocci/eve/issues/796 for more
		# information about this.
		assert not update, "Expected 'validate_update' to be called for updates " \
			"instead of 'validate' with 'update=True'."

		if 'state' in document and document['state'] not in ['inactive', 'available']:
			self._error('state', "Tasks can only be created in the 'inactive' and "
				"'available' states.")
			return False

		# We call the parent's `validate` function now, so that we can
		# ensure that all ObjectIDs for continuations are valid.
		if not super().validate(document, schema, update, context):
			return False

		return self.validate_continuations(document)

	def validate_continuations(self, document):
		if 'continuations' in document:
			children = [self.db['tasks'].find_one({'_id': _id}) for _id in
				document['continuations']]

			# It's not practical to check for cyclic dependencies,
			# but we do perform a basic sanity check.
			if '_id' in document:
				if document['_id'] in children:
					self._error('continuations', "Task cannot have itself as a "
						"continuation.")
					return False

			for child in children:
				if not self.validate_continuation(child):
					return False
		return True

	def validate_continuation(self, child):
		state = child['state']

		if state != 'inactive':
			self._error('continuations', "Continuation '{}' should be 'inactive', but "
				"is in the '{}' state.".format(child['_id'], state))
			return False

		return True

	def validate_state_change(self, final_state, update, required_fields):
		def fail():
			self._error('state', "State cannot be changed to '{}' without setting "
				"fields '{}' using 'update_execution_data'.".format(final_state,
				required_fields))
			return False

		if 'update_execution_data' not in update:
			return fail()

		updated_fields = set(update['update_execution_data'].keys())
		if len(updated_fields & required_fields) != len(required_fields):
			return fail()

		return True

	def validate_update(self, document, _id, original_document=None):
		"""
		Called after each PATCH request, e.g. when a task is updated in some way.
		"""

		# The authorization token and corresponding user are set by the authenticator.
		assert g.user is not None
		role = g.user['role']

		if 'state' in document:
			si = original_document['state']
			sf = document['state']

			legal_trans = legal_provider_transitions if role == 'provider' else \
				legal_worker_transitions

			if sf not in legal_trans[si]:
				self._error('state', "User with role '{}' is not authorized to make "
					"state transition from '{}' to '{}'.".format(role, si, sf))
				return False

			if sf == 'running':
				if not self.validate_state_change(sf, document,
						required_fields={'worker'}):
					return False
			elif sf == 'terminated' or (sf == 'cancelled' and role == 'worker'):
				if not self.validate_state_change(sf, document,
						required_fields={'exit_status', 'time_terminated'}):
					return False
		elif 'update_execution_data' in document:
			keys = set(document['update_execution_data'].keys())
			special_keys = {'worker', 'exit_status', 'time_terminated'}
			common_keys = keys & special_keys

			if len(common_keys) != 0:
				self._error('update_execution_data', "The fields {} cannot be "
					"changed independently of the task state.".format(
					common_keys))
				return False

		"""
		We call the parent's `validate_update` function now, so that we can ensure that all
		ObjectIds for continuations are valid.
		"""
		if not super().validate_update(document, _id, original_document):
			return False

		return self.validate_continuations(document)

	def _validate_empty(self, empty, field, value):
		"""
		Extends the 'empty' rule so that it can also be applied to lists. Taken from Nicola
		Iarocci's answer here_.

		.. _here: http://stackoverflow.com/a/23708110
		"""

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

	def _validate_createonly(self, createonly, field, value):
		"""
		A field that is marked ``createonly`` may only be initialized if no value is already
		associated with it for the given document.
		"""

		if not createonly or not self._original_document:
			return True

		if field in self._original_document:
			self._error(field, "Cannot modify field '{}' once it has been set.".
				format(field))
			return False

		return True

	def _validate_creatable_iff_inactive(self, createonly, field, value):
		"""
		Like ``createonly``, but with the additional restriction that the task must also be
		in the ``inactive`` state in order for the field to be set.
		"""

		if not createonly or not self._original_document:
			return True

		if self._original_document['state'] != 'inactive':
			self._error(field, "Cannot set field '{}' when task is no longer in "
				"'inactive' state.".format(field))
			return False

		return self._validate_createonly(createonly, field, value)

	def _validate_mutable_iff_inactive(self, mutable, field, value):
		"""
		Like ``creatable_iff_inactive``, but allows mutation instead of only initialization.
		"""

		if not mutable or not self._original_document or \
			self._original_document['state'] == 'inactive':
			return True

		if field in self._original_document and value != self._original_document[field]:
			self._error(field, "Cannot change value of field '{}' when task is no "
				"longer in 'inactive' state.".format(field))
			return False

		return True

class BulkUpdateValidator(ValidatorBase):
	"""
	A validator specialized for validating virtual resources.
	"""

	def __init__(self, schema, resource=None, allow_unknown=False,
		transparent_schema_rules=False):

		"""
		The last two arguments are retained despite the fact that they are unused, in order
		to maintain compatibility with Eve's validator interface.
		"""

		super().__init__(schema, resource)

	def validate_update_format(self, updates):
		"""
		Ensures that the JSON array of updates is in the correct format, without validating
		the content of any update. This function is factored out of ``validate_update`` so
		that derived classes can perform intermedidate validation before calling
		``validate_update_content``.
		"""

		if not isinstance(updates, list):
			self._error('updates', "Updates string must be a JSON array.")
			return False

		if len(updates) > max_update_list_length:
			self._error('updates', "Updates list can have at most {} elements.".
				format(max_update_list_length))
			return False

		virtual_resource_keys = ['targets', 'values']

		for i, update in enumerate(updates):
			if not isinstance(update, dict):
				self._error('update {}'.format(i), "Array element is not a dict.")
				continue

			cur_issues = []
			for key in virtual_resource_keys:
				if key not in update:
					cur_issues.append("Missing field '{}'.".format(key))

			invalid_keys = update.keys() - virtual_resource_keys
			if len(invalid_keys) != 0:
				cur_issues.append("Invalid keys '{}'.".format(invalid_keys))

			targets, values = update['targets'], update['values']
			if not isinstance(targets, list):
				cur_issues.append("'targets' field must be a list.")
			if not isinstance(values, list) and not isinstance(values, dict):
				cur_issues.append("'values' field must be a list or a dict.")

			if len(cur_issues) > 0:
				self._error('update {}'.format(i), str(cur_issues))

		if len(self._errors) != 0:
			return False

		for i, update in enumerate(updates):
			# TODO: fill in default fields for the schema.
			# TODO: fill in default values for list elements, if specified.

			"""
			This deserializes some values that require special handlers, such as
			ObjectIds and datetime objects. If this becomes a bottleneck, then write a
			custom function that only modifies the fields that are needed.
			"""
			updates[i] = serialize(update, schema=self.schema)

		return True

	def validate_update_content(self, updates, original_ids=None, original_documents=None):
		assert (original_ids and original_documents) or \
			(not original_ids) and (not original_documents)

		for i, update in enumerate(updates):
			if original_ids:
				"""
				To process rules like ``createonly``, we need the previous values of
				the fields.
				"""
				super().validate_update(updates[i], original_ids[i],
					original_documents[i])
			else:
				super().validate(updates[i])

		return len(self._errors) == 0

	def validate_update(self, updates, original_ids=None, original_documents=None):
		"""
		All requests made to virtual resources are considered to be updates, since according
		to our design, virtual resources can only be used to modify fields, not update them.

		The fields ``original_ids`` and ``original_documents`` only need to be provided if
		the documents being altered by the updates have validation rules that require
		knowledge of the previous values of fields (e.g. ``createonly``).

		Args:
			updates: The parsed ``dict`` of updates.
			original_ids: An array of the ids corresponding to the documents in
				``original_documents`` (optional).
			original_documents: An array of the original documents corresponding to the
				IDs in ``updates['targets']`` (optional).
		"""

		if not self.validate_update_format(updates):
			return False
		return self.validate_update_content(updates, original_ids, original_documents)

class Validator(ValidatorBase):
	"""
	Adds support for virtual resources to ``ValidatorBase``.
	"""

	def __init__(self, schema, resource, allow_unknown=False, transparent_schema_rules=False):
		"""
		The last two arguments are retained despite the fact that they are unused, in order
		to maintain compatibility with Eve's validator interface.
		"""

		self.db = app.data.driver.db
		self.virtual_validators = {}

		# We use a local import here to avoid cyclic dependencies.
		from schema import virtual_resources

		for parent_res, virtuals in virtual_resources.items():
			if parent_res != resource:
				continue

			for virtual_res, v_schema in virtuals.items():
				if 'validator' not in v_schema:
					validator = BulkUpdateValidator
				else:
					validator = v_schema['validator']

				self.virtual_validators[virtual_res] = validator(
					schema=v_schema['schema'], resource=resource)

		super().__init__(schema, resource)

	def _validate_virtual_resource(self, virtual_resource, field, value):
		if not virtual_resource:
			return True

		assert self._id is not None
		assert isinstance(value, list) or isinstance(value, dict)

		dummy = [{'targets': [self._id], 'values': value}]
		validator = self.virtual_validators[field]

		if not validator.validate_update(dummy):
			for k, v in validator.errors.items():
				self._error(k, v)
			return False

		return True
