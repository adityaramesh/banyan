# -*- coding: utf-8 -*-

"""
test.test_worker
------------------

Tests functionality that is implemented completely on the worker-side.
"""

import unittest

# Allows us to import the 'banyan' module.
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))

from banyan.worker.task import Task
from banyan.worker.executor import Executor
from banyan.worker.resource_info import ResourceSummary

import banyan.worker.resource_info as resource_info

class TestExecutor(unittest.TestCase):
	def __init__(self, *args, **kwargs):
		self.total_res = ResourceSummary(memory_bytes=4 * 2 ** 30, cpu_cores=4, gpus=0)
		self.req_res = {
			'cpu_memory_bytes': 128 * 2 ** 20,
			'cpu_cores': {'count': 0, 'percent': 0.0},
			'gpu_count': 0
		}
		super().__init__(*args, **kwargs)

	def test_single_task(self):
		e = Executor(self.total_res)

		t = Task('ls', requested_resources=self.req_res, estimated_runtime=1000.,
			max_shutdown_time=10.)
		e.submit(t)

		while len(e.running) != 0:
			e.poll()

		self.assertEqual(e.terminated[0].status(), 0)

	def test_multiple_tasks(self):
		e = Executor(self.total_res)

		for _ in range(50):
			t = Task('ls', requested_resources=self.req_res, estimated_runtime=1000.,
				max_shutdown_time=10.)
			e.submit(t)

		while len(e.running) != 0:
			e.poll()

		for t in e.terminated:
			self.assertEqual(t.status(), 0)

if __name__ == '__main__':
	unittest.main()
