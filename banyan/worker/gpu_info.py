# -*- coding: utf-8 -*-

"""
banyan.worker.gpu_info
----------------------

Overview
--------

Wrapper around PyNVML library (available from pip) that returns various GPU
usage statistics. If ``pynvmlInit`` fails due to the shared library not being
found, we assume that the machine does not have any available GPUs (as this
implies that ``nvidia-smi`` would not work either).

Note about installation: 7.352.0 of the library has a stray print statement
without parenthesis that causes the Python 3 interpreter to error out.
Otherwise, the code is compatible with Python 3. If you experience this problem
after installing, then find this line and comment it out.

Design Decisions
----------------

Only information that is provided by both Tesla and non-Tesla GPUs is reported
to the server.  Otherwise, we would have to change what is being sent based on
the GPU model, and tools that rely on information only available from Tesla
GPUs will not work on Titan GPUs. Distributed applications that require this
information in order to coordinate communications are tasked with obtaining
this information on their own, rather than from Banyan.

As an example, only a Tesla GPU can provide a list of running processes, along
with compute and memory utilization rates for each process.

Development Notes
-----------------

Relevant functions from NVML API:
- nvmlDeviceGetCount
- nvmlDeviceGetName
- nvmlDeviceGetMemoryInfo

- nvmlDeviceGetComputeRunningProcesses (probably not worth implementing support
  for this, since only Tesla GPUs supply this information)
- nvmlDeviceGetUtilizationRates (probably not worth implementing support for
  this, since only Tesla GPUs supply this information)

Functions useful for applications that require access to the system topology:
- nvmlDeviceGetPciInfo
- nvmlDeviceOnSameBoard
"""

import atexit
from functools import total_ordering

from pynvml import *
import pycuda.autoinit
import pycuda.driver as cuda

gpus = []

@total_ordering
class ComputeCapability:
	def __init__(self, major, minor):
		assert isinstance(major, int)
		assert isinstance(minor, int)
		self.major = major
		self.minor = minor

	def __str__(self):
		return major + '.' + minor

	def __eq__(self, other):
		return major == other.major and minor == other.minor

	def __lt__(self, other):
		return (major, minor) < (other.major, other.minor)

def is_idle_performance_state(state):
	"""
	Non-Tesla GPUs do not expose an interface that allows us to determine
	if any applications are running. As a proxy, we check whether the
	performance state is high (between 0 and 2). In theory, this method is
	falliable (e.g., quering the performance state could cause the GPU to
	jump to a higher performance state), but in practice it has been a
	reliable indicator.

	The performance state must be between 0 and 15, inclusive. On the
	compute clusters that I use, idle GPUs are put in performance state 8.
	"""
	assert state >= 0 and state <= 15
	return state <= 2

def initializeGPUInfo():
	for i in range(nvmlDeviceGetCount()):
		handle     = nvmlDeviceGetHandleByIndex(i)
		mem_info   = nvmlDeviceGetMemoryInfo(handle)
		perf_state = nvmlDeviceGetPerformanceState(handle)
		dev        = cuda.Device(i)
		cc         = ComputeCapability(dev.compute_capability_major,
				dev.compute_capability_minor)

		gpus.append({
			'handle':                 handle,
			'name':                   nvmlDeviceGetName(handle),
			'compute_capability':     cc,
			'total_memory_bytes':     mem_info.total,
			'free_memory_bytes':      mem_info.free,
			'available_memory_bytes': mem_info.available,
			'performance_state':      perf_state,
			'is_idle':                is_idle_performance_state(perf_state)
		})

def updateGPUInfo():
	for gpu in gpus:
		handle     = gpu['handle']
		mem_info   = nvmlDeviceGetMemoryInfo(handle)
		perf_state = nvmlDeviceGetPerformanceState(handle)

		gpu['free_memory_bytes']      = mem_info.free
		gpu['available_memory_bytes'] = mem_info.available
		gpu['performance_state']      = perf_state
		gpu['is_idle']                = is_idle_performance_state(perf_state)

try:
	nvmlInit()
except NVMLError_LibraryNotFound:
	initializeGPUInfo()
else:
	atexit.register(nvmlShutdown())
