# -*- coding: utf-8 -*-

"""
banyan.server.authentication
----------------------------

Implements a simple, token-based authentication scheme. See ``banyan/auth/access.py`` for more
information.
"""

from flask import g, current_app as app
from eve.auth import TokenAuth as TokenAuthBase

class TokenAuth(TokenAuthBase):
	def check_auth(self, token, allowed_roles, resource, method):
		db = app.data.driver.db
		res = db.users.find_one({'request_token': token}, {'role': True})

		"""
		Save the token and associated user, in case they will be needed later during
		validation or processing.
		"""
		g.token = token
		g.user = res

		if not res or res['role'] not in allowed_roles:
			return False
		return True

class RestrictCreationToProviders(TokenAuthBase):
	def check_auth(self, token, allowed_roles, resource, method):
		db = app.data.driver.db
		res = db.users.find_one({'request_token': token}, {'role': True})

		"""
		Save the token and associated user, in case they will be needed later during
		validation or processing.
		"""
		g.token = token
		g.user = res

		if not res or (method == 'POST' and res['role'] != 'provider'):
			return False
		return True
