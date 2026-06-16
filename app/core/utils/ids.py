"""ID generation for BetterAuth-style tables.

The `user`/`session`/`account`/`passkey`/`twoFactor` tables (see
migrations/001.initial_schema.sql) use varchar(191) primary keys assigned
by the application, not auto-increment ints - so every INSERT into one of
these tables needs an id generated up front.

Generate it in code, you can reference across multiple related inserts (user-->account-->session) in one transaction

A UUID is a 128-bit identifier. Version 4 means it's generated from random bits rather than from a timestamp, MAC address, or name.
Of the 128 bits, 6 are fixed to mark the version and variant, leaving 122 random bits.
"""

import uuid


def new_id() -> str:
    # uuid.uuid4() returns a UUID object;
    # .hex renders it as a 32-character lowercase hex string with no dashes since each hex character encodes exactly 4 bits
    # 3f8a1c2e9b4d4f7a8c1e2d3b4a5f6789
    return uuid.uuid4().hex
