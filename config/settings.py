# -*- coding: utf-8 -*-

"""
banyan.settings
---------------

Settings common to both the ``server`` and ``worker`` modules.
"""

mongo_port        = 27017
banyan_port       = 5100
max_task_set_size = 128

# How often the server should poll workers for resource usage updates.
usage_update_poll_period = 60 * 1000
