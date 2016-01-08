# Overview

Banyan is a simple distributed job submission system written in Python. It uses
a simple model in which one server hosts a shared job queue, and each client
claims tasks from the queue based on available resources.

# Agenda

- Server-side code.
  - Virtual resources for adding and removing continuations; make the
    continuations field read-only.
    - Get `add_continuations` to work as an external resource.
      - First make sure `add_continuations` is invoked correctly.
      - Add support for validating both of the following:
        - POST requests to `/tasks/add_continuations`
        - `add_continuations` fields in PATCH requests
      - Validate the payload of the request. `_validate_data_relation` and
	`_validate_type_objectid` may be useful. The schema of each array can
        be obtained automatically from the one in `settings.py`.
      - Generate and print the query that would be executed by the DB
      - Put in the parts of the `patch_interal` function that are relevant here
	(e.g. calling hooks). Make use of `allows_duplicates` to determine
        whether to use `$addToSet` or `$push`.
      - Add tests for the final implementation to `test_server.py`.
    - Get `remove_continuations` to work as an external resource.
      - Change from above: use `$pull` instead of `$addToSet`.
    - Get `add_continuations` to work when used with general PATCH requests.
      - Only two classes need to be modified for this: the validator and the
        data layer.
      - First subclass `Mongo` so that `update` simply discards
        `add_continuation` fields.
      - Use this as the data layer when instantiating the Eve app.
      - Ensure that validation works.
      - Now change the validator so that `add_continuation` is no longer a
	no-op. Make use of `allows_duplicates` to determine whether to use
        `$addToSet` or `$push`.
      - Add tests for the final implementation to `test_server.py`.
    - Get `remove_continuations` to work when used with general PATCH requests.
      - Change from above: 
    - After implementing the above, remove the indicated code from
      `event_hooks.py`.
  - Abstract and generalize the mechanism to create virtual subresources.
    - Kinds of virtual subresources: alias (readonly or read and write),
      append, remove.
      - Last two cases already taken care of.
      - POST for item-level writes; PATCH for field-level writes.
      - Alias readonly: only supports GET. Model `get.py` in Eve.
	- Does not support item-level read, since "gather" reads should be
          performed using projections (test later).
      - Alias read and write: supports GET and PATCH. Need to add support for
        inclusion of virtual subresource in PATCH requests.
	- Does not support item-level read, but should support item-level write
	  (e.g. so that worker can set the `worker` field for many tasks to its
          identity simultaneously).
	- GET for reads. POST for item-level writes; PATCH for field-level
          writes.
  - Automatically create virtual resources using the schema given by
    `VIRTUAL_RESOURCES` in `settings.py`. All of the tags used must be
    implemented, including `readonly` for virtual resources that alias their
    targets.
  - Test support for projections with virtual resources.
  - Implement a method for workers to authenticate themselves, so that
    additional updates can be made. When a worker is started on a machine, one
    of the first things it should do is establish a connection with the server
    and authenticate itself.
  - Change the virtual subresources for history in `settings.py` so that only
    authenticated workers can write history.
  - Test.
  - Implement work-stealing (server side).
  - Test.
  - Implement cancellation (server side).
  - Test.
  - Implement server-side code for state changes made by worker.
  - Test.

- Worker-side code.
  - Implement basic prototype to run jobs without the server.
  - Test.
  - Implement work-stealing (worker side).
  - Test.
  - Implement task termination.
  - Test.
  - Implement cancellation (worker side).
  - Test.

- At this point, the job submission system works, but:
  - We have to use curl. Consider writing a more convenient submission script
    in Python.

- Add support for the client sending progress reports.
- Test.

- Implement the virtual resources on the server side to compute statistics.

# Usage Notes

- Eve supports projections, which allow the client to request only certain
  fields. Use this whenever we don't actually need to look at the entire state
  of a job or group, since it will generally be quite large.

## Example Requests

	curl -X POST -H 'Content-Type: application/json' -d '{"command": "test", "requested_resources": {"memory": "1 GiB"}}' http://<entry_point>/tasks
	
	curl -X PATCH -H 'Content-Type: application/json' -d '{"requested_resources": {"cores": 1, "memory": "1 GiB"}}' http://<entry_point>/tasks/<id>

	curl -X POST -H 'Content-Type: application/json' -d '{"name": "parent", "continuations": ["<id>"]}' http://<entry_point>/tasks

# Limitations for first version

- Only one queue.
- No indexing is used. Consider doing this for the next release, if we find
  that query performance is a problem.
- Bulk PATCH requests are not supported by Eve. Currently, PATCH only works for
  item endpoints (as it should, according to REST principles). A pragmatric
  (though semantically incorrect) solution is to allow bulk PATCH requests of
  the following form:

	{ {'_id': <id 1>, <updates>}, ...,  {'_id': <id n>, <updates>} }
