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

- Ensure that the last update time of execution info is actually updated by the queries that we are
  using in Banyan.
- Also add a virtual resource (accessible by providers only) to unregister workers with the Banyan
  server. All active tasks claimed by the worker should be cancelled, and the server should wait for
  a set period of time (based on the max shutdown times provided for the tasks) before abandoning
  the cancelled tasks. The worker should be informed that it is being unregistered, so that it does
  not attempt to claim more tasks.
  - TODO implement the appropriate event hook to do the above in `event_hooks.py`.

- Maintain connections to workers to check for responsiveness and perform cancellation.
  - Change the `exit_status` field of execution data so that it is a string rather than an integer.
    Otherwise, it becomes difficult for us to convey information to the user about what the state
    means. Success is "success"; failure is "failure" if the program exited with -1. If the program
    exited with a signal, the status is "failure (<signal>)". It's up to the worker to interpret the
    exit status of the program and provide a string.
  - If a worker does not respond with a health report in a maximum allotted time, set the exit
    status of all jobs currently being serviced by that worker to "abandoned (worker unreachable)".
    - Also implement the TODO `worker_notifier.py` so that it can call the function to abandom all
      jobs currently being serviced by a worker, and unregister it from the active worker database.
  - On the other hand, if the worker cannot reach the server in the maximum allotted time limit, it
    should assume that all of its job were abandoned, cancel all active jobs, and dump the task
    cache.

- Look at `worker.md` for next stuff to implement.
  - Call the driver file `run.py`.
  - Implement task cache (possibly in new test file).
  - Test.
  - Implement cancellation buffer.
  - Test.
  - Implement updates (both for cancelled tasks and the regular status updates).
  - Test.

- For CIMS, we should create a dot directory somewhere with a dump of the worker entries auth
  database.
- Test how quickly contention for jobs is resolved by setting up one server and
  multiple workers.
  - Implement some way to time the communication overhead, so that we can check that it is not very
    high.

- Implement the virtual resources on the server side to compute statistics.
- Get sphinx to work.

- Switch to using production web server instead of Flask.
- Check that the communication overhead drops after the change.

- Use HTTPS instead of HTTP.
- Add AES encryption to sockets.

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

Example of filter query (note the escaped characters):

	curl -i -g -H 'Authorization: Basic fHdaOCp1NE9kNEFyTGp0NDo=' 'http://172.22.140.7:5100/tasks?where={"name":%20"task%201"}'

	curl -i -g -H 'Authorization: Basic fHdaOCp1NE9kNEFyTGp0NDo=' 'http://172.22.140.7:5100/tasks?where={"retry_count":{"$lt":10}}'

# Limitations for first version

- Only one queue.
- No indexing is used. Consider doing this for the next release, if we find
  that query performance is a problem.
- Bulk PATCH requests are not supported by Eve. Currently, PATCH only works for
  item endpoints (as it should, according to REST principles). A pragmatric
  (though semantically incorrect) solution is to allow bulk PATCH requests of
  the following form:

	{ {'_id': <id 1>, <updates>}, ...,  {'_id': <id n>, <updates>} }
