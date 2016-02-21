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

- TODO: try to prevent deadlock in the event of an internal server error. can we release any
  acquired locks in a handler somewhere?

- Move Banyan settings to an external path rather than keeping the settings file in the `banyan`
  source directory.
- Add key to the execution data field, and require workers to provide the key when they post updates
  to the execution data. It's not good for workers infer job abandonment by the server with a 422
  response, since there is a relatively high probability of false positives.
- Add a virtual resource (accessible by providers only) to register workers with the Banyan server.
  Don't scan the `auth` database to detect workers; it should only be store credentials, not IPs.

- Maintain connections to workers to check for responsiveness and perform cancellation.
  - Change the `exit_status` field of execution data so that it is a string rather than an integer.
    Otherwise, it becomes difficult for us to convey information to the user about what the state
    means. Success is "success"; failure is "failure" if the program exited with -1. If the program
    exited with a signal, the status is "failure (<signal>)". It's up to the worker to interpret the
    exit status of the program and provide a string.
  - If a worker does not respond in a maximum allotted time, set the exit status of all jobs
    currently being serviced by that worker to "abandoned (worker unreachable)".
  - On the other hand, if the worker cannot reach the server in the maximum allotted time limit, it
    should assume that all of its job were abandoned, cancel all active jobs, and dump the task
    cache.
- To properly clean up resources in Eve, the following links suggest that we have to options:
  - http://stackoverflow.com/questions/30739244/python-flask-shutdown-event-handler
  - http://stackoverflow.com/questions/10795095/where-do-i-put-cleanup-code-in-a-flask-application
- Option 1: use atexit. But this won't work if the application is terminated by a signal.
- Option 2: respond to the signals (e.g. using signalfd with epoll in a separate thread).

- Look at `worker.md` for next stuff to implement.
  - Call the driver file `run.py`.
  - Implement task cache (possibly in new test file).
  - Test.
  - Implement cancellation buffer.
  - Test.
  - Implement updates (both for cancelled tasks and the regular status updates).
  - Test.

- Test how quickly contention for jobs is resolved by setting up one server and
  multiple workers.

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
