#!/usr/bin/env python3
"""Entrypoint for dfir/basic-tools:1.0.

Reads /input/job_config.json, runs only backend-approved commands for the
requested modules, and writes all results under /output.

Security rules enforced here:
  - Module IDs are validated against SUPPORTED_MODULES; unknown IDs are skipped.
  - All subprocess calls use shell=False with fixed argv lists.
  - User-supplied options are validated and clamped before use.
  - No option value is ever interpolated into a shell string.
  - Errors are written to result.json; the process never crashes silently.

Output layout:
  /output/result.json                        structured summary (all modules)
  /output/<module_id>.txt                    raw tool stdout for each module
  /output/<module_id>.stderr.txt             raw tool stderr for each module
  /output/artifacts/                         reserved; empty for MVP modules
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CONFIG_PATH  = Path("/input/job_config.json")
EVIDENCE     = Path("/input/evidence")
OUTPUT_DIR   = Path("/output")

# Module IDs this image is authorised to handle.
# Any ID not in this set is skipped with a clear error in result.json.
SUPPORTED_MODULES = frozenset({
    "generic.file_identification",
    "generic.hash_calculation",
    "generic.strings_extraction",
})

# Hash type → (command, argument list) — no user values ever appear in argv.
_HASH_CMDS: dict[str, list[str]] = {
    "MD5":    ["md5sum",    str(EVIDENCE)],
    "SHA1":   ["sha1sum",   str(EVIDENCE)],
    "SHA256": ["sha256sum", str(EVIDENCE)],
    "SHA512": ["sha512sum", str(EVIDENCE)],
}
_ALLOWED_HASH_TYPES = frozenset(_HASH_CMDS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], stdout_path: Path, stderr_path: Path) -> int:
    """Run cmd with shell=False, capture stdout/stderr to files, return exit code."""
    with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
        proc = subprocess.run(cmd, shell=False, stdout=out_f, stderr=err_f)
    return proc.returncode


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def _module_paths(module_id: str) -> tuple[Path, Path]:
    safe_name = module_id.replace(".", "_").replace("/", "_")
    return (
        OUTPUT_DIR / f"{safe_name}.txt",
        OUTPUT_DIR / f"{safe_name}.stderr.txt",
    )


# ---------------------------------------------------------------------------
# Module handlers
# ---------------------------------------------------------------------------

def _run_file_identification(options: dict) -> dict:
    stdout_path, stderr_path = _module_paths("generic.file_identification")

    # Two fixed calls: human-readable description + MIME type.
    # -b (brief) suppresses the filename prefix.
    rc_desc = _run(
        ["file", "-b", str(EVIDENCE)],
        stdout_path,
        stderr_path,
    )
    mime_path = OUTPUT_DIR / "generic_file_identification_mime.txt"
    rc_mime = _run(
        ["file", "-b", "--mime-type", str(EVIDENCE)],
        mime_path,
        stderr_path,
    )

    description = _read(stdout_path).strip()
    mime_type   = _read(mime_path).strip()

    # Merge into one human-readable output file.
    stdout_path.write_text(f"Description : {description}\nMIME type   : {mime_type}\n")
    mime_path.unlink(missing_ok=True)

    overall_rc = rc_desc or rc_mime
    return {
        "status":      "success" if overall_rc == 0 else "failed",
        "exit_code":   overall_rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       None,
    }


def _run_hash_calculation(options: dict) -> dict:
    stdout_path, stderr_path = _module_paths("generic.hash_calculation")

    # Validate requested hash types against the allowed set.
    raw_types = options.get("hash_types", ["MD5", "SHA1", "SHA256"])
    if not isinstance(raw_types, list):
        raw_types = ["MD5", "SHA1", "SHA256"]
    hash_types = [h for h in raw_types if h in _ALLOWED_HASH_TYPES] or ["SHA256"]

    lines: list[str] = []
    errors: list[str] = []
    overall_rc = 0

    for hash_type in hash_types:
        cmd = _HASH_CMDS[hash_type]
        tmp_out  = OUTPUT_DIR / f"_hash_{hash_type}.tmp"
        tmp_err  = OUTPUT_DIR / f"_hash_{hash_type}.err"
        rc = _run(cmd, tmp_out, tmp_err)

        if rc == 0:
            # sha*sum output: "<hash>  <filename>" — extract just the hash
            raw = _read(tmp_out).split()[0] if _read(tmp_out).strip() else ""
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
        "status":      "success" if overall_rc == 0 else "failed",
        "exit_code":   overall_rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       "; ".join(errors) or None,
    }


def _run_strings_extraction(options: dict) -> dict:
    stdout_path, stderr_path = _module_paths("generic.strings_extraction")

    # Clamp min_length to [4, 100] — never pass raw user input to argv.
    try:
        min_length = int(options.get("min_length", 6))
    except (TypeError, ValueError):
        min_length = 6
    min_length = max(4, min(100, min_length))

    rc = _run(
        ["strings", "-n", str(min_length), str(EVIDENCE)],
        stdout_path,
        stderr_path,
    )

    return {
        "status":      "success" if rc == 0 else "failed",
        "exit_code":   rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       None,
    }


_HANDLERS = {
    "generic.file_identification": _run_file_identification,
    "generic.hash_calculation":    _run_hash_calculation,
    "generic.strings_extraction":  _run_strings_extraction,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "artifacts").mkdir(exist_ok=True)

    # Read job config.
    try:
        config = json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        (OUTPUT_DIR / "result.json").write_text(json.dumps({
            "job_id": "unknown",
            "status": "failed",
            "error":  f"Cannot read job_config.json: {exc}",
            "modules": {},
        }, indent=2))
        sys.exit(1)

    job_id  = config.get("job_id", "unknown")
    modules = config.get("modules", [])

    if not EVIDENCE.exists():
        (OUTPUT_DIR / "result.json").write_text(json.dumps({
            "job_id": job_id,
            "status": "failed",
            "error":  "/input/evidence not found",
            "modules": {},
        }, indent=2))
        sys.exit(1)

    print(f"[analyzer] job={job_id} modules={[m.get('id') for m in modules]}")

    module_results: dict[str, dict] = {}
    overall_status = "completed"

    for entry in modules:
        module_id = entry.get("id", "")
        options   = entry.get("options") or {}

        print(f"[analyzer] running module={module_id}")

        if module_id not in SUPPORTED_MODULES:
            module_results[module_id] = {
                "status":    "skipped",
                "exit_code": None,
                "error":     f"Module '{module_id}' not supported by this image",
            }
            continue

        try:
            result = _HANDLERS[module_id](options)
        except Exception as exc:
            result = {
                "status":      "failed",
                "exit_code":   -1,
                "stdout_file": None,
                "stderr_file": None,
                "error":       str(exc),
            }

        module_results[module_id] = result
        if result.get("status") == "failed":
            overall_status = "partial"
        print(f"[analyzer] module={module_id} status={result.get('status')}")

    (OUTPUT_DIR / "result.json").write_text(json.dumps({
        "job_id":  job_id,
        "status":  overall_status,
        "modules": module_results,
    }, indent=2))

    print(f"[analyzer] done status={overall_status}")
    sys.exit(0 if overall_status != "failed" else 1)


if __name__ == "__main__":
    main()
