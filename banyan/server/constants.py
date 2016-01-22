# -*- coding: utf-8 -*-

"""
Defines constants used by the schema.
"""

"""
When the user POSTs to a virtual subresource, it is understood that all of the
requested updates are to made in one atomic transaction. The `Mongo` data layer
provided by Eve doesn't implement this functionality. Instead, we use the
following steps:
  1. Validate the JSON array of updates.
  2. Use the JSON array to construct one large batch update operation.
  3. Execute the update operation.

The problem here is that MongoDB imposes a limit of 16 Mb on any BSON document.
So the update will be invalid if it is too large. To ensure that this doesn't
happen, we restrict the sizes of the following:
  1. The number of updates in the JSON array.
  2. The size of the 'targets' and 'updates' lists for each update.

We assume that the maximum size of any element in the 'target' or 'updates'
list is 128 bytes. With the constants as defined below, the maximum update size
is precisely 16 Mb. Atomic updates larger than this cannot be made.
"""
max_item_list_length = 1024
max_update_list_length = 128

max_name_string_length = 256
max_command_string_length = 1024

memory_regex = r'^(0|[1-9][0-9]*) (byte|bytes|KiB|MiB|GiB|TiB)'
max_memory_string_length = 32

time_regex = r'[1-9][0-9]*(.[0-9]*)? (second|minute|hour)s?'
max_time_string_length = 32
