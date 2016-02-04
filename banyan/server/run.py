# -*- coding: utf-8 -*-

"""
banyan.server.run
-----------------

Starts an instance of the Banyan application.
"""

import os
import sys
import socket
from eve import Eve

from validation import Validator
from virtual_blueprints import blueprints
#from event_hooks import EventHooks

def get_public_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)

	# TODO register_event_hooks()
	for blueprint in blueprints:
		app.register_blueprint(blueprint)
	app.run(host=get_public_ip(), port=5000)
