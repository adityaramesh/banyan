# -*- coding: utf-8 -*-

"""
banyan.server.lock
------------------

Defines locks for resources that require synchronized access. A request may result in the execution
of several database operations, so we cannot rely on atomicity of individual database operations to
enforce this.
"""

from threading import Lock

task_lock = Lock()
registered_workers_lock = Lock()
