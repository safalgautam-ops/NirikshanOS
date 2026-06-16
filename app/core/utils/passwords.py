"""Password hashing.

Argon2id via argon2-cffi - the password hashing winner of the Password
Hashing Competition, and the current OWASP recommendation. Argon2id is a memory-hard hashing function.
It deliberately consumes RAM and CPU time,
so brute-forcing stolen hashes is expensive even on GPUs/ASICs.
The "id" variant blends two modes (resistance to side-channel attacks + resistance to GPU cracking).

It encodes the algorithm, version, cost parameters (memory m, iterations t, parallelism p),
the random salt, and the digest — all in one string. So you store only that string.
On verify, the salt and parameters are read back out of it; no separate salt column is needed.
"""

# PasswordHaser() -- a single resuable instance holding default cost parameters.
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# created once at module load
_hasher = PasswordHasher()


# generates a fresh random salt internally and returns the encoded hash string.
# Calling it twice on the same password yields different strings (different salts)
def hash_password(password: str) -> str:
    return _hasher.hash(password)


# re-derives the digest using the salt/params embedded in password_hash and compares it (in constant time) to the stored digest
def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:  # on mismatch(wrong password): argon2-cffi raises VerifyMismatchError rather than returning False
        # other exceptions -- InvalidHashError(malformed/corruped hash string) or VerificationError will propagate out because that is different problem than a wrong password
        return False
