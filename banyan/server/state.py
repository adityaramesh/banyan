# -*- coding: utf-8 -*-

"""
banyan.server.state
-------------------

Defines legal state transitions for API users.
"""

legal_provider_transitions = {
	'inactive':             ['cancelled', 'available'],
	'available':            ['cancelled'],

	# Note: when a user attempts to change the state of a running task to `cancelled`, the
	# server first puts the task in the `pending_cancellation` state, and then goes through the
	# procedures described in the specification.
	'running':              ['pending_cancellation'],
	'pending_cancellation': [],
	'cancelled':            [],
	'terminated':           []
}

legal_worker_transitions = {
	'inactive':             [],
	'available':            ['running'],
	'running':              ['terminated'],
	'pending_cancellation': ['cancelled', 'terminated'],
	'cancelled':            [],
	'terminated':           []
}

legal_transitions = {}
for si, sf_1 in legal_provider_transitions.items():
	sf_2 = legal_worker_transitions[si]
	legal_transitions[si] = sf_1 + sf_2
