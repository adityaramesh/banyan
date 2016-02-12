# Overview

This is a description of the worker's basic strategy.

Resource configuration: [done]
  - Get information about total system resources.
  - Determine maximum number of resources that will be consumed by this worker
    (using a niceness level).
    - When determining the number of available cores, take utilization of each
      core into account (perhaps don't include cores that have CPU utilization
      of 60% or more).
  - Set the limit to

  	min(available resources - max(
		max resources requested by our running processes,
		resources actually used by our running processes
	), maximum consumable).
	
  - The available resources are queried each time the function that implements
    this is called.

Procedure to claim jobs as resources become available:
  - This procedure is run in a loop, as we check for available resources.
  - Obtain list of jobs from server.
  - Decide upon a selection of jobs to claim.
    - We use a greedy approach, so that jobs with the largest resource
      requirements that fit within the available resources are selected.
    - Among all jobs satisfying our requirements, we choose at random, in order
      to minimize conflicts.
  - Attempt to claim the selection of jobs (in separate requests).
  - Run claimed jobs using subprocess, without blocking.

  - Two variables configurable in settings: `job_cache_refresh_period` (default 10 seconds),
    `job_poll_period` (default 100 ms), and `job_update_period` (default one minute). Assert that
    the latter is less than the former.

  - Set the local cache so that we can start.
  - t1 = 0
  - t2 = 0

  - Loop forever:
    - If `t1 >= job_cache_update_period` and not `waiting_to_update_cache`:
      - `t1 = 0`
      - Send GET request to server with details about available resources.
      - `waiting_to_update_cache = True`
    - Else if waiting for GET request:
      - If response received:
        - Update local cache.
        - `waiting_to_update_cache = False`
	
    - Try to claim more jobs from the cache:
      - Update the `resource_set` of the `Executor` with result of `resource_info.total_resources`
      - If responses to job claim requests have been received:
	- Enqueue successfully claimed jobs; remove both successfully and unsuccessfully claimed
	  jobs from the cache.
      - If able to claim more jobs from cache:
	- Request the jobs (use a limit on the total number (e.g. 128 -- make this another
	  configuration variable), so we don't accept a very large number of jobs with low resource
	  requirements).
	- Requests for the updates have to be filed individually, because Eve doesn't support bulk
	  updates.

    - Call `poll` on the executor.

    - If the cancellation request buffer is not empty:
      - `errors = []`
      - For each job in the cancellation request buffer:
         - If the job is neither in the running list not in the terminated list:
	   - Append the job to the `errors` list.
	 - If the job is in the running list:
	   - Invoke `cancel` on the job.
      - If `errors` is not empty, log the exception here.

    - If there are terminated jobs:
      - Set `updates = []`
      - For each terminated job:
        - Append updates with the status of the terminated job.
      - Send the updates to the server.

    - If `t2 >= job_update_period`:
      - `t2 = 0`
      - `updates = []`
      - For each running job:
        - Append an update with the resource usage to `updates`
      - Send the updates

    - sleep for job_poll_period
    - `t1 = t1 + job_poll_period`
    - `t2 = t2 + job_poll_period`

Polling jobs: [done]
  - For each job:
    - Check whether it has terminated.
    - If so, send update to server and add it to a list of retired tasks, along
      with a timestamp and other relevant information.
    - If the job was marked for cancellation, send a reply back to the server.

Cancellation:
  - Periodically check a message buffer as part of the overall loop.
  - The server sends cancellation messages to the worker by delivering to this
    message buffer.
    - This buffer should also be used when the server needs to know about
      overall usage statistics. The worker then sends a response to the server.
    - Do we need a separate resource on the server for resources available on each worker?
      - Other solution: associate with user database.
      - Reuse `resource_info` for schema?
  - For each cancellation message:
    - If the corresponding task has already been cancelled or terminated:
      - Send a reply using the saved information.
    - If the corresponding task is running:
      - Mark the job as pending cancellation.
      - Use SIGTERM/SIGKILL based on the wait times associated with that task.

Updates about job resource usage:
  - TODO
