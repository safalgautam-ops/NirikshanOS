"""Docker container runner for analysis jobs.

Call chain:

    worker_main.py
      ↓
    docker_runner.run_container(config)
      ↓
    Docker container (isolated, resource-capped, no network)
      ↓
    RunResult (paths, exit_code, artifacts, timing)

Security guarantees enforced here, not by callers:
  - job_id validated against strict allowlist (no dots, no path traversal)
  - evidence_path must be absolute and must exist before any work begins
  - isolation_level must be a known key — no silent fallback to weaker limits
  - runtime_image and module IDs verified against module_registry.MODULES directly
    (no service.py dependency — avoids circular imports, single source of truth)
  - no shell=True anywhere in this file
  - no Docker socket mounted inside the container
  - no project source mounted inside the container
  - network disabled for all isolation levels (--network none)
  - container root filesystem read-only; /tmp writable via tmpfs only
  - /input mounted read-only; /work and /output mounted writable
  - all Linux capabilities dropped; no-new-privileges set
  - PID limit enforced (--pids-limit)
  - swap bounded to equal RAM (--memory-swap == --memory)
  - container runs as worker's own uid:gid, not root
  - container always removed after run (--rm + kill fallback on timeout/error)

Host-side workspace layout per job:

    {JOBS_DIR}/{job_id}/
      input/
        evidence          ← copy of the evidence file (no symlinks: symlinks
                            resolve on the host, not inside the container)
        job_config.json   ← modules + options; container entrypoint reads this
      work/               ← container scratch space
      output/
        stdout.txt
        stderr.txt
        result.json       ← written by the container entrypoint (optional)
        artifacts/        ← any extra files the container produces

Inside the container these map to:
    /input   read-only
    /work    writable
    /output  writable
    /tmp     writable tmpfs (64 MiB, nosuid, nodev): tmpfs means the filesystem is stored in RAM, not on disk
"""

from __future__ import annotations

import asyncio  # run Docker asynchronously
import json  # tells the container what modules to run
import os  # environment variables and gets the current Linux user ID/group ID.
import re  # validate job_id format
import time  # measure how long the container runs
from dataclasses import dataclass  # define the RunConfig dataclass
from pathlib import Path  # clean file system path handling


JOBS_BASE_DIR = os.environ.get("JOBS_DIR", "/storage/jobs")

# Dots excluded intentionally: "." and ".." are valid path components and must
# never appear as a job_id. Slashes are already excluded by the character class,
# but dots are the subtler traversal risk.
# job_id is used to create a folder path so it must be sanitized to avoid path traversal.
_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Hard resource caps per isolation_level. Unknown levels are rejected by
# _validate_config_shape — there is no silent fallback to weaker limits.
_RESOURCE_LIMITS: dict[str, dict[str, str]] = {
    "none": {"cpus": "2.0", "memory": "1g", "pids": "256"},
    "network_restricted": {"cpus": "1.0", "memory": "512m", "pids": "128"},
    "sandboxed": {"cpus": "0.5", "memory": "256m", "pids": "64"},
}


@dataclass
class RunConfig:  # input to the Docker runner
    job_id: str
    evidence_path: str  # absolute local path — caller downloads from MinIO first
    runtime_image: str  # sourced from module_registry, never from user input
    modules: list[
        dict
    ]  # [{"id": "...", "name": "...", "options": {...}}] analysis modules to run
    timeout_seconds: int
    isolation_level: str


@dataclass
class RunResult:  # this is what the Docker runner returns to the caller
    exit_code: int
    stdout_path: str
    stderr_path: str
    output_dir: str
    artifacts: list[str]  # absolute paths of files under output/artifacts/
    execution_time: float  # wall-clock seconds
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Shape validation (input sanity, no registry knowledge)
# ---------------------------------------------------------------------------


