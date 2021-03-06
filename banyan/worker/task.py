# -*- coding: utf-8 -*-

"""
banyan.worker.task
------------------

Implementation of shell command as runnable task.
"""

import re
import math
from collections import namedtuple

from datetime import datetime
from timeit import default_timer as timer

from subprocess import Popen, DEVNULL
from psutil import Process

from banyan.worker.resource_info import ResourceSummary

ResourceUsageBase = namedtuple('ResourceUsageBase', ['resident_memory_bytes', 'cpu_cores', 'gpus'])

class ResourceUsage(ResourceUsageBase):
	def __new__(cls, resident_memory_bytes=0, virtual_memory_bytes=0,
		cpu_utilization_percent=0.):

		self = super().__new__(cls, resident_memory_bytes, virtual_memory_bytes,
			cpu_utilization_percent)
		return self

	def __add__(self, other):
		return ResourceUsage(
			resident_memory_bytes=self.resident_memory_bytes +
				other.resident_memory_bytes,
			virtual_memory_bytes=self.virtual_memory_bytes +
				other.virtual_memory_bytes,
			cpu_utilization_percent=self.cpu_utilization_percent +
				other.cpu_utilization_percent,
		)

def reserved_resources(requested_resources, resource_set):
	"""
	Given the ``requested_resources`` field associated with a given task, this function
	determines the actual number of resources that ought to be reserved on this machine for that
	task.

	Args:
		requested_resources: See description above.
		resource_set: Subset of system resources that we are allowed to use.
	"""

	req_memory     = requested_resources['cpu_memory_bytes']
	min_core_count = requested_resources['cpu_cores']['count']
	min_core_ratio = requested_resources['cpu_cores']['percent'] / 100
	gpus           = requested_resources['gpu_count']

	total_mem   = resource_set.memory_bytes
	total_cores = resource_set.cpu_cores
	total_gpus  = resource_set.gpus

	"""
	We should have only claimed this job if sufficient resources exist on this system.
	"""
	assert req_memory     <= total_mem
	assert min_core_count <= total_cores
	assert gpus           <= total_gpus

	return ResourceSummary(
		memory_bytes=req_memory,
		cpu_cores=max(min_core_count, math.ceil(min_core_ratio * total_cores)),
		gpus=gpus
	)

class Task:
	def __init__(self, command, requested_resources, estimated_runtime, max_shutdown_time):
		assert command is not None
		assert isinstance(command, str)
		assert isinstance(estimated_runtime, float)
		assert isinstance(max_shutdown_time, float)

		self.command             = command
		self.requested_resources = requested_resources
		self.estimated_runtime   = estimated_runtime
		self.max_shutdown_time   = max_shutdown_time
		self.waiting_for_sigterm = False

	def run(self, resource_set):
		self.proc = Popen(self.command, shell=True, stdout=DEVNULL, stderr=DEVNULL)
		self.proc_info = Process(self.proc.pid)
		self.time_started = datetime.now()
		self.reserved_resources = reserved_resources(self.requested_resources, resource_set)

		# When used asychronously, ``cpu_percent`` uses the time since
		# the last call as the polling interval. Hence, the first call
		# will always return 0. To ensure that ``usage`` reports useful
		# information, we call this function in advance.
		self.proc_info.cpu_percent()

	def cancel(self):
		if self.sent_sigterm:
			return

		self.terminate()
		self.sigterm_start = timer()
		self.waiting_for_sigterm = True

	def status(self):
		if self.proc.poll() is not None:
			self.time_terminated = datetime.now()
			return self.proc.returncode

		if not self.waiting_for_sigterm:
			return

		if timer() - self.sigterm_start > self.max_shutdown_time:
			self.proc.kill()
			self.waiting_for_sigterm = False

	def usage(self):
		info = self.proc_info
		mem = info.memory_info()

		return ResourceUsage(
			resident_memory_bytes=mem[0],
			virtual_memory_bytes=mem[1],
			cpu_utilization_percent=info.cpu_percent()
		)
