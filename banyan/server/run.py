# -*- coding: utf-8 -*-

"""
banyan.server.run
-----------------

Starts an instance of the Banyan application.
"""

from eve import Eve
import socket

# Gives us access to the module hierarchy.
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '../..'))

from banyan.server.validation import Validator
from banyan.server.virtual_blueprints import blueprints
import banyan.server.event_hooks as event_hooks

from config.settings import banyan_port

def get_public_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)
	event_hooks.register(app)

	for blueprint in blueprints:
		app.register_blueprint(blueprint)

	app.run(host=get_public_ip(), port=banyan_port)
