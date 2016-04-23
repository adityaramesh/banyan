# -*- coding: utf-8 -*-

"""
banyan.server.worker_availability_checker
-----------------------------------------

Periodically checks that each worker in the set of registered workers is available. If we find that
a given worker is no longer available, then we proceed to unregister it.
"""

import time

from datetime import datetime
from timeit import default_timer as timer
from threading import Thread
from flask import current_app as app

from config.settings import usage_update_poll_period 
from banyan.notification_protocol import resource_usage_request, format_message
from banyan.server.locks import registered_workers_lock
from banyan.server.mongo_common import find_by_id

class WorkerAvailabilityChecker:
	def __init__(self, notifier):
		self.notifier        = notifier
		self.db              = app.data.driver.db
		self.current_workers = set()

		Thread(target=self._poll_workers).start()

	def _notify_worker(self, _id):
		worker = find_by_id('users', _id, self.db, {'request_token': True})
		msg = format_message(resource_usage_request, worker['request_token'])
		self.notifier.notify(_id, msg)

	def _received_update(self, _id, cur_time):
		return db.execution_info.find_one({
			'worker_id': _id,
			'last_update': {'$gt': cur_time}
		}) == None

	def _poll_workers(self):
		sleep_time = usage_update_poll_period

		while True:
			cur_time = datetime.now()
			time.sleep(sleep_time)
			start = timer()

			"""
			We need to use a lock here, so that we do not try to send a notification to
			a worker before it has been registered with ``WorkerNotifier`` by the event
			hook.
			"""
			with registered_workers_lock:
				workers    = self.db.registered_workers.find()
				worker_ids = set([worker['worker_id'] for worker in workers])

				# Request newly-registered workers to send resource usage updates.
				for _id in worker_ids - self.current_workers:
					self._notify_worker(_id)

				# Check that we have received updates from workers that have already
				# been registered.
				for _id in self.current_workers & worker_ids:
					if not self._received_update(_id, cur_time):
						# TODO cancel all tasks claimed by the worker
					else:
						self._notify_worker(_id)

				self.current_workers = worker_ids

			elapsed    = end() - start()
			sleep_time = max(0, usage_update_poll_period - elapsed)
