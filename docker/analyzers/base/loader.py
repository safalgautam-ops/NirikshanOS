"""Generic runner for YAML-defined analysis modules.

Each module YAML supports three keys that drive the full execution lifecycle:

  install:          (optional) Install the tool if missing.
    apt: [pkg, ...]     packages to install via apt-get
    check: binary       binary name to test with `which` first
                        if `which` succeeds, apt-get is skipped

  argv / script:    What to run (one of these is required).

    argv mode — single shell command as a list:
      argv:
        - strings
        - -n
        - {opt: min_length}     substituted from validated options
        - /case/evidence        evidence path inside the container

    script mode — embedded Python:
      script: |
        import subprocess
        r = subprocess.run(["sha256sum", "/case/evidence"], capture_output=True, text=True)
        stdout_path.write_text(r.stdout)
      Namespace: options, output_dir, stdout_path, stderr_path, run_cmd, read_file, Path

  pipe:             (optional) Pipe main-command stdout through a second command.
    argv:
      - grep
      - -i
      - -E
      - {opt: filter_string}
    skip_if_empty: filter_string   skip the pipe if this option value is blank

  options:          Typed, validated parameter schema.
    key:
      type: int | str | bool | list
      default: ...
      label: ...
      allowed: [...]   (str / list — whitelist of valid values)
      min: ...         (int only)
      max: ...         (int only)
      optional: true   (str — treat empty string as "not supplied")

Evidence file is always at /case/evidence inside the container.
"""
from __future__ import annotations

import shutil
import subprocess
import traceback
from pathlib import Path

from utils import output_paths, read_file, run_cmd


# ── Option validation ─────────────────────────────────────────────────────────

def _validate_options(schema: dict, raw: dict) -> dict:
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
                val = str(spec.get("default", allowed[0] if allowed else ""))

        elif opt_type == "bool":
            if isinstance(raw_val, bool):
                val = raw_val
            elif isinstance(raw_val, str):
                val = raw_val.lower() in ("true", "1", "yes")
            else:
                val = bool(spec.get("default", False))

        elif opt_type == "list":
            allowed = spec.get("allowed", [])
            if isinstance(raw_val, list):
                val = [v for v in raw_val if not allowed or v in allowed]
            elif isinstance(raw_val, str) and raw_val:
                val = [v.strip() for v in raw_val.split(",") if not allowed or v.strip() in allowed]
            else:
                val = list(spec.get("default", []))
            if not val and allowed:
                val = list(spec.get("default", [allowed[0]]))

        else:
            val = raw_val if raw_val is not None else spec.get("default")

        result[key] = val
    return result


# ── Tool installation ─────────────────────────────────────────────────────────

def _install_if_needed(install_spec: dict) -> None:
    """Install apt packages if the required binary is not already on PATH.

    Runs once per module per container lifetime. If the tool is already installed
    (common when multiple modules share a package), the apt-get call is skipped
    entirely so startup stays fast.
    """
    check_bin = install_spec.get("check", "")
    packages  = install_spec.get("apt", [])
    if not packages:
        return

    # If the binary exists, nothing to do.
    if check_bin and shutil.which(check_bin):
        print(f"[loader] tool '{check_bin}' already present — skipping install")
        return

    print(f"[loader] installing: {packages}")
    try:
        subprocess.run(
            ["apt-get", "update", "-qq"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
            check=True, capture_output=True,
        )
        print(f"[loader] installed: {packages}")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"apt-get install failed for {packages}: {exc.stderr.decode(errors='replace')}") from exc


# ── argv helpers ──────────────────────────────────────────────────────────────

def _build_argv(template: list, validated: dict) -> list[str]:
    argv = []
    for item in template:
        if isinstance(item, dict) and "opt" in item:
            key = item["opt"]
            if key not in validated:
                raise ValueError(
                    f"argv template references option '{key}' which is not declared in the options schema"
                )
            argv.append(str(validated[key]))
        else:
            argv.append(str(item))
    return argv


