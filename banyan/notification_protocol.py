# -*- coding: utf-8 -*-

"""
banyan.server.notification_protocol
-----------------------------------

Definition of the protocol used by the server to send notifications to workers.
"""

import struct

cancellation_notice    = 0
deregistration_notice  = 1
resource_usage_request = 2

"""
- 16 bytes for the token sent by the server to the worker to authenticate itself.
- 1 byte for the message type.
- 16 bytes for the data associated with the message.
"""
msg_len = 33
padding = bytearray(16)

class ProtocolError(Exception):
	pass

def format_message(msg_type, request_token, data):
	if msg_type == cancellation_notice:
		msg = struct.pack('sBs', request_token.encode('utf-8'), msg_type,
			data.encode('utf-8'))
	elif msg_type in [deregistration_notice, resource_usage_request]:
		msg = struct.pack('sB', request_token.encode('utf-8'), msg_type) + padding
	else:
		raise ProtocolError("Unknown message type.")

	assert len(msg) == msg_len
	return msg

def parse_message(msg):
	if len(msg) != msg_len:
		return ProtocolError("Message must be exactly 17 bytes long.")

	token = msg[:16].decode('utf-8')
	msg_type = msg[16]

	if msg_type == cancellation_notice:
		return (token, msg_type, msg[17:].decode('utf-8'))
	elif msg_type in [deregistration_notice, resource_usage_request]:
		return (token, msg_type, None)
	else:
		raise ProtocolError("Unknown message type.")
