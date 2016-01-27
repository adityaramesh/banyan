# -*- coding: utf-8 -*-

"""
Implements simple, token-based authentication schemes.
"""

from base64 import b64encode
from bson.binary import Binary
from flask import current_app as app
from eve.auth import TokenAuth

"""
Just validates the token supplied by the user.
"""
class ValidateToken(TokenAuth):
	def check_auth(self, token, allowed_roles, resource, method):
		db = app.data.driver.db
		return db.users.find_one({'token': token}, {'role': True})

"""
Validates the token supplied by the user. If the request requires write access, we enforce that the
user's role is in the `allowed_roles` list.
"""
class RestrictWriteAccess(ValidateToken):
	def check_auth(self, token, allowed_roles, resource, method):
		res = super().check_auth(token, allowed_roles, resource, method)

		if not res:
			return False
		if method in ['POST', 'PUT', 'PATCH', 'DELETE'] and res['role'] not in allowed_roles:
			return False
		return True
