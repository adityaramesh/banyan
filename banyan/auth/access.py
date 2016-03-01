# -*- coding: utf-8 -*-

"""
banyan.auth.access
------------------

Script to manage authentication tokens for users.
"""

from argparse import ArgumentParser
from pprint import pprint
from pymongo import MongoClient, DESCENDING

# Allows us to import the 'banyan' module.
import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '../..'))

from banyan.common import make_token, authorization_key

def parse_args():
	ap = ArgumentParser(description="Manages access privileges for users and workers.")
	ap.add_argument('--action', type=str, choices=['add', 'remove', 'list'], required=True)
	ap.add_argument('--name',   type=str)
	ap.add_argument('--role',   type=str, choices=['provider', 'worker'])

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

def add_provider(name, request_token, db):
	if db.users.find_one({'name': name}):
		raise RuntimeError("User with name '{}' already exists.".format(name))

	return db.users.insert({
		'name': name,
		'request_token': request_token,
		'role': 'provider'
	})

def add_worker(name, request_token, response_token, db):
	"""
	Args:
		request_token: Used by the server to validate the authenticity of an update from a
			worker.
		response_token: Used by the worker to determine whether a server attempting to
			esablish a connection with it is authorized to do so.
	"""

	if db.users.find_one({'name': name}):
		raise RuntimeError("User with name '{}' already exists.".format(name))

	return db.users.insert({
		'name': name,
		'response_token': response_token,
		'request_token': request_token,
		'role': 'worker'
	})

def remove_user(name, db):
	"""
	Note: this function should work even if the specified user does not exist in the database.
	``test_server.py`` expects this behavior from this function.
	"""

	db.users.delete_one({'name': name})

def list_users(db):
	for u in db.users.find().sort('name', DESCENDING):
		u['authorization_key'] = authorization_key(u['request_token'])
		pprint(u)

if __name__ == '__main__':
	args = parse_args()
	db = MongoClient().banyan
	ensure_indices(db)

	if args.action == 'add':
		if args.role == 'provider':
			add_provider(args.name, make_token(), db)
		else:
			add_worker(args.name, make_token(), make_token(), db)
	elif args.action == 'remove':
		remove_user(args.name, db)
	elif args.action == 'list':
		list_users(db)
