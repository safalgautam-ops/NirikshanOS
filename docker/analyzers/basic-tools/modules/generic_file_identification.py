"""Handler for generic.file_identification.

Runs two file(1) calls — human-readable description and MIME type — then
merges them into one output file. This needs custom Python because it runs
two commands and combines their output; a single-command YAML definition
cannot express that.
"""
from __future__ import annotations

from pathlib import Path

from utils import output_paths, read_file, run_cmd

MODULE_ID = "generic.file_identification"

_EVIDENCE = Path("/input/evidence")


def run(options: dict, output_dir: Path) -> dict:
    stdout_path, stderr_path = output_paths(MODULE_ID, output_dir)

    rc_desc = run_cmd(["file", "-b", str(_EVIDENCE)], stdout_path, stderr_path)

    mime_tmp = output_dir / "_file_mime.tmp"
    rc_mime = run_cmd(["file", "-b", "--mime-type", str(_EVIDENCE)], mime_tmp, stderr_path)

    description = read_file(stdout_path).strip()
    mime_type = read_file(mime_tmp).strip()

    stdout_path.write_text(f"Description : {description}\nMIME type   : {mime_type}\n")
    mime_tmp.unlink(missing_ok=True)

    overall_rc = rc_desc or rc_mime
    return {
        "status": "success" if overall_rc == 0 else "failed",
        "exit_code": overall_rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error": None,
    }
