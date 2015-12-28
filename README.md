# Overview

Banyan is a simple distributed job submission system written in Python. It uses
a simple model in which one server hosts a shared job queue, and each client
claims tasks from the queue based on available resources.

# Agenda

- Revise the test script and rerun it to verify correctness.

- Server-side code.
  - Implement task creation.
  - Test.
  - Implement work-stealing (without worker).
  - Test.
  - Implement cancellation (without worker).
  - Test.
  - Implement task state changes.
  - Test.

- Worker-side code.
  - Implement basic prototype to run jobs without the server.
  - Test.
  - Implement task termination.
  - Test.
  - Implement work-stealing.
  - Test.
  - Implement cancellation.
  - Test.

- Write the client program.
- Finish cancellation.
- Add support for the client sending progress reports.
- Test.

- At this point, the job submission system works, but:
  - We have to use curl. Consider writing a more convenient submission script
    in Python.

- Implement the virtual resources on the server side to compute statistics.

# Usage Notes

- Eve supports projections, which allow the client to request only certain
  fields. Use this whenever we don't actually need to look at the entire state
  of a job or group, since it will generally be quite large.

# Limitations for first version

- Only one queue.
- No indexing is used. Consider doing this for the next release, if we find
  that query performance is a problem.
