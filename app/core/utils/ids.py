"""ID generation for BetterAuth-style tables.

The `user`/`session`/`account`/`passkey`/`twoFactor` tables (see
migrations/001.initial_schema.sql) use varchar(191) primary keys assigned
by the application, not auto-increment ints - so every INSERT into one of
these tables needs an id generated up front.
"""

import uuid


def new_id() -> str:
    return uuid.uuid4().hex
