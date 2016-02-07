# Overview

This is a description of the worker's basic strategy.

Resource configuration:
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
  - Attempt to claim the selection of jobs (in separate requests).
  - Run claimed jobs using subprocess, without blocking.

Polling jobs:
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
