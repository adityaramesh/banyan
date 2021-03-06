# Overview

This is the specification for the server's interface.

# Synchronization

- Actions that need locking:
  - Any state changes:
    - Conflicts with task being made available. This can only happen if there is more than one user
      with access to the queue. This conflict is benign as long as the task doesn't get claimed,
      since the cancellation procedure doesn't change, and there are no side effects.
    - Conflicts with task being made available. Then a worker may end up running a cancelled task.
    - Conflicts with termination. Then some continuations may end up getting run, while others get
      cancelled. Continuation lists of parent tasks may no longer be accurate, leading to application      errors.
  - Terminating a task: see above conflict list.
  - Running a task: see above conflict list.
  - Adding/removing continuations.
  - Task creation.

- This synchronization may lead to problems when many workers claim tasks or report termination of
  tasks simultaneously. But servicing both kinds of requests requires access to the database anyway,   and this is always serialized. So I'm not sure if the additional overhead will be significant.

# Indices to Potentially Create

- `tasks`
  - `state`
  - `continuations`
  - `estimated_runtime`
  - `requested_resources`

# Virtual Resources to Implement

- For use by the user:
  - `tasks/add_continuations`
  - `tasks/remove_continuations`
  - `tasks/current_history`

- TODO: virtual resources for computing statistics.
  - Global virtual resources for global statistics.
  - Subresources of `tasks` for finer scope.

- For use by workers:
  - `execution_info/worker`
  - `execution_info/exit_status`
  - `execution_info/time_terminated`
  - `execution_info/time_started`
  - `execution_info/memory_usage`
  - `execution_info/cpu_utilization`
  - `execution_info/gpu_usage`
  - `execution_info/report_memory_usage`
  - `execution_info/report_cpu_utilization`
  - `execution_info/report_gpu_usage`

# Events

## Task Creation; Dynamic Addition and Removal of Continuations

- Procedure `acquire_continuation(task)`.
  - Assert that the state is `inactive`.
  - Increment `pending_dependency_count`.

- Procedure `release_continuation(task)`.
  - Assert that the state is `inactive`.
  - Ensure that `pending_dependency_count` is positive.
  - Decrement `pending_dependency_count`.
  - If `pending_dependency_count` is zero, set the state to `available`.

- Procedure `release_continuations(g)`.
  - For each continuation `c`, call `release_continuation(c)`.

- When a task is created:
  - Check that the state is either `inactive` or `available`.
  - For each continuation `c`, call `acquire_continuation(c)`.
  - If the task has no provided command and is created in the `available`
    state, then call `release_continuations(self)`. Then set the state to
    `terminated`.

- Create the following virtual resources for this; make the `continuations`
  field read-only.
  - `tasks/add_continuation`.
  - `tasks/remove_continuation`.

## Work-Stealing

- The worker obtains a list of `available` tasks from the server. It only needs
  the following fields (use projections for this to avoid unnecessary data
  transmission):
  - `_id`
  - `max_termination_time`
  - `requested_resources`

- Procedure `claim_task`.
  - The worker sends a PATCH request with:
    - `state` set to `running`.
    - `execution_info/worker` to its own identity.
  - If the task wasn't claimed by another worker or cancelled, the server
    performs the change and reports success.
  - After the worker receives a successful response, it sends a POST request to
    `execution_info/time_started`, and executes the task.
  - Otherwise, the request to claim the task was unsuccessful. The worker does
    one of the following:
      - Try to claim another task.
      - Obtain a fresh view of the list of available tasks.

## Cancellation

- Procedure `cancel_continuations(task)`.
  - For each continuation `c`, call `cancel_task(c)`.

- Procedure `cancel_task(task)` (server side).
  - If state is `cancelled` or `terminated`, then do nothing and report success.
  - If `inactive` or `available`, set the state to `cancelled`.
    - Call `cancel_continuations(task)`.
  - If `running`:
    - Using a dedicated socket, send a message to the worker to cancel the task.
    - Change the state of the task to `pending_cancellation`.
    - When the worker sends the next update for the task to the server, the
      state should either be changed to `terminated` or `cancelled`. This
      causes the worker to execute `cancel_task`.
    - This model is elegant, because even if the worker never gets the
      cancellation signal, things are still OK on the server side. The server
      is not dependent on confirmation from the worker in order to continue
      affairs.