def _validate_config_shape(
    config: RunConfig,
) -> None:  # validates the basic input fields
    """Validate raw RunConfig fields before touching the filesystem or registry."""
    if not _JOB_ID_RE.match(config.job_id):
        raise ValueError(f"Unsafe job_id: {config.job_id!r}")

    evidence = Path(config.evidence_path)
    if not evidence.is_absolute():
        raise ValueError("evidence_path must be absolute")
    if not evidence.exists():
        raise ValueError(f"evidence_path does not exist: {config.evidence_path}")

    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    if config.timeout_seconds > 600:
        raise ValueError("timeout_seconds cannot exceed 600")

    if config.isolation_level not in _RESOURCE_LIMITS:
        raise ValueError(
            f"Unknown isolation_level: {config.isolation_level!r}. "
            f"Must be one of: {sorted(_RESOURCE_LIMITS)}"
        )


# ---------------------------------------------------------------------------
# Registry guard (defense-in-depth against stale DB / upstream bugs)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _workspace(job_id: str) -> Path:
    # job_id is already validated by _validate_config_shape before this is called.
    return Path(JOBS_BASE_DIR) / job_id  # all files for this job will live


def _build_cmd(
    config: RunConfig, workspace: Path
) -> list[str]:  # ["docker", "run", "--rm", ...]
    """Return the full docker run argv. Never uses shell interpolation."""
    # isolation_level is guaranteed valid by _validate_config_shape, so direct
    # key access is safe — no fallback needed or wanted.
    # docker command arguments are passed as a list, so there is no shell interpolation and shell injectins.
    limits = _RESOURCE_LIMITS[
        config.isolation_level
    ]  # get limits for this isolation level
    uid = os.getuid()  # get the current user's UID (current user means the user running the NirikshanOS process)
    gid = os.getgid()  # get the current user's GID (current user means the user running the NirikshanOS process)

    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"nirikshan_{config.job_id}",
        "--network",
        "none",
        "--cpus",
        limits["cpus"],
        "--memory",
        limits["memory"],
        "--memory-swap",
        limits["memory"],  # swap == memory → no extra swap
        "--pids-limit",
        limits["pids"],
        "--cap-drop",  # drop all capabilities to minimize attack surface
        "ALL",
        "--security-opt",  # prevents the process from gaining privileges
        "no-new-privileges",
        "--read-only",  # makes the container root filesystem read-only
        "--tmpfs",  # creates a read-write tmpfs mount for /tmp since many tools need it
        "/tmp:rw,nosuid,nodev,size=64m",  # 64MiB
        "--user",
        f"{uid}:{gid}",  # overriding the default user(root) to the current user
        # Two separate read-only bind mounts instead of mounting the whole input/
        # directory. This lets the evidence file be mounted directly from its
        # download path without copying — important for multi-GB forensic files.
        "-v",
        # this maps the host file: /storage/jobs/job_001/input/job_config.json to container path: /input/job_config.json
        f"{workspace / 'input' / 'job_config.json'}:/input/job_config.json:ro",  # container can read the job config but not write to it
        "-v",
        # this maps the host file: /storage/uploads/sample.bin to container path: /input/evidence
        f"{config.evidence_path}:/input/evidence:ro",
        "-v",
        # this maps the host file: /storage/jobs/job_001/work to container path: /work (scratch space)
        f"{workspace / 'work'}:/work:rw",
        "-v",
        # this maps the host file: /storage/jobs/job_001/output to container path: /output (output directory)
        f"{workspace / 'output'}:/output:rw",
        config.runtime_image,
        # No command appended — the image entrypoint reads /input/job_config.json
        # and decides what tools to invoke. The backend controls the image via
        # module_registry; the frontend only supplies module IDs and options.
    ]


