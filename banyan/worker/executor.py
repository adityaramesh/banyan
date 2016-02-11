# -*- coding: utf-8 -*-

"""
banyan.worker.executor
----------------------

Agent responsible for managing tasks and providing cumulative resource utilization information.
"""

from banyan.worker.resource_info import ResourceSummary
from banyan.worker.task import ResourceUsage

class Executor:
	def __init__(self, resource_set):
		self.resource_set = resource_set
		self.running      = []
		self.terminated   = []

	def submit(self, task):
		task.run(self.resource_set)
		self.running.append(task)

	def poll(self):
		"""
		Updates the ``running`` and ``terminated`` task lists.
		"""

		new_running = [t for t in self.running if t.status() is None]
		self.terminated.extend([t for t in self.running if t.status() is not None])
		self.running = new_running

	def usage(self):
		"""
		Returns the sum of the resources used by all running tasks.
		"""

		return sum([t.usage() for t in self.running if t.status() is None],
			ResourceUsage())

	def resources_claimed(self):
		"""
		Returns the resources that we expect to be necessary in order to ensure that the
		tasks currently running can terminate successfully, and in a reasonable amount of
		time. Generally, this means taking the maximum of the resources reserved by the
		task, and the resources currently being consumed by the task.
		"""

		claimed_memory = 0
		claimed_cores  = 0
		claimed_gpus   = 0

		for task in self.running:
			if task.status() is not None:
				continue

			usage = task.usage()
			reserved = task.reserved_resources

			claimed_memory = claimed_memory + max(reserved.memory_bytes,
				usage.resident_memory_bytes)
			claimed_cores = claimed_cores + reserved.cpu_cores
			claimed_gpus = claimed_gpus + reserved.gpus

		return ResourceSummary(
			memory_bytes=claimed_memory,
			cpu_cores=claimed_cores,
			gpus=claimed_gpus
		)

	def resources_unclaimed(self):
		"""
		Returns the resources in our resource set that are not being used by any processes.
		"""

		claimed = self.resources_claimed()

		"""
		It's possible for our processes to use more memory than the user indicated that they
		would require, but the total number of reserved cpu cores and gpus should still be
		less than the correpsonding counts in our assigned resource set.
		"""
		assert claimed.cpu_cores <= self.resource_set.cpu_cores
		assert claimed.gpus <= self.resource_set.gpus

		return ResourceSummary(
			max(0, claimed.memory_bytes - self.resource_set.memory_bytes),
			self.resource_set.cpu_cores - claimed.cpu_cores,
			self.resource_set.gpus - claimed.gpus
		)
