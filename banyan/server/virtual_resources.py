# -*- coding: utf-8 -*-

"""
Defines the virtual subresources used to add items to and remove items from
list-based fields.
"""

from copy import copy
from bson import ObjectId
from datetime import datetime

from werkzeug import exceptions
from flask import Blueprint, current_app as app

from eve.defaults import build_defaults
from eve.utils import *
from eve.validation import ValidationError
from eve.methods.common import *
from eve.versioning import *

from validation import Validator

blueprint = Blueprint('virtual_resources', __name__)

"""
When the user POSTs to a virtual subresource, it is understood that all of the
requested updates are to made in one atomic transaction. The `Mongo` data layer
provided by Eve doesn't implement this functionality. Instead, we use the
following steps:
  1. Validate the JSON array of updates.
  2. Use the JSON array to construct one large batch update operation.
  3. Execute the update operation.

The problem here is that MongoDB imposes a limit of 16 Mb on any BSON document.
So the update will be invalid if it is too large. To ensure that this doesn't
happen, we restrict the sizes of the following:
  1. The number of updates in the JSON array.
  2. The size of the 'targets' and 'updates' lists for each update.

We assume that the maximum size of any element in the 'target' or 'updates'
list is 128 bytes. With the constants as defined below, the maximum update size
is precisely 16 Mb. Atomic updates larger than this cannot be made.
"""
max_update_list_length = 128
max_item_list_length = 1024

virtual_resource_keys = {'targets', 'values'}

"""
Note: we could disallow empty lists for targets using `'empty': False`, since
the update would effectively be a no-op. But technically, returning success in
this case is the right thing to do.
"""
target_schema = {
	'targets': {
		'type': 'list',
		'maxlength': max_item_list_length,
		'allows_duplicates': False,
		'schema': {
			'type': 'objectid',
			'data_relation': {
				'resource': 'tasks',
				# The key 'field' defaults to _id, so normally, we would not need to
				# provide it explcitly. These default values for schema are set in
				# flaskapp.py. However, it's easier to provide the default value
				# manually than to apply the existing code to do it for us.
				'field': '_id'
			}
		}
	}
}


"""
Note: we could disallow empty lists for updates using `'empty': False`, since
the update would effectively be a no-op. But technically, returning success in
this case is the right thing to do.
"""
continuation_update_schema = copy(target_schema)
continuation_update_schema['values'] = {
	'type': 'list',
	'maxlength': max_item_list_length,
	'allows_duplicates': False,
	'schema': {
		'type': 'objectid',
		'data_relation': {
			'resource': 'tasks',
			'field': '_id'
		}
	}
}

def validate_updates(updates, schema, extra_valid_func=None):
	if not isinstance(updates, list):
		return updates, {'input': "Updates string must be a JSON array."}

	if len(updates) > max_update_list_length:
		return updates, {'input', "Updates array can have at most {} elements.". \
			format(max_update_list_length)}

	issues = {}

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
		# This deserializes some values that require special handlers,
		# such as ObjectIds.
		# TODO: fill in default fields for the schema.
		# TODO: fill in default values for list elements, if specified.
		revised_update = serialize(update, schema=schema)
		revised_updates.append(revised_update)

		def log_issue(msg):
			issues['update {}: validator errors'.format(i)] = msg

		if not validator.validate(revised_update):
			log_issue(str(validator.errors))
			continue

		if extra_valid_func:
			extra_valid_func(revised_update, log_issue)

	return revised_updates, issues

"""
TODO revise description:

Given the name of an array-valued field, this function appends given elements
to the corresponding array of each task in a given set.

For the task corresponding to each id in `task_ids`, this function appends
the elements in `values` to the array mapped to by the field `field`.

The implementation is based on the function `eve.methods.patch.patch_internal`.
We can't use `patch_internal` directly, because `field` is typically
`readonly`. This prevents the client from appending to/removing from `field` directly
(which is inefficient, because the whole array must be sent to the client,
modified remotely, and then sent back to replace the original).

Parameters:
- `field`: Name of the field that maps to the array that we wish to append to.
- `task_ids`: Array whose elements are either `ObjectId`s or arrays of
  `ObjectId`s. Each `ObjectId` corresponds to a task that we wish to update.
  Each element of the outer array 
- `values`: Elements to append to the array for each task.
- `valid_func`: Function used to validate the 

- Notes: how to make `continuations` be treated like a set.
  - Ideally, we would just always use Mongo's $addToSet operator. But Eve's
    `Mongo` `DataLayer` is only capable of performing updates using
    `db.update_one` and `$set`. In order to change this behavior, we would
    essentially need to write our own `DataLayer` object, which is a lot of
    work.
  - Easier solution: (1) when the task is first created, use a pre-insert hook
    to remove duplicates from `continuations`, if it is provided. (2) from this
    point onward, continuations can only be added using `add_continuations`. In
    this case, we perform the insertion by ourselves, so we can use `$addToSet`
    without removing duplicates beforehand. Subclass `Mongo` for this.

-------------------------------------------------------------------------------

- TODO: also allow the user to use virtual subresources in regular POST
  requests, e.g. so that other fields of a task can be modified using the same
  request that adds/removes continuations. To do this, use the method below.

- This method involves subclassing the eve.io.mongo.Mongo DataLayer.
  - Remember to set the DataLayer of the Eve app to the subclassed version of
    the DataLayer when starting Eve.
  - Override the `update` function of `Mongo`.
  - If `resource` contains any virtual subresources (store the names of these
    in a list, perhaps in the config, or else determine it automatically), call
    `super()._change_request`, using `$push` or `$addToSet` as necessary.
  - Consider implementing a rule like `is_set`, so that we can choose which
    operator to use for appending elements.
  - Use `$pull` to remove elements. We need to do special formatting for this
    query, so that the argument of the operator is a set of dictionaries of the
    form `{'_id': <id>}`.
"""
@blueprint.route('/tasks/add_continuations', methods=['POST'])
def add_continuations():
	# JSON representation of request payload.
	updates = payload()

	issues = {}
	response = {}
	
	try:
		def check_self_loops(updates, log_issue):
			t = updates['targets']
			u = updates['values']

			if len(set(u) - set(t)) != len(u):
				log_issue("Field 'updates' mentions values in 'targets'.")

		updates, errors = validate_updates(updates, continuation_update_schema,
			check_self_loops)

		if not errors:
			# TODO
			pass
		else:
			issues = errors
	except ValidationError as e:
		issues['validator exception'] = str(e)
	except exceptions.HTTPException as e:
		raise e
	except Exception as e:
		app.logger.exception(e)
		abort(400, description=debug_error_message("An exception occurred: {}".format(e)))

	print(issues)
		
	#if len(issues) > 0:
	#	response[config.ISSUES] = issues
	#	response[config.STATUS] = config.STATUS_ERR
	#	status = config.VALIDATION_ERROR_STATUS
	#else:
	#	response[config.STATUS] = config.STATUS_OK
	#	status = 200

	#response = marshal_write_response(response, 'tasks')

	# We don't support concurrency control, and by returning `None` for
	# 'last modified', we simply return the current time.
	# todo incorporate stuff below into response using send_response
	#etag = None
	#last_modified = None
	#, last_modified, etag, None #status= None
	return "poop" 
