"""ID generation for BetterAuth-style tables."""

import uuid


def new_id() -> str:
    return uuid.uuid4().hex
