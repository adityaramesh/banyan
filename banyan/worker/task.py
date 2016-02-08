# -*- coding: utf-8 -*-

"""
banyan.worker.task
------------------

Implementation of shell command as runnable task.
"""

from collections import namedtuple

from datetime import datetime
from timeit import default_timer as timer

from subprocess import Popen
from psutil import Process

TaskResourceUsage = namedtuple('TaskResourceUsage', [
	'resident_memory_bytes',
	'virtual_memory_bytes',
	'cpu_utilization_percent'
])

class Task:
	def __init__(self, command, requested_resources, estimated_runtime, max_termination_time):
		assert command is not None
		assert isinstance(command, str)
		assert isinstance(estimated_runtime, float)
		assert isinstance(max_termination_time, float)
		assert isinstance(requested_resources['cpu_utilization_percent'], float)
		assert isinstance(requested_resources['memory'], int)

		self.command              = command
		self.requested_resources  = requested_resources
		self.estimated_runtime    = estimated_runtime
		self.max_termination_time = max_termination_time
		self.waiting_for_sigterm  = False

	def run(self):
		self.proc = Popen(self.command, shell=True)
		self.proc_info = Process(self.proc.pid)
		self.time_started = datetime.now()

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

		return TaskResourceUsage(
			resident_memory_bytes=mem[0],
			virtual_memory_bytes=mem[1],
			cpu_utilization_percent=info.cpu_percent()
		)
