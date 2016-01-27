# -*- coding: utf-8 -*-

"""
Script to grant/revoke authentication tokens for users and workers.
"""

from argparse import ArgumentParser
from base64 import b64encode
from random import SystemRandom
from pprint import pprint
from pymongo import MongoClient, DESCENDING

import string
import os
import sys

"""
We can't just use `os.urandom` to generate a UUID to use as the token, because the token must be
embedded in the `Authentication` header of the HTTP request. Eve automatically validtes the contents
of this header, parses its contents, and passes the token to us in the `check_auth` function. In
this process, the raw bytes in the header are decoded using UTF-8. The mapping between UTF-8 and
binary is not one-to-one, so this is a lossy process. In general, printing out the base-64 encoded
contents of the parsed header will give us a different result from the original base-64 encoded
UUID.

To avoid this problem, we instead generate a random alphanumeric string to use as the token. The
implementation here is based on the one given by Ignacio Vazquez-Abrams [here][rand_str_gen].

[rand_str_gen]: http://stackoverflow.com/a/2257449/414271
"""
def make_token():
	return ''.join(SystemRandom().choice(string.ascii_letters + string.digits + \
		string.punctuation.replace(':', '')) for _ in range(16))

def parse_args():
	ap = ArgumentParser(description="Manages access privileges for users and workers.")
	ap.add_argument('--action', type=str, choices=['add', 'remove', 'list'], required=True)
	ap.add_argument('--name',   type=str)
	ap.add_argument('--role',   type=str, choices=['user', 'worker'])

	args = ap.parse_args()
	add_or_remove = args.action in ['add', 'remove']

	if add_or_remove and not args.name:
		raise ValueError("Argument '--name' is required for '--add' or '--remove'.")
	if args.action == 'add' and not args.role:
		raise ValueError("Argument '--role' is required for '--add'.")
	return args

def ensure_indices(db):
	db.users.create_index('name', unique=True)
	db.users.create_index('token')

def add_user(name, token, role, db):
	if db.users.find_one({'name': name}):
		raise RuntimeError("User with name '{}' already exists.".format(name))
	db.users.insert({'name': name, 'token': token, 'role': role})

def remove_user(name, db):
	db.users.delete_one({'name': name})

def list_users(db):
	for u in db.users.find().sort('name', DESCENDING):
		username = u['token'] + ':'
		u['authorization key'] = b64encode(username.encode()).decode('utf-8')
		pprint(u)

if __name__ == '__main__':
	args = parse_args()
	db = MongoClient().banyan
	ensure_indices(db)

	if args.action == 'add':
		add_user(args.name, make_token(), args.role, db)
	elif args.action == 'remove':
		remove_user(args.name, db)
	elif args.action == 'list':
		list_users(db)
