# -*- coding: utf-8 -*-

"""
banyan.server.worker_notifier
-----------------------------

Provides the event hooks that implement the server-side functionality.
"""

import os
import sys
import signalfd
import socket
import select

from errno import EAGAIN, EWOULDBLOCK, ENOBUFS
from signal import SIGHUP, SIGINT, SIGQUIT, SIGABRT, SIGTERM
from signalfd import SFD_NONBLOCK, SFD_CLOEXEC, SIG_UNBLOCK
from select import EPOLLIN, EPOLLOUT, EPOLLERR, EPOLLRDHUP, EPOLLHUP, EPOLLONESHOT, EPOLL_CLOEXEC

from flask import request
from threading import Thread, Lock

shutdown_signals = {SIGHUP, SIGINT, SIGQUIT, SIGABRT, SIGTERM}

def close_connection(conn, how=socket.SHUT_RDWR):
	"""
	Closes ``conn`` after calling ``shutdown``, so that processes using the other end know that
	we are no longer listening.
	"""

	if conn is None:
		return

	try:
		conn.shutdown(how)
	except:
		pass

	conn.close()

class WorkerQueue:
	def __init__(self, name, conn):
		self.name             = name
		self.conn             = conn
		self.msg_queue        = []
		self.pending_shutdown = False

	def apppend(self, msg):
		self.msg_queue.append(msg)

	def drain(self):
		"""
		Sends as many messages as possible before the socket would block again. Returns the
		length of the internal message queue after this process.
		"""

		while len(self) != 0:
			msg = self.msg_queue[-1]

			try:
				self.conn.send(msg)
			except OSError as e:
				if e.errno in {EAGAIN, EWOULDBLOCK, ENOBUFS}:
					return len(self.msg_queue)
				raise

			self.msg_queue.pop()
		return 0

class WorkerNotifier:
	conn_event_bitmask = EPOLLOUT | EPOLLRDHUP | EPOLLONESHOT

	def __init__(self):
		signalfd.sigprocmask(SIG_UNBLOCK, shutdown_signals)
		self.sig_fd = signalfd.signalfd(-1, shutdown_signals, SFD_CLOEXEC | SFD_NONBLOCK)

		self.lock       = Lock()
		self.fd_to_wq   = {}
		self.name_to_fd = {}

		self.epoll = select.epoll(flags=EPOLL_CLOEXEC)
		self.epoll.register(self.sig_fd, EPOLLIN)
		Thread(target=self.poll_events).start()

	def log(msg):
		print(msg, file=sys.stderr, flush=True)

	def _name_to_wq(self, name):
		return self.fd_to_wq[self.name_to_fd[name]]

	def register(self, name, addr):
		"""
		Registers a worker so that we can send notifications to it in the future. If a
		worker with the given name is already registered with this queue, then a
		``RuntimeError`` is raised.

		Args:
			name: The name of the worker.
			addr: A tuple describing the IP address and port identifying the worker with
			name ``name``.
		"""

		try:
			conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			conn.connect(addr)
			conn.setblocking(False)

			with self.lock:
				if name in self.name_to_fd:
					raise RuntimeError("Worker '{}' is already registered.".
						format(name))

				self.epoll.register(conn, self.conn_event_bitmask)
				fd = conn.fileno()
				wq = WorkerQueue(name, conn)

				self.name_to_fd[name] = fd
				self.fd_to_wq[fd] = wq
		except:
			close_connection(conn)
			raise

	def unregister(self, name):
		"""
		Initiates the shutdown process for the message queue associated with the worker with
		name ``name``.
		"""

		with self.lock:
			if name not in self.name_to_fd:
				return

			wq = self._name_to_wq(name)
			wq.pending_shutdown = True
			self.epoll.modify(wq.conn, self.conn_event_bitmask)

	def notify(self, name, msg):
		with self.lock:
			if name not in self.name_to_fd or self._name_to_wq(name).pending_shutdown:
				return False

			wq = self._name_to_wq(name)
			wq.append(msg)
			self.epoll.modify(wq.conn, self.conn_event_bitmask)

	def _shutdown_queue(self, wq):
		close_connection(wq.conn)
		self.fd_to_wq.pop(wq.conn.fileno())
		self.name_to_fd.pop(wq.name)

	def _check_queue(self, fd, event):
		if event & (EPOLLOUT | EPOLLERR | EPOLLRDHUP | EPOLLHUP):
			wq = self.fd_to_wq[fd]
			assert fd == wq.conn.fileno()

			try:
				rem = wq.drain()
			except OSError as e:
				self.log("Error notifying worker '{}': {}".format(wq.name, repr(e)))
				self._shutdown_queue(wq)
				# TODO cancel all tasks claimed by this worker

			if rem == 0 and not wq.pending_shutdown:
				return
			elif rem == 0 and wq.pending_shutdown:
				self._shutdown_queue(wq)
			elif rem != 0:
				self.epoll.modify(fd, self.conn_event_bitmask)
		else:
			self.log("Unexpected event {:#x} for connection FD.".format(event))
			return

	def _shutdown(self):
		self.epoll.close()
		os.close(self.sig_fd)

		for wq in self.fd_to_wq.values():
			close_connection(wq.conn)

		request.environ.get('werkzeug.server.shutdown')()

	def _check_signal(self, event):
		if event & EPOLLIN:
			info = signalfd.read_siginfo(self.sig_fd)
			sig = info.ssi_signo

			if sig not in shutdown_signals:
				self.log("Unexpected signal {}.".format(sig))
			else:
				self.log("Terminated by signal {}.".format(sig))
				self._shutdown()
		else:
			self.log("Unexpected event {:#x} for signal FD.".format(event))

	def _process_event(self, fd, event):
		if fd in self.fd_to_wq:
			self._check_queue(fd, event)
		elif fd == self.sig_fd:
			self._check_signal(event)

	def _poll_events(self):
		while True:
			events = self.epoll.poll()

			with self.lock:
				for fd, event in events:
					self._process_event(fd, event)
