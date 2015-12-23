# -*- coding: utf-8 -*-

"""
Starts a server that maintains a shared job queue.
"""

import os
import socket
from eve import Eve

def get_ip():
	return socket.gethostbyname(socket.gethostname())

if __name__ == '__main__':
	app = Eve()
	app.run(host=get_ip(), port=5000)
