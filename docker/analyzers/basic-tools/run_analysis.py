#!/usr/bin/env python3
"""Entrypoint for dfir/basic-tools:1.0.

Reads /input/job_config.json, dispatches each requested module, and writes a
summary to /output/result.json.

Two dispatch paths:
  Local registry — module was bundled at image build time (modules/ directory).
  Inline spec    — module definition embedded in job_config by the worker (DB-driven
                   flow). Triggered when a module entry carries `execution_spec`.

This file contains only orchestration — no tool commands, no option validation,
no output parsing. All of that lives in:
  registry.py  — discovers local modules and routes to the right handler
  loader.py    — executes YAML-defined modules (argv or embedded script)
  modules/     — Python handlers for complex modules + YAML for simple ones
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import registry

CONFIG_PATH = Path("/input/job_config.json")
OUTPUT_DIR  = Path("/output")
EVIDENCE    = Path("/input/evidence")


def _dispatch_module(entry: dict) -> dict:
    """Route one module entry to the correct dispatch path."""
    module_id = entry.get("id", "")
    options   = entry.get("options") or {}
    spec      = entry.get("execution_spec")

    if spec:
        return registry.dispatch_spec(spec, options, OUTPUT_DIR)
    return registry.dispatch(module_id, options, OUTPUT_DIR)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "artifacts").mkdir(exist_ok=True)

    try:
        config = json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        OUTPUT_DIR.joinpath("result.json").write_text(json.dumps({
            "job_id":  "unknown",
            "status":  "failed",
            "error":   f"Cannot read job_config.json: {exc}",
            "modules": {},
        }, indent=2))
        sys.exit(1)

    job_id  = config.get("job_id", "unknown")
    modules = config.get("modules", [])

    if not EVIDENCE.exists():
        OUTPUT_DIR.joinpath("result.json").write_text(json.dumps({
            "job_id":  job_id,
            "status":  "failed",
            "error":   "/input/evidence not found",
            "modules": {},
        }, indent=2))
        sys.exit(1)

    print(f"[analyzer] job={job_id} modules={[m.get('id') for m in modules]}")
    print(f"[analyzer] local_modules={sorted(registry.SUPPORTED_MODULES)}")

    module_results: dict[str, dict] = {}
    overall_status = "completed"

    for entry in modules:
        module_id = entry.get("id", "")
        print(f"[analyzer] running module={module_id}")

        try:
            result = _dispatch_module(entry)
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

    OUTPUT_DIR.joinpath("result.json").write_text(json.dumps({
        "job_id":  job_id,
        "status":  overall_status,
        "modules": module_results,
    }, indent=2))

    print(f"[analyzer] done status={overall_status}")
    sys.exit(0 if overall_status != "failed" else 1)


if __name__ == "__main__":
    main()
