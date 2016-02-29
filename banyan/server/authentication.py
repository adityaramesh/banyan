# -*- coding: utf-8 -*-

"""
banyan.server.authentication
----------------------------

Implements a simple, token-based authentication scheme. See ``banyan/auth/access.py`` for more
information.
"""

from flask import g, current_app as app
from eve.auth import TokenAuth as TokenAuthBase
from eve.utils import config

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

		"""
		XXX For some reason, Eve never seems to add the user's role to ``allowed_roles``
		when the method is DELETE. A superficial search over the Eve codebase didn't bring
		up anything useful, so I'm resorting to a hack for now.
		"""
		if method == 'DELETE':
			extra_roles = app.config['DOMAIN'][resource].get('allowed_write_roles')
			allowed_roles = allowed_roles + extra_roles

		if not res or res['role'] not in allowed_roles:
			return False

		"""
		We only perform partial validation of the worker credentials here. Additional
		validation is performed in the validator.
		"""
		if resource == 'tasks' and res['role'] == 'worker':
			user_info = db.registered_users.find_one({config.ID_FIELD: res['_id']},
				projection={'roles': True})
			if not user_info or len(user_info['roles']) == 0:
				return False

			g.user_info = info

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
