"""Shared helpers used by both the YAML loader and Python plugin modules."""
from __future__ import annotations

import subprocess
from pathlib import Path


def run_cmd(
    cmd: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int | None = None,
) -> int:
    """Run cmd with shell=False, write stdout/stderr to files, return exit code.

    Raises subprocess.TimeoutExpired (caught by the caller) if timeout is set
    and the process exceeds it.
    """
    with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
        proc = subprocess.run(
            cmd, shell=False, stdout=out_f, stderr=err_f, timeout=timeout
        )
    return proc.returncode


def read_file(path: Path) -> str:
    """Read a text file safely; return empty string if it doesn't exist."""
    return path.read_text(errors="replace") if path.exists() else ""


def output_paths(module_id: str, output_dir: Path) -> tuple[Path, Path]:
    """Return (stdout_path, stderr_path) for a module's output files."""
    safe = module_id.replace(".", "_").replace("/", "_")
    return output_dir / f"{safe}.txt", output_dir / f"{safe}.stderr.txt"
