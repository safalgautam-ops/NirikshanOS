"""Handler for generic.hash_calculation.

Runs one hash command per selected hash type and merges the results.
Multi-command fan-out with per-type output normalization requires custom
Python; a single-command YAML definition cannot express this.
"""
from __future__ import annotations

from pathlib import Path

from utils import output_paths, read_file, run_cmd

MODULE_ID = "generic.hash_calculation"

_EVIDENCE = Path("/input/evidence")

_HASH_CMDS: dict[str, list[str]] = {
    "MD5":    ["md5sum",    str(_EVIDENCE)],
    "SHA1":   ["sha1sum",   str(_EVIDENCE)],
    "SHA256": ["sha256sum", str(_EVIDENCE)],
    "SHA512": ["sha512sum", str(_EVIDENCE)],
}
_ALLOWED_HASH_TYPES = frozenset(_HASH_CMDS)


def run(options: dict, output_dir: Path) -> dict:
    stdout_path, stderr_path = output_paths(MODULE_ID, output_dir)

    raw_types = options.get("hash_types", ["MD5", "SHA1", "SHA256"])
    if not isinstance(raw_types, list):
        raw_types = ["MD5", "SHA1", "SHA256"]
    # Only keep types that exist in _HASH_CMDS; fall back to SHA256 if nothing valid.
    hash_types = [h for h in raw_types if h in _ALLOWED_HASH_TYPES] or ["SHA256"]

    lines: list[str] = []
    errors: list[str] = []
    overall_rc = 0

    for hash_type in hash_types:
        tmp_out = output_dir / f"_hash_{hash_type}.tmp"
        tmp_err = output_dir / f"_hash_{hash_type}.err"
        rc = run_cmd(_HASH_CMDS[hash_type], tmp_out, tmp_err)

        if rc == 0:
            # sha*sum prints "<hash>  <filename>" — extract only the hash.
            raw = read_file(tmp_out).split()[0] if read_file(tmp_out).strip() else ""
            lines.append(f"{hash_type}: {raw}")
        else:
            errors.append(f"{hash_type} failed (exit {rc})")
            overall_rc = rc

        tmp_out.unlink(missing_ok=True)
        tmp_err.unlink(missing_ok=True)

    stdout_path.write_text("\n".join(lines) + "\n")
    if errors:
        stderr_path.write_text("\n".join(errors) + "\n")

    return {
        "status": "success" if overall_rc == 0 else "failed",
        "exit_code": overall_rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error": "; ".join(errors) or None,
    }
