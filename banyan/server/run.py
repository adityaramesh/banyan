# -*- coding: utf-8 -*-

"""
banyan.server.run
-----------------

Starts an instance of the Banyan application.
"""

from eve import Eve
import socket

from validation import Validator
from virtual_blueprints import blueprints
import event_hooks

def get_public_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)
	event_hooks.register(app)

	for blueprint in blueprints:
		app.register_blueprint(blueprint)

	app.run(host=get_public_ip(), port=5000)
