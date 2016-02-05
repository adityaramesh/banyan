# -*- coding: utf-8 -*-

"""
banyan.server.lock
------------------

Lock to serialize processing of requests that deal with task creation, state
changes, and continuations.
"""

from threading import Lock

lock = Lock()
