# Overview

Banyan is a simple distributed job submission system written in Python. It uses
a simple model in which one server hosts a shared job queue, and each client
claims tasks from the queue based on available resources.

# Agenda

- Test the schema.
- Test the server program on duncan using a Python script that issues requests.
- Test the server program from another node.
- Test the server program from liz.
- Write code to handle things like cancellation correctly.
- Test again.

- Write the client program.
- Write tests.

# Limitations for first version

- Only one queue.
- No server to client communication (so running jobs can't be cancelled).
