# -*- coding: utf-8 -*-

"""
Starts a server that maintains a shared job queue.
"""

import os
from eve import Eve

if __name__ == '__main__':
	app = Eve()
	app.run(host='127.0.0.1', port=5000)
