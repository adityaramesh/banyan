# -*- coding: utf-8 -*-

"""
banyan.worker.resource_info
---------------------------

Provides information about the resources available for use on this machine, taking into account the
restrictions specified by the user in ``settings.py``.
"""

from cerberus import Validator
from collections import namedtuple
import math
import psutil

from banyan.worker.schema import usage_limits_schema
import banyan.worker.settings as settings
import banyan.worker.gpu_info as gpu_info

class ValidationError(Exception):
	def __init__(self, var_name, errors):
		super().__init__("Encountered errors while validating '{}': {}".format(var_name,
			str(errors)))

def get_usage_limits():
	usage_limits = getattr(settings, 'usage_limits', None) or {}

	"""
	Unfortunately, Cerberus does not implement the 'default' rule, so we have to fill in the
	default values on our own before validation. We could try to use Eve, but the default values
	are not filled in by ``eve.mongo.io.Validator``. I don't want to waste time rummaging
	through the source code in order to find out where this happens.
	"""

	if 'memory' not in usage_limits:
		usage_limits['memory'] = {}
	if 'min_unused_percent' not in usage_limits['memory']:
		usage_limits['memory']['min_unused_percent'] = 0.0
	if 'min_unused_bytes' not in usage_limits['memory']:
		usage_limits['memory']['min_unused_bytes'] = 0

	if 'cores' not in usage_limits:
		usage_limits['cores'] = {}
	if 'min_unused_count' not in usage_limits['cores']:
		usage_limits['cores']['min_unused_count'] = 0

	if 'gpus' not in usage_limits:
		usage_limits['gpus'] = {}
	if 'min_unused_count' not in usage_limits['gpus']:
		usage_limits['gpus']['min_unused_count'] = 0

	v = Validator(usage_limits_schema)
	if not v.validate(usage_limits):
		raise ValidationError('usage_limits')
	return usage_limits

usage_limits = get_usage_limits()

ResourceSummaryBase = namedtuple('ResourceUsage', ['memory_bytes', 'cpu_cores', 'gpus'])

class ResourceSummary(ResourceSummaryBase):
	def __new__(cls, memory_bytes=0, cpu_cores=0, gpus=0):
		self = super().__new__(cls, memory_bytes, cpu_cores, gpus)
		return self

	def __add__(self, other):
		return ResourceSummary(
			memory_bytes=self.memory_bytes + other.memory_bytes,
			cpu_cores=self.cpu_cores + other.cpu_cores,
			gpus=self.gpus + other.gpus
		)

def total_resources():
	"""
	Returns the total system resources, adjusted according to the resource usage limits
	specified in ``settings.py``.
	"""

	avail_memory  = psutil.virtual_memory().available
	min_mem_bytes = usage_limits['memory']['min_unused_bytes']
	min_mem_ratio = usage_limits['memory']['min_unused_percent'] / 100
	usable_memory = max(avail_memory - min_mem_bytes, avail_memory -
		math.ceil(min_mem_ratio * avail_memory))

	total_cores = psutil.cpu_count()
	avail_cores = max(0, total_cores - usage_limits['cores']['min_unused_count'])

	total_gpus = len(gpu_info.gpus)
	avail_gpus = max(0, total_gpus - usage_limits['gpus']['min_unused_count'])

	return ResourceSummary(memory_bytes=usable_memory, cpu_cores=avail_cores, gpus=avail_gpus)
