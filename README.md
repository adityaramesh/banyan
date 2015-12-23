# Overview

Banyan is a simple distributed job submission system written in Python. It uses
a simple model in which one server hosts a shared job queue, and each client
claims tasks from the queue based on available resources.

# Agenda

- Make it so that the user can only modify some of the fields. The clients
  should be able to authenticate themselves, and modify the others.

- Write code to handle creation.
- Test.
- Write code to handle the cancellation, except for the part that involves
  communication with the client.
- Test.

- Write the client program.
- Finish cancellation.
- Add support for the client sending progress reports.
- Test.

- At this point, the job submission system works, but:
  - We have to use curl. Consider writing a more convenient submission script
    in Python.
  - We still need the program to print out statistics, and information about
    the registered workers.

# Hooks

- Use Eve's "event hooks".

- Master to worker communication model:
  - Worker uses master's REST API.
  - One-way connection from master to worker for job cancellation. Overview:
    - Server sends message to worker to cancel job, and puts the job in an
      `unknown` state.
    - When the client sends the next update for the job to the server, it
      changes the state of the job to either `terminated` or `cancelled`.
    - This model is elegant, because even if the worker never gets the
      cancellation signal, things are still OK on the server side.

## Creation

- When a group is created:
  - For each dependent:
    - Assert that the dependent belongs to this group.
    - Assert that the dependent's status is `inactive`.
    - Increment the dependent's `pending_dependency_count`.

- When a job is created:
  - Check that:
    - The state is either `inactive` or `available`. If the job has
      dependencies, the client should never set the status to `available`. But
      it is expensive to check for this, so we won't do it.
  - For each group mentioned in `groups`, add the job to the group's pending
    job list.
  - For each dependent:
    - Assert that the dependent's status is `inactive`.
    - Increment the dependent's `pending_dependency_count`.

- When the state of a job is changed to `available`.
  - Recursively set the states of all dependents to `available`. We can stop
    recursing over a given branch when we find a job whose status is already
    set to `available`.
    - While recursing, ensure that all dependents have the `inactive` status.

## Cancellation

- When a group is cancelled:
  - For each job in the `pending_members` list:
    - Cancel the job, and remove it from the list.

- When a job is cancelled:
  - If the job is already cancelled or terminated, do nothing and report
    success.
  - If the job is `inactive` or `available`, set the status to cancelled, and
    recursively cancel all dependents.
  - If the job is `running`, send a message to the worker to cancel the job.
    The worker first uses `SIGTERM` and waits for an amount of time given by
    `max_cancellation_time`. If the process hasn't terminated yet, the worker
    uses `SIGKILL`.
  - Cancel each dependent.

- When a job terminates:
  - TODO do stuff with dependents and each group to which the job belongs.
  - If not successful:
    - TODO
    - TODO stuff with retries.
  - If successful:
    - TODO

## Client Progress Reports

- TODO

# Limitations for first version

- Only one queue.
- Fixed cancellation strategy.
- Current limitation of Eve: to append to a list, the entire list needs to be
  downloaded, appended to by the client, and transmitted back to the server.
