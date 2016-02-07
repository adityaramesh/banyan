# -*- coding: utf-8 -*-

"""
banyan.worker.executor
----------------------

Agent responsible for managing tasks and providing cumulative resource utilization information.
"""

from math import floor
from collections import namedtuple

ExecutorResourceUsage = namedtuple('ExecutorResourceUsage', [
	'cpu_utilization_percent',
	'cpu_cores',
	'gpus',
	'memory_bytes'
])

class Executor:
	def __init__(self):
		self.running = []
		self.terminated = []

	def submit(self, task):
		task.run()
		self.running.append(task)

	def usage(self):
		"""
		Returns the resources that we expect to be necessary in order to ensure that the
		tasks currently running can terminate successfully, and in a reasonable amount of
		time.
		"""

		reserved_util   = 0
		reserved_cores  = 0
		reserved_gpus   = 0
		reserved_memory = 0

		for task in self.running:
			if task.status() is not None:
				continue

			usage = task.usage()

			req_util = task.requested_resources['cpu_utilization_percent']
			req_gpus = len(task.requested_resources['gpus'])
			req_mem  = task.requested_resources['memory']

			used_util = usage['cpu_utilization_percent']
			used_mem  = usage['resident_memory_bytes']
			max_util  = max(req_util, used_util)

			reserved_util   = reserved_util   + max_util
			reserved_cores  = reserved_cores  + floor(max_util)
			reserved_gpus   = reserved_gpus   + req_gpus
			reserved_memory = reserved_memory + max(req_mem, used_mem)

		return ExecutorResourceUsage(
			cpu_utilization_percent=reserved_util,
			cpu_cores=reserved_cores,
			gpus=reserved_gpus,
			memory_bytes=reserved_memory
		)

	def poll(self):
		"""
		Updates the ``running`` and ``terminated`` task lists.
		"""

		new_running = [t for t in self.running if t.status() is None]
		self.terminated.extend([t for t in self.running if t.status() is not None])
		self.running = new_running