# ── Execution modes ───────────────────────────────────────────────────────────

def _run_script(script: str, validated: dict, output_dir: Path, stdout_path: Path, stderr_path: Path) -> dict:
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
        return {"status": "failed", "exit_code": 1,
                "stdout_file": stdout_path.name, "stderr_file": stderr_path.name,
                "error": str(exc)}

    if "result" in namespace:
        return namespace["result"]
    return {
        "status":      "success" if stdout_path.exists() else "failed",
        "exit_code":   0,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "error":       None,
    }


def _run_pipe(pipe_spec: dict, validated: dict, stdout_path: Path, stderr_path: Path, timeout: int | None) -> int:
    """Feed the current stdout_path through a second command, replacing it in place.

    Uses a temporary file so the original output is not lost if the pipe fails.
    Returns the pipe command's exit code.
    """
    pipe_argv = _build_argv(pipe_spec["argv"], validated)
    tmp_path  = stdout_path.with_suffix(".pipe_tmp")
    pipe_err  = stderr_path.with_suffix(".pipe.stderr.txt")
    try:
        rc = run_cmd(pipe_argv, tmp_path, pipe_err, timeout=timeout, stdin_path=stdout_path)
        if rc == 0 and tmp_path.exists():
            tmp_path.replace(stdout_path)
        return rc
    finally:
        tmp_path.unlink(missing_ok=True)
        pipe_err.unlink(missing_ok=True)


# ── Public entry point ────────────────────────────────────────────────────────

def run_yaml_module(defn: dict, raw_options: dict, output_dir: Path) -> dict:
    """Execute one YAML-defined module and return the standard result dict.

    Execution order:
      1. Install tool if needed (install: block).
      2. Validate and coerce options.
      3. Run main command (argv: or script:).
      4. Pipe output if pipe: is declared and the trigger option is non-empty.
    """
    module_id   = defn["id"]
    stdout_path, stderr_path = output_paths(module_id, output_dir)
    timeout     = defn.get("timeout")
    schema      = defn.get("options", {})
    validated   = _validate_options(schema, raw_options)

    # Step 1 — install
    if "install" in defn:
        try:
            _install_if_needed(defn["install"])
        except RuntimeError as exc:
            stderr_path.write_text(str(exc))
            return {"status": "failed", "exit_code": -1,
                    "stdout_file": None, "stderr_file": stderr_path.name,
                    "error": str(exc)}

    # Step 2 — run
    if "script" in defn:
        result = _run_script(defn["script"], validated, output_dir, stdout_path, stderr_path)
    elif "argv" in defn:
        argv = _build_argv(defn["argv"], validated)
        try:
            rc = run_cmd(argv, stdout_path, stderr_path, timeout=timeout)
        except subprocess.TimeoutExpired:
            stderr_path.write_text(f"Module timed out after {timeout}s\n")
            return {"status": "failed", "exit_code": -1,
                    "stdout_file": stdout_path.name, "stderr_file": stderr_path.name,
                    "error": f"Timed out after {timeout}s"}
        result = {
            "status":      "success" if rc == 0 else "failed",
            "exit_code":   rc,
            "stdout_file": stdout_path.name,
            "stderr_file": stderr_path.name,
            "error":       None if rc == 0 else f"Tool exited {rc}",
        }
    else:
        return {"status": "failed", "exit_code": -1,
                "stdout_file": None, "stderr_file": None,
                "error": "Module definition has neither 'argv' nor 'script'"}

    # Step 3 — optional pipe
    pipe_spec = defn.get("pipe")
    if pipe_spec and result.get("status") == "success":
        skip_key = pipe_spec.get("skip_if_empty", "")
        skip     = skip_key and not str(validated.get(skip_key, "")).strip()
        if not skip:
            _run_pipe(pipe_spec, validated, stdout_path, stderr_path, timeout)

    return result
