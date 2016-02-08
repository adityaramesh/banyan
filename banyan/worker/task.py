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

from subprocess import Popen
from psutil import Process

from banyan.worker.resource_info import ResourceSummary
from banyan.server.constants import memory_regex

ResourceUsage = namedtuple('ResourceUsage', ['resident_memory_bytes', 'virtual_memory_bytes',
	'cpu_utilization_percent'])

def parse_memory_string(mem_str):
	"""
	Returns the number of bytes represented by a string matching the regex described by
	``banyan.server.constants.memory_regex``.
	"""

	mem_pat = re.compile(memory_regex)
	m = mem_pat.match(mem_str)

	assert m is not None
	assert len(m.groups()) == 2

	base = int(m.groups()[0])
	scale = {
		'byte':  1,
		'bytes': 1,
		'KiB':   2 ** 10,
		'MiB':   2 ** 20,
		'GiB':   2 ** 30,
		'TiB':   2 ** 40
	}[m.groups()[1]]

	return base * scale

def reserved_resources(requested_resources, resource_set):
	"""
	Given the ``requested_resources`` field associated with a given task, this function
	determines the actual number of resources that ought to be reserved on this machine for that
	task.

	Args:
		requested_resources: See description above.
		resource_set: Subset of system resources that we are allowed to use.
	"""

	req_memory     = parse_memory_string(requested_resources['memory'])
	min_core_count = requested_resources['cpu_cores']['count']
	min_core_ratio = requested_resources['cpu_cores']['percent'] / 100
	gpus           = len(requested_resources['gpus'])

	total_mem   = resource_set['memory_bytes']
	total_cores = resource_set['cpu_cores']
	total_gpus  = resource_set['gpus']

	"""
	We should have only claimed this job if sufficient resources exist on this system.
	"""
	assert req_memory     <= total_mem
	assert min_core_count <= total_cores
	assert gpus           <= total_gpus

	return ResourceSummary(
		total_mem=req_memory,
		total_cores=max(min_core_count, math.ceil(min_core_ratio * total_cores)),
		gpus=gpus
	)

class Task:
	def __init__(self, command, requested_resources, estimated_runtime, max_termination_time):
		assert command is not None
		assert isinstance(command, str)
		assert isinstance(estimated_runtime, float)
		assert isinstance(max_termination_time, float)

		self.command              = command
		self.requested_resources  = requested_resources
		self.estimated_runtime    = estimated_runtime
		self.max_termination_time = max_termination_time
		self.waiting_for_sigterm  = False

	def run(self, resource_set):
		self.proc = Popen(self.command, shell=True)
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

		if timer() - self.sigterm_start > self.max_termination_time:
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
