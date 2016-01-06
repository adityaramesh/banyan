# -*- coding: utf-8 -*-

"""
Starts a job queue server.
"""

import os
import sys
import socket
from eve import Eve

from validation import Validator
from event_hooks import EventHooks

def get_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)
	hooks = EventHooks(app)
	app.run(host=get_ip(), port=5000)
