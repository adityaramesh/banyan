# -*- coding: utf-8 -*-

"""
Implements simple, token-based authentication schemes.
"""

from base64 import b64encode
from bson.binary import Binary
from flask import current_app as app
from eve.auth import TokenAuth

class TokenAuth(TokenAuth):
	def check_auth(self, token, allowed_roles, resource, method):
		db = app.data.driver.db
		res = db.users.find_one({'token': token}, {'role': True})

		if not res or res['role'] not in allowed_roles:
			return False
		return True

class RestrictCreationToUsers(TokenAuth):
	def check_auth(self, token, allowed_roles, resource, method):
		db = app.data.driver.db
		res = db.users.find_one({'token': token}, {'role': True})

		if not res or (method == 'POST' and res['role'] != 'user'):
			return False
		return True
