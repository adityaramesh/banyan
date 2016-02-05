# Overview

Banyan is a simple distributed job submission system written in Python. It uses
a simple model in which one server hosts a shared job queue, and each client
claims tasks from the queue based on available resources.

# What's Done Now

- Task creation
  - Tasks with no command
  - Tasks created with continuations
- Virtual resources.
  - Resource- and item-level.
  - Item-level virtual resources allowed in PATCH requests.
  - For adding and removing continuations; adding execution history.
  - Locks to ensure synchronize access to certain resources.
- Access control for users and workers using tokens.
- Endpoints secured; requests are checked for appropriate permissions.
- Server-side support for state transitions.

# Agenda

- Server-side code.
  - Add tests for virtual resources in `test_server.py`.
    - State changes; addition, removal, cancellation of continuations; updates
      to execution data.

- Worker-side code.
  - Implement basic prototype to run jobs without the server.
  - Test.
  - Implement work-stealing (worker side).
  - Test.
  - Implement task termination.
  - Test.
  - Implement cancellation (worker side).
  - Test.

- Switch to using production web server instead of Flask's, and use HTTPS instead of HTTP.
- At this point, the job submission system works, but:
  - We have to use curl. Consider writing a more convenient submission script
    in Python.

- Add support for the client sending progress reports.
- Test.

- Implement the virtual resources on the server side to compute statistics.
- Get sphinx to work.

# Usage Notes

- Eve supports projections, which allow the client to request only certain
  fields. Use this whenever we don't actually need to look at the entire state
  of a job or group, since it will generally be quite large.

## Example Requests

	curl -X POST -H 'Content-Type: application/json' -d '{"command": "test", "requested_resources": {"memory": "1 GiB"}}' http://<entry_point>/tasks
	
	curl -X PATCH -H 'Content-Type: application/json' -d '{"requested_resources": {"cores": 1, "memory": "1 GiB"}}' http://<entry_point>/tasks/<id>

POST using arrays and ObjectIDs:

	curl -X POST -H 'Content-Type: application/json' -d '{"name": "parent", "continuations": ["<id>"]}' http://<entry_point>/tasks

POST using authentication token and datetime. Notes:
- Assumes that `DATE_FORMAT` is set to the default value of `"%a, %d %b %Y %H:%M:%S GMT"`.
- The authorization header must describe the username and password in the format `<user>:<pass>`,
where the entire string, encoding the colon, are base-64 encoded. So even if we are using no
password (as is the case for authentication tokens), an encoded colon should be included at the end
of the username.

	curl -X POST -H 'Content-Type: application/json' -H 'Authorization: Basic tmHMHLY0ues0+eh1fEa04To=' -d '{"task": "56a210d5e7794978227cb2f4", "time": "Tue, 02 Apr 2013 10:29:13 GMT", "resident_memory_bytes": 256}' http://172.22.140.7:5000/memory_usage

# Limitations for first version

- Only one queue.
- No indexing is used. Consider doing this for the next release, if we find
  that query performance is a problem.
- Bulk PATCH requests are not supported by Eve. Currently, PATCH only works for
  item endpoints (as it should, according to REST principles). A pragmatric
  (though semantically incorrect) solution is to allow bulk PATCH requests of
  the following form:

	{ {'_id': <id 1>, <updates>}, ...,  {'_id': <id n>, <updates>} }