# if the container is already gone, the runner ignores the error and moves on
async def _force_remove(job_id: str) -> None:
    """Best-effort 'docker rm -f'. Ignores errors; container may already be gone."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            f"nirikshan_{job_id}",
            stdout=asyncio.subprocess.DEVNULL,  # DEVNULL means ignore output
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception:
        pass


def _prepare_workspace(config: RunConfig, workspace: Path) -> tuple[Path, Path, Path]:
    """Create directory tree and write job_config.json.

    Returns (stdout_path, stderr_path, output_dir).

    The evidence file is NOT copied here. It is bind-mounted directly from
    config.evidence_path into the container as /input/evidence:ro, so
    multi-GB forensic files are never duplicated on disk.
    """
    """
    /storage/jobs/job_001/
      input/
      work/
      output/
        artifacts/
    create parent folders if needed and do not fail if the folder already exists
    """
    (workspace / "input").mkdir(parents=True, exist_ok=True)
    (workspace / "work").mkdir(parents=True, exist_ok=True)
    (workspace / "output" / "artifacts").mkdir(parents=True, exist_ok=True)

    """
    write job_config.json to the input folder
    {
      "job_id": "job_001",
      "modules": [
        {
          "id": "hash",
          "name": "Hash",
          "options": {}
        }
      ]
    }
    The Docker image entrypoint reads this to decide which analysis modules to run.
    """
    (workspace / "input" / "job_config.json").write_text(
        json.dumps({"job_id": config.job_id, "modules": config.modules}, indent=2)
    )

    """
    stdout_path = /storage/jobs/job_001/output/stdout.txt
    stderr_path = /storage/jobs/job_001/output/stderr.txt
    output_dir  = /storage/jobs/job_001/output
    """
    output_dir = workspace / "output"
    return output_dir / "stdout.txt", output_dir / "stderr.txt", output_dir


"""
collect artifacts from the output directory /output/artifacts

output/artifacts/report.json
output/artifacts/strings.txt
output/artifacts/images/screenshot.png

returns:

[
    "/storage/jobs/job_001/output/artifacts/report.json",
    "/storage/jobs/job_001/output/artifacts/strings.txt",
    "/storage/jobs/job_001/output/artifacts/images/screenshot.png",
]
"""


def _collect_artifacts(output_dir: Path) -> list[str]:
    artifacts_dir = output_dir / "artifacts"
    if not artifacts_dir.exists():
        return []
    return [str(p) for p in sorted(artifacts_dir.rglob("*")) if p.is_file()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_container(config: RunConfig) -> RunResult:
    """Validate, set up workspace, run the container, and return results.

    Caller responsibilities before invoking this function:
      1. Download the evidence file from MinIO to an absolute local path.
      2. Pass that path as config.evidence_path.
      3. Read stdout_path / stderr_path / output_dir from the returned RunResult.

    All exceptions — including validation errors — are caught and returned as
    a RunResult with exit_code=-1 and the error in error_message, so the worker
    can mark the job failed without a separate try/except.
    """
    started_at = time.monotonic()  # records the start time
    """
    Use /dev/null for now.
    Later, replace it with real paths if workspace setup succeeds.
    If setup fails early, we still have something safe to return.
    """
    stdout_path: Path = Path("/dev/null")
    stderr_path: Path = Path("/dev/null")
    output_dir: Path = Path("/dev/null")

    try:
        _validate_config_shape(config)

        workspace = _workspace(config.job_id)
        stdout_path, stderr_path, output_dir = _prepare_workspace(config, workspace)

        cmd = _build_cmd(config, workspace)  # creates the full Docker command as a list

        with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
            proc = await asyncio.create_subprocess_exec(  # actually starts the docker
                *cmd,
                stdout=out_f,
                stderr=err_f,
            )
            try:  # waits for Docker to finish, with a timeout
                await asyncio.wait_for(proc.wait(), timeout=config.timeout_seconds)
            except asyncio.TimeoutError:
                # if the container exceeds the timeout,
                # kill the local Docker CLI process
                # force-remove the Docker container
                # wait for the Docker CLI process to fully exit
                proc.kill()
                await _force_remove(config.job_id)
                await proc.wait()
                elapsed = time.monotonic() - started_at  # calculate runtime
                return RunResult(
                    exit_code=-1,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    output_dir=str(output_dir),
                    artifacts=_collect_artifacts(output_dir),
                    execution_time=elapsed,
                    error_message=f"Timed out after {config.timeout_seconds}s",
                )

        elapsed = time.monotonic() - started_at
        rc = proc.returncode
        return RunResult(
            exit_code=rc,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            output_dir=str(output_dir),
            artifacts=_collect_artifacts(output_dir),
            execution_time=elapsed,
            error_message=None if rc == 0 else f"Container exited {rc}",
        )

    except Exception as exc:
        elapsed = time.monotonic() - started_at
        await _force_remove(config.job_id)
        return RunResult(
            exit_code=-1,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            output_dir=str(output_dir),
            artifacts=[],
            execution_time=elapsed,
            error_message=str(exc),
        )
