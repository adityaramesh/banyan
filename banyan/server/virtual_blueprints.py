# -*- coding: utf-8 -*-

"""
banyan.server.virtual_blueprints
--------------------------------

Creates Flask Blueprints for the virtual resources based on the schema defined in ``schema.py``.
"""

from werkzeug import exceptions
from flask import Blueprint, abort, jsonify, request, current_app as app
from eve.auth import resource_auth
from eve.utils import config, debug_error_message
from eve.validation import ValidationError
from eve.methods.common import payload

from schema import virtual_resources

def make_resource_level_handler(parent_resource, virtual_resource, schema, validator_class,
	on_update):

	"""
	Defines and returns a request handler for a virtual resource at resource-level granularity.
	"""

	def handler(updates, skip_validation=False):
		# Authentication code here adapted from ``auth.py`` in Eve.
		resource = app.config['DOMAIN'].get(parent_resource)
		public   = resource['public_methods']
		roles    = list(resource['allowed_roles'])

		if request.method in ['GET', 'HEAD', 'OPTIONS']:
			roles += resource['allowed_read_roles']
		else:
			roles += resource['allowed_write_roles']

		auth = resource_auth(parent_resource)
		if request.method not in public:
			if not auth.authorized(roles, parent_resource, request.method):
				return auth.authenticate()

		issues = {}
		
		try:
			if not skip_validation:
				validator = validator_class(schema=schema, resource=parent_resource)

			if skip_validation or validator.validate_update(updates):
				"""
				Note: the following features supported by Eve are not implemented
				here, because I'm not using them for this project. See the comments
				prefixed by "XXX" for more information.
				- Document versioning
				- Storing media files
				- Oplog updates
				- Callbacks (both pre- and post-update callbacks are ignored) [1]_
				- Informative response [2]_

				.. [1] Supporting callbacks here would also be very inefficient,
				because we would need to fetch documents for all parent and child
				tasks involved.

				.. [2] For similar reasons, the response returned to the client
				merely contains the status code, along with any errors that
				occurred.  Information about what was updated for each document is
				not provided.
				"""

				# XXX not implemented: late versioning (see patch.py in Eve).
				# XXX not implemented: storing media files (see patch.py in Eve).
				# XXX not implemented: resolving document version (see patch.py in
				# Eve).

				on_update(updates, app.data.driver.db)

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
				issues = validator.errors
				assert len(issues) != 0
		except ValidationError as e:
			issues['validator exception'] = str(e)
		except exceptions.HTTPException as e:
			raise e
		except Exception as e:
			app.logger.exception(e)
			abort(400, description=debug_error_message("An exception occurred: {}".
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

def make_item_level_handler(parent_resource, virtual_resource, schema, validator, on_update):
	"""
	Same as ``make_resource_level_handler``, but for virtual resources that work at item-level
	granularity.
	"""

	handler = make_resource_level_handler(parent_resource, virtual_resource, schema, validator,
		on_update)

	def scaffold(target_id, values, skip_validation=False):
		"""
		Args:
			skip_validation: Allows us to accept virtual resources in PATCH requests
				that also make changes to other fields. After Eve performs
				validation, we can process the updates to the virtual resources in a
				pre-event hook by invoking this handler with
				``skip_validation=True``.
		"""

		assert isinstance(target_id, str)
		return handler([{'targets': [target_id], 'values': values}], skip_validation)

	return scaffold

blueprints = []

# TODO authorization.
# XXX not implemented: rate limiting, authorization, pre-event (see patch.py in Eve).
def route(p_res, v_res, schema):
	update_schema = schema['schema']
	on_update = schema['on_update']
	validator = schema.get('validator')

	schema['handlers'] = {}
	router = Blueprint(p_res + '/' + v_res, __name__)
	blueprints.append(router)

	if 'resource' in schema['granularity']:
		h1 = make_resource_level_handler(p_res, v_res, update_schema, validator, on_update)
		schema['handlers']['resource_level'] = h1

		@router.route('/' + p_res + '/' + v_res, methods=['POST'])
		def route_resource_level():
			return h1(payload())

	if 'item' in schema['granularity']:
		h2 = make_item_level_handler(p_res, v_res, update_schema, validator, on_update)
		schema['handlers']['item_level'] = h2

		"""
		We allow PATCH for item-level virtual resources, because one should be able to use
		them in PATCH requests that also involve other fields.
		"""
		@router.route('/' + p_res + '/<item_id>/' + v_res, methods=['POST', 'PATCH'])
		def route_item_level(item_id):
			return h2(item_id, payload())

for parent_res, virtuals in virtual_resources.items():
	for virtual_res, v_schema in virtuals.items():
		route(parent_res, virtual_res, v_schema)
