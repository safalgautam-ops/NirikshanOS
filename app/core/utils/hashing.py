"""File hashing utilities.

Used from Week 3 onward to hash uploaded evidence (evidence.sha256).
"""

import hashlib

CHUNK_SIZE = 65536


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        # Reads in fixed-size chunks so large evidence files don't have to
        # be loaded into memory all at once.
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
