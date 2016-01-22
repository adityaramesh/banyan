# -*- coding: utf-8 -*-

"""
Starts a job queue server.
"""

import os
import sys
import socket
from eve import Eve

from virtual_resources import blueprints
from validation import Validator
from event_hooks import EventHooks

def get_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)

	"""
	We need to "bind" to the current app context, because many Flask global
	variables are actually proxies to variables that are local to the
	current concurrency context (e.g. thread). For the same reason, each
	request is also associated with its own context.
	"""
	with app.app_context():
		hooks = EventHooks()
		for blueprint in blueprints:
			app.register_blueprint(blueprint)
		app.run(host=get_ip(), port=5000)
