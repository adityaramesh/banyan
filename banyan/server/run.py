# -*- coding: utf-8 -*-

"""
Starts a server that maintains a shared job queue.
"""

import os
import sys
import socket
from eve import Eve
from validation import Validator

def get_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve(validator=Validator)
	# on_insert_tasks
	app.run(host=get_ip(), port=5000)
