# -*- coding: utf-8 -*-

"""
Defines the virtual subresources used to add items to and remove items from
list-based fields.
"""

# TODO reorganize later
from datetime import datetime
from bson import ObjectId
from flask import Blueprint, abort, request, current_app as app
from eve.utils import config, parse_request
from eve.render import send_response
from eve.methods import patch

from eve.method.common import get_document, parse, payload as payload_, store_media_files, \
	resolve_embedded_fields
from eve.versioning import resolve_document_version, late_versioning_catch
import pdb

blueprint = Blueprint('virtual_resources', __name__)

"""
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

*** KEEP SOME OF THE IMPORTANT NOTES IN THE DOC (e.g. about datalayer) BUT
REMOVE THE REST LATER ***

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

- Use the schema of the values array (e.g. so that we can create a
  new Validator and implicitly use `_validate_data_relation`
  `_validate_type_objectid` to check correctness). We can just obtain this
  schema directly from the one defined in settings.py; the programmer doesn't
  need to provide it.
- http://stackoverflow.com/questions/3144737/multiple-simultaneous-updates-with-mongodb-pymongo

-------------------------------------------------------------------------------

- TODO: also allow the user to use virtual subresources in regular POST
  requests, e.g. so that other fields of a task can be modified using the same
  request that adds/removes continuations. To do this, use one of the methods
  below.

- Don't use the method below unless method 1 is infeasible.

- Method 1. This method involves subclassing the eve.io.mongo.Mongo DataLayer.
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

- Method 2. WARNING: the procedure below is NOT a robust, production-ready
  solution. Since all of the updates will no longer be performed using the same
  transaction sent to the database, the update will not be atomic if either the
  regular updates or the updates to the virtual subresources fail.
  - Use a pre-event hook to (1) convert the body of the request payload into
    JSON, and (2) filter out any virtual subresources from it. If possible, try
    to reuse this JSON when the request is forwarded to the internals of Eve.
  - In the pre-event hook, we need to validate all of the virtual subresource
    fields. Otherwise, we can't guarantee that the entire PATCH operation will
    be atomic. If validation fails, return in the same way that
    `patch_internal` does.
  - Save the PATCH fields that we have filtered out somehow (e.g. using Flask's
    request object, if it's valid to do this).
  - Post-event hooks are called in `render.py`; `send_response` is wrapped by a
    decorator that calls the appropriate post-event hooks before returning the
    response. This allows us to modify the response, if necessary.
  - In the post-event hook, do the following. If the current response already
    indicates failure, then do nothing. Otherwise, for each virtual subresource
    field that was saved, perform the update to it. If it fails, alter the
    current response so that it has the correct status code and message. Then
    return. Otherwise, don't alter the response.
"""

# TODO offload the validation step to a separate function, so that we can reuse
# this in the pre-event hook to allow virtual subresources to be used in general
# PATCH requests. If `validate=False`, don't call this function (as it should
# be been done already by the pre-event hook).
def append_to_lists(field, updates, validate=True):
	target_schema = {}


	resource = 'tasks'
	original = get_document(resource, concurrency_check=False, **lookup)

	if not original:
		abort(404)

	resource_def = app.config['DOMAIN'][resource]
	object_id = original[resource_def['id_field']]
	
	if config.BANDWIDTH_SAVER:
		embedded_fields = []
	else:
		req = parse_request(resource)
		embedded_fields = resolve_embedded_fields(resource, req)

	try:
		# Converts the payload (a string) into JSON.
		updates = parse(payload, resource)

		if validation_func(updates, object_id, original):
			# Apply coerced values

			# Sneak in a shadow copy if it wasn't already there
			late_versioning_catch(original, resource)

			# Stores any media files (defined in the resource
			# schema) in advance, before processing the document.
			store_media_files(updates, resource, original)

			# If document versioning is enabled, then the function
			# below updates the version number of the document.
			resolve_document_version(updates, resource, 'PATCH', original)

			updates[config.LAST_UPDATED] = datetime.utcnow().replace(microsecond=0)
			
"""
The payload must be a JSON object whose keys are either `ObjectId`s or arrays
of `ObjectId`s of the parent tasks. The values must be arrays of `ObjectId`s of
the continuation tasks. This design allows for:

  1. Efficient addition of the same continuations to many parents.
  2. Efficient bulk insertion of continuations to many parents.
"""
@blueprint.route('/tasks/add_continuations', methods=['POST'])
def add_continuations():
	resource = 'tasks'
	
	# Payload: {'continuations': [...]}.
	# Ensure that payload has only that key.
	# Ensure that each id is a valid objectid using the same code that eve does.
	# Ensure no duplicates.
	#response = patch(resource, **{config.ID_FIELD: ObjectId(task_id)})
	return send_response(resource, response)
