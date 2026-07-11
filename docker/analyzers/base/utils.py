"""Shared helpers used by loader.py and embedded module scripts."""
from __future__ import annotations

import subprocess
from pathlib import Path


def run_cmd(
    cmd: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int | None = None,
    stdin_path: Path | None = None,
) -> int:
    """Run cmd with shell=False. Writes stdout/stderr to files. Returns exit code.

    Pass stdin_path to feed a file as stdin (used by the pipe step in loader.py
    to avoid holding the first command's output in memory).
    Raises subprocess.TimeoutExpired if timeout is set and exceeded.
    """
    stdin_f = stdin_path.open("rb") if stdin_path else None
    try:
        with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
            proc = subprocess.run(
                cmd, shell=False,
                stdin=stdin_f,
                stdout=out_f,
                stderr=err_f,
                timeout=timeout,
            )
        return proc.returncode
    finally:
        if stdin_f:
            stdin_f.close()


def read_file(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def output_paths(module_id: str, output_dir: Path) -> tuple[Path, Path]:
    safe = module_id.replace(".", "_").replace("/", "_")
    return output_dir / f"{safe}.txt", output_dir / f"{safe}.stderr.txt"
