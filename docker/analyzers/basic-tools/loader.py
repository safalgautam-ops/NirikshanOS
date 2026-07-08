"""Generic runner for YAML-defined analysis modules.

A YAML module definition supports two execution modes:

1. argv mode — single command built from a template:

    id: generic.strings_extraction
    argv:
      - strings
      - "-n"
      - {opt: min_length}    # replaced with the validated option value at runtime
      - /input/evidence
    options:
      min_length:
        type: int
        default: 6
        min: 4
        max: 100

2. script mode — embedded Python for multi-step or conditional logic:

    id: generic.custom_extractor
    script: |
      import re
      with open("/input/evidence", "rb") as f:
          data = f.read()
      urls = re.findall(rb'https?://\\S+', data)
      stdout_path.write_text("\\n".join(u.decode("utf-8", errors="replace") for u in urls))
    options:
      encoding:
        type: str
        default: utf-8
        allowed: [utf-8, latin-1]

    Script namespace: options (validated dict), output_dir (Path),
    stdout_path / stderr_path (Path), run_cmd, read_file (from utils).
    The script may set `result` (the standard result dict); if it does not,
    a default success result is built from whether stdout_path was written.

Security: option values are validated and typed before they reach argv or the
script namespace. shell=False is always used for subprocess calls. Scripts are
trusted — they come from the admin-uploaded YAML definitions, not from users.
"""
from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

from utils import output_paths, read_file, run_cmd


def _validate_options(schema: dict, raw: dict) -> dict:
    """Coerce and clamp raw option values against the module's declared schema.

    Unknown keys in raw are ignored. Missing keys fall back to schema defaults.
    """
    result = {}
    for key, spec in schema.items():
        raw_val = raw.get(key, spec.get("default"))
        opt_type = spec.get("type", "str")

        if opt_type == "int":
            try:
                val = int(raw_val)
            except (TypeError, ValueError):
                val = int(spec.get("default", 0))
            if "min" in spec:
                val = max(int(spec["min"]), val)
            if "max" in spec:
                val = min(int(spec["max"]), val)

        elif opt_type == "str":
            val = str(raw_val) if raw_val is not None else str(spec.get("default", ""))
            allowed = spec.get("allowed", [])
            if allowed and val not in allowed:
                val = str(spec.get("default", allowed[0]))

        elif opt_type == "bool":
            if isinstance(raw_val, bool):
                val = raw_val
            elif isinstance(raw_val, str):
                val = raw_val.lower() in ("true", "1", "yes")
            else:
                val = bool(spec.get("default", False))

        else:
            val = raw_val if raw_val is not None else spec.get("default")

        result[key] = val
    return result


def _build_argv(template: list, validated: dict) -> list[str]:
    """Build a safe argv list from the YAML template.

    Each item is either:
      - a plain string  → used as-is
      - {opt: key_name} → replaced with str(validated[key_name])

    Only keys declared in the module's options schema appear in validated,
    so arbitrary injection from user input is impossible.
    """
    argv = []
    for item in template:
        if isinstance(item, dict) and "opt" in item:
            key = item["opt"]
            argv.append(str(validated[key]))
        else:
            argv.append(str(item))
    return argv


def _run_script(
    script: str,
    validated: dict,
    output_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict:
    """Execute an embedded Python script from a YAML module definition.

    The script runs in a controlled namespace with helpers pre-injected.
    It may set `result` (the standard result dict); if not, a default is
    built based on whether stdout_path was written without exception.
    """
    namespace: dict = {
        "options":     validated,
        "output_dir":  output_dir,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "run_cmd":     run_cmd,
        "read_file":   read_file,
        "Path":        Path,
    }
    try:
        exec(script, namespace)  # noqa: S102 — trusted admin-uploaded code
    except Exception as exc:
        err = f"Script raised: {exc}\n{traceback.format_exc()}"
        stderr_path.write_text(err)
        return {
            "status":      "failed",
            "exit_code":   1,
            "stdout_file": stdout_path.name,
            "stderr_file": stderr_path.name,
            "error":       str(exc),
        }

    if "result" in namespace:
        return namespace["result"]

    return {
        "status":      "success" if stdout_path.exists() else "failed",
        "exit_code":   0,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       None,
    }


def run_yaml_module(defn: dict, raw_options: dict, output_dir: Path) -> dict:
    """Execute a YAML-defined module and return the standard result dict.

    Dispatches to script mode if `script:` is present, argv mode otherwise.
    Respects `timeout:` (seconds) declared in the definition.
    """
    module_id = defn["id"]
    stdout_path, stderr_path = output_paths(module_id, output_dir)
    timeout = defn.get("timeout")

    validated = _validate_options(defn.get("options", {}), raw_options)

    if "script" in defn:
        return _run_script(defn["script"], validated, output_dir, stdout_path, stderr_path)

    argv = _build_argv(defn["argv"], validated)

    try:
        rc = run_cmd(argv, stdout_path, stderr_path, timeout=timeout)
    except subprocess.TimeoutExpired:
        stderr_path.write_text(f"Module timed out after {timeout}s\n")
        return {
            "status":      "failed",
            "exit_code":   -1,
            "stdout_file": stdout_path.name,
            "stderr_file": stderr_path.name,
            "error":       f"Timed out after {timeout}s",
        }

    return {
        "status":      "success" if rc == 0 else "failed",
        "exit_code":   rc,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       None,
    }
