# -*- coding: utf-8 -*-

"""
Sets up virtual resources based on the schema defined in `virtual_schema.py`.
"""

from werkzeug import exceptions
from flask import Blueprint, abort, jsonify, make_response, current_app as app

from eve.utils import *
from eve.validation import ValidationError
from eve.methods.common import *

from constants import *
from virtual_schema import virtual_resources
from validation import Validator

def validate_updates(updates, schema, valid_func=None):
	if not isinstance(updates, list):
		return updates, {'input': "Updates string must be a JSON array."}

	if len(updates) > max_update_list_length:
		return updates, {'input', "Updates array can have at most {} elements.". \
			format(max_update_list_length)}

	issues = {}
	virtual_resource_keys = ['targets', 'values']

	for i, update in enumerate(updates):
		if not isinstance(update, dict):
			issues['update {}'.format(i)] = "Array element is not a dict."
			continue

		cur_issues = []
		for key in virtual_resource_keys:
			if key not in update:
				cur_issues.append("Missing field '{}'.".format(key))

		invalid_keys = update.keys() - virtual_resource_keys
		if len(invalid_keys) != 0:
			cur_issues.append("Invalid keys '{}'.".format(invalid_keys))

		if len(cur_issues) > 0:
			issues['update {}'.format(i)] = str(cur_issues)

	if len(issues) > 0:
		return updates, issues

	validator = Validator(schema=schema, resource='tasks')
	revised_updates = []

	for i, update in enumerate(updates):
		# TODO: fill in default fields for the schema.
		# TODO: fill in default values for list elements, if specified.

		# This deserializes some values that require special handlers,
		# such as ObjectIds.
		revised_update = serialize(update, schema=schema)
		revised_updates.append(revised_update)

		def log_issue(msg):
			issues['update {}: validator errors'.format(i)] = msg

		if not validator.validate(revised_update):
			log_issue(str(validator.errors))
			continue

		if valid_func:
			valid_func(revised_update, log_issue)

	return revised_updates, issues

"""
Defines and returns a request handler for a virtual resource at the resource-level granularity.
Parameters:
- `parent_resource`: Name of the physical resource for which the virtual resource is based.
- `virtual_resource`: Name of the virtual resource.
- `schema`: Schema used to validate the payload.
- `update_func`: Function that updates the database after the payload is validated.
- `valid_func`: Performs additional validation of the payload after it is checked against the
  update schema.
"""
def make_resource_level_handler(parent_resource, virtual_resource, schema, update_func, \
	valid_func=None):

	def handler(payload):
		issues = {}
		
		try:
			updates, errors = validate_updates(payload, schema, valid_func)

			if not errors:
				"""
				Note: the following features supported by Eve are not implemented
				here, because I'm not using them for this project. See the comments
				prefixed by "XXX" for more information.
				- Document versioning
				- Storing media files
				- Oplog updates
				- Callbacks (both pre- and post-update callbacks are ignored) [1]
				- Informative response [2]

				[1]: Supporting callbacks here would also be very inefficient,
				because we would need to fetch documents for all parent and child
				tasks involved.

				[2]: For similar reasons, the response returned to the client merely
				contains the status code, along with any errors that occurred.
				Information about what was updated for each document is not
				provided.
				"""
		
				# XXX not implemented: late versioning (see patch.py in Eve).
				# XXX not implemented: storing media files (see patch.py in Eve).
				# XXX not implemented: resolving documnet version (see patch.py in
				# Eve).

				update_func(updates, app.data.driver.db)

				"""
				XXX not implemented: etags (see patch.py in Eve). etags are obtained
				by computing the SHA1 hash of the document, excluding fields that
				are in a specified list. See utils.py in Eve for details.
				"""

				# XXX not implemented: oplog update (see patch.py in Eve).
				# XXX not implemented: insert versioning documents (see patch.py in
				# Eve).
				# XXX not implemented: informative response.
			else:
				issues = errors
		except ValidationError as e:
			issues['validator exception'] = str(e)
		except exceptions.HTTPException as e:
			raise e
		except Exception as e:
			app.logger.exception(e)
			abort(400, description=debug_error_message("An exception occurred: {}". \
				format(e)))

		response = {}

		if len(issues) != 0:
			response[config.ISSUES] = issues
			response[config.STATUS] = config.STATUS_ERR
			status = config.VALIDATION_ERROR_STATUS
		else:
			response[config.STATUS] = config.STATUS_OK
			status = 200

		response = jsonify(response)
		response.status_code = status
		return response

	return handler

"""
Same as `make_resource_level_handler`, but for virtual resources that work at item-level
granularity.
"""
def make_item_level_handler(parent_resource, virtual_resource, schema, update_func, valid_func=None):
	handler = make_resource_level_handler(parent_resource, virtual_resource, schema, update_func,
		valid_func)

	def scaffold(target_id, values):
		assert isinstance(target_id, str)
		return handler([{'targets': [target_id], 'values': values}])

	return scaffold

blueprints = []

# XXX not implemented: rate limiting, authorization, pre-event (see patch.py in Eve).
def route(p_res, v_res, schema):
	update_schema = schema['schema']
	u_func = schema['update_func']
	v_func = schema.get('validate_func')

	schema['handlers'] = {}
	router = Blueprint(p_res + '/' + v_res, __name__)
	blueprints.append(router)

	if 'resource' in schema['granularity']:
		h1 = make_resource_level_handler(p_res, v_res, update_schema, u_func, v_func)
		schema['handlers']['resource_level'] = h1

		@router.route('/' + p_res + '/' + v_res, methods=['POST'])
		def route_resource_level():
			return h1(payload())

	if 'item' in schema['granularity']:
		h2 = make_item_level_handler(p_res, v_res, update_schema, u_func, v_func)
		schema['handlers']['item_level'] = h2

		"""
		We allow PATCH for item-level virtual resources, because one should be able to use
		them in PATCH requests that also involve other fields.
		"""
		@router.route('/' + p_res + '/<item_id>/' + v_res, methods=['POST', 'PATCH'])
		def route_item_level(item_id):
			return h2(item_id, payload())

for parent_res, virtuals in virtual_resources.items():
	for virtual_res, schema in virtuals.items():
		route(parent_res, virtual_res, schema)
