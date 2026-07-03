"""Parser for generic.hash_calculation (tool: hashdeep / sha256sum).

Handles two output shapes:
  - Key-value  "SHA256: abc123..."  (sha256sum / md5sum style)
  - hashdeep   "size,hash,filename"  (hashdeep -c sha256,md5 output)
"""

from __future__ import annotations

import re

# Matches "SHA256: abc...", "MD5: abc...", "SHA-1: abc...", etc.
_KV_RE = re.compile(
    r"^(sha[-_]?(?:256|512|1|384)|md5|sha)\s*[=:]\s*([a-f0-9]{16,})",
    re.IGNORECASE | re.MULTILINE,
)

# hashdeep line: "size,hash1,hash2,...,filename"
# We only care about the hash columns; size and filename are ignored here.
_HASHDEEP_HASH_RE = re.compile(r"\b([a-f0-9]{32,})\b", re.IGNORECASE)

_HASH_SIZE_TO_NAME = {32: "md5", 40: "sha1", 56: "sha224", 64: "sha256", 96: "sha384", 128: "sha512"}


def _normalise_key(raw: str) -> str:
    return raw.upper().replace("-", "").replace("_", "")


def parse(stdout: str, stderr: str, exit_code: int) -> dict:
    hashes: dict[str, str] = {}

    # Key-value style first
    for match in _KV_RE.finditer(stdout):
        key  = _normalise_key(match.group(1))
        val  = match.group(2).lower()
        hashes[key] = val

    # Fall back to hashdeep if nothing found yet
    if not hashes:
        for line in stdout.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            for m in _HASHDEEP_HASH_RE.finditer(line):
                h   = m.group(1).lower()
                key = _HASH_SIZE_TO_NAME.get(len(h))
                if key and key.upper() not in hashes:
                    hashes[key.upper()] = h

    return {
        "summary": hashes,
        "iocs":    [],
        "findings": [],
        "artifacts": [],
    }
