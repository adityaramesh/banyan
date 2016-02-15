# -*- coding: utf-8 -*-

"""
banyan.worker.settings
----------------------

Settings for the worker client program.
"""

from banyan.settings import max_task_set_size

"""
XXX: If ``usage_limits`` is not declared, than Banyan will attempt to consume all resources
available on the system. See ``banyan/worker/schema.py`` for information about how to restrict
resource usage.
"""

task_cache_size = max_task_set_size
# How often to refresh the local task cache.
task_cache_update_period_ms = 10 * 1000
# How often to send updates to the server, in milliseconds.
task_update_period = 60 * 1000
# How often the statuses of running tasks should be polled.
task_poll_period = 100
