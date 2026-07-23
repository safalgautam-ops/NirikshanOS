"""Docker container runner for analysis jobs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.db.orm import db

JOBS_BASE_DIR = os.environ.get("JOBS_DIR", "/storage/jobs")

_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


async def _get_active_instance_by_image(image_tag: str) -> dict | None:
    """The `instances` table IS the allowlist now — an admin registers an instance through the UI, and only images with an active, registered row may ever be scheduled."""
    return await db.table("instances").where("image_tag", image_tag).where("is_active", 1).first()


@dataclass
class RunConfig:
    job_id: str
    evidence_path: str
    runtime_image: str
    modules: list[dict]
    timeout_seconds: int


@dataclass
class RunResult:
    exit_code: int
    stdout_path: str
    stderr_path: str
    output_dir: str
    artifacts: list[str]
    execution_time: float
    error_message: str | None = None


async def _validate_config_shape(
    config: RunConfig,
) -> dict:
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

    instance = await _get_active_instance_by_image(config.runtime_image)
    if instance is None:
        raise ValueError(
            f"runtime_image {config.runtime_image!r} is not a registered, active "
            f"instance. Register it at /admin/instances first."
        )
    return instance


def _workspace(job_id: str) -> Path:
    return Path(JOBS_BASE_DIR) / job_id


def _build_cmd(config: RunConfig, workspace: Path, instance: dict) -> list[str]:
    """Return the full docker run argv."""
    uid = os.getuid()
    gid = os.getgid()

    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"nirikshan_{config.job_id}",
        "--cpus",
        instance["cpu_limit"],
        "--memory",
        instance["memory_limit"],
        "--memory-swap",
        instance["memory_limit"],
        "--pids-limit",
        str(instance["pids_limit"]),
        "--cap-drop",
        "ALL",
        "--cap-add",
        "CHOWN",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "FOWNER",
        "--cap-add",
        "SETUID",
        "--cap-add",
        "SETGID",
        "--cap-add",
        "MKNOD",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--user",
        f"{uid}:{gid}",
        "-v",
        f"{workspace / 'input' / 'job_config.json'}:/case/job_config.json:ro",
        "-v",
        f"{config.evidence_path}:/case/evidence:ro",
        "-v",
        f"{workspace / 'work'}:/work:rw",
        "-v",
        f"{workspace / 'output'}:/output:rw",
        config.runtime_image,
    ]


async def _force_remove(job_id: str) -> None:
    """Best-effort 'docker rm -f'. Ignores errors; container may already be gone."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            f"nirikshan_{job_id}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception:
        pass


def _prepare_workspace(config: RunConfig, workspace: Path) -> tuple[Path, Path, Path]:
    """Create directory tree and write job_config.json."""
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


async def run_container(config: RunConfig) -> RunResult:
    """Validate, set up workspace, run the container, and return results."""
    started_at = time.monotonic()
    """
    Use /dev/null for now.
    Later, replace it with real paths if workspace setup succeeds.
    If setup fails early, we still have something safe to return.
    """
    stdout_path: Path = Path("/dev/null")
    stderr_path: Path = Path("/dev/null")
    output_dir: Path = Path("/dev/null")

    try:
        instance = await _validate_config_shape(config)

        workspace = _workspace(config.job_id)
        stdout_path, stderr_path, output_dir = _prepare_workspace(config, workspace)

        cmd = _build_cmd(config, workspace, instance)

        with stdout_path.open("wb") as out_f, stderr_path.open("wb") as err_f:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=out_f,
                stderr=err_f,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=config.timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                await _force_remove(config.job_id)
                await proc.wait()
                elapsed = time.monotonic() - started_at
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