- Procedure `send_task_ended_update(task, state, time, status)`. Send a PATCH
  request for `task` to the server:
  - Change the state to `state`.
  - Set `execution_info/time_terminated` to `time`.
  - If `code` is not null, set `execution_info/exit_status` to `code`.

- Procedure `cancel_task(task)` (worker side).
  - If `task` has already terminated, call
    `send_task_ended_update(task, terminated, time, status)` and return.
  - Use SIGTERM and wait for the amount of time given by
    `max_termination_time`. If the process hasn't terminated yet, resort to
    using `SIGKILL`.
  - Call `send_task_ended_update(task, cancelled, time)` and return. Include
    `status` in the function call if the process was successfully terminated
    with SIGTERM.

## Progress Reports from Workers

- Concurrency control should not be required for this.
- The rate at which updates are sent to the server is completely up to the
  worker.

- The server maintains a history of `execution_info` objects; each instance of
  `execution_info` contains the information associated with one attempt to
  complete a task.
- The worker shouldn't have to know about the `history` field in order to send
  updates to the server. Instead, the server should deal with appending the
  updates received from the worker to the appropriate data structures.
- To implement this behavior, the server exposes the following API to the
  worker. It is similar to the structure of the `execution_info` field, except
  that list-typed fields can only be appended to via POST or PATCH requests to
  `report_*` resources.
- `execution_info`
  - `worker`
  - `exit_status`
  - `time_terminated`
  - `report_memory_usage`
  - `report_cpu_utilization`
  - `report_gpu_usage`

## Computing Statistics

- TODO: implement the rest of the events first.

## Task State Changes

- No concurrency control is required for any of the state changes below. Rather
  than enforcing that the client has up-to-date information for each request,
  it's better to simply fail invalid requests, and let the client decide what
  to do.

- Allowable state changes:
  - Inactive to:
    - Available
    - Cancelled
  - Available to:
    - Running
    - Cancelled
  - Running to:
    - Terminated
    - Cancelled (actually puts the task in 'Pending Cancellation' state)
  - Pending Cancellation to:
    - Terminated
    - Cancelled

### Inactive to Available

- Nothing special.

### Inactive to Cancelled

- Also remove the task from all continuation lists that mention it.

### Available to Running

- The server fulfills a request from a worker to claim a task.
- Run the steps described in the section on work-stealing; nothing more has to
  be done. 
- Increment `retry_count`.
- Insert a new `execution_data` document into the `execution_history` database.

### Available to Cancelled

- In this case, the server receives a request from the user to change the
  status of the task to `cancelled` when the current state of the task is
  `available`.
- Run the steps described in the section on cancellation above; nothing more
  has to be done.

### Running to Terminated

- In this case, the server receives a PATCH request from a worker that does the
  following:
  - Updates the state to `terminated`.
  - Updates `execution_info/time_terminated`.
  - Updates `execution_info/exit_status`.
- If the status indicates unsuccessful termination:
  - If `retry_count` is less than `max_retry_count`:
    - Record the changes to `execution_info`.
    - Append a new `execution_info` object to the `history` list.
    - Set the state to `available`.
  - Else, call `cancel_continuations(self)`.
- Else, call `release_continuations(self)`.

### Running to Pending Cancellation

- Run the steps described in the section on cancellation above; nothing more
  has to be done.

### Pending Cancellation to Terminated

- In this case, the server has received a request from the worker to change the
  status of the task to `terminated` when the current state of the task is
  `pending_cancellation`.
- Run the steps described in the section on cancellation above.

### Pending Cancellation to Cancelled

- In this case, the server receives a request from the worker to change the
  status of the task to `cancelled` when the current state of the task is
  `pending_cancellation`.
- Run the steps described in the section on cancellation above; nothing more
  has to be done.
