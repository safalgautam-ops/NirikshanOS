"""Auto-discovers and registers all analysis modules from the modules/ directory.

Discovery rules (run once at import time):
  .yaml files → loaded as YAML module definitions, executed via loader.run_yaml_module
  .py files   → imported via importlib; must export MODULE_ID (str) and
                run(options: dict, output_dir: Path) -> dict

Files beginning with '_' are skipped (e.g. __init__.py, __pycache__).

Public surface:
  SUPPORTED_MODULES         frozenset[str]     — all known module IDs (local)
  dispatch(module_id, options, output_dir)     — run a locally-registered module
  dispatch_spec(spec, options, output_dir)     — run from an inline execution spec
                                                 (used when worker embeds the full
                                                 definition in job_config.json)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

from loader import run_yaml_module

_MODULES_DIR = Path(__file__).parent / "modules"

_python_handlers: dict[str, object] = {}
_yaml_defs: dict[str, dict] = {}


def _discover() -> None:
    for path in sorted(_MODULES_DIR.iterdir()):
        if path.name.startswith("_"):
            continue

        if path.suffix == ".yaml":
            try:
                defn = yaml.safe_load(path.read_text())
                module_id = defn["id"]
                _yaml_defs[module_id] = defn
                print(f"[registry] loaded yaml module: {module_id}")
            except Exception as exc:
                print(f"[registry] failed to load {path.name}: {exc}")

        elif path.suffix == ".py":
            try:
                spec = importlib.util.spec_from_file_location(path.stem, path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[path.stem] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, "MODULE_ID") and hasattr(mod, "run"):
                    _python_handlers[mod.MODULE_ID] = mod.run
                    print(f"[registry] loaded python module: {mod.MODULE_ID}")
                else:
                    print(f"[registry] skipped {path.name}: missing MODULE_ID or run()")
            except Exception as exc:
                print(f"[registry] failed to load {path.name}: {exc}")


_discover()

# Python handlers take precedence over YAML if both exist for the same module_id.
SUPPORTED_MODULES: frozenset[str] = frozenset(_python_handlers) | frozenset(_yaml_defs)


def dispatch(module_id: str, options: dict, output_dir: Path) -> dict:
    """Run a locally-registered module by ID.

    Returns the standard result dict. If the module is not registered in this
    image, returns a 'skipped' result rather than raising — the caller decides
    whether to treat an unknown module as a hard failure.
    """
    if module_id in _python_handlers:
        return _python_handlers[module_id](options, output_dir)
    if module_id in _yaml_defs:
        return run_yaml_module(_yaml_defs[module_id], options, output_dir)
    return {
        "status":      "skipped",
        "exit_code":   None,
        "stdout_file": None,
        "stderr_file": None,
        "error":       f"Module '{module_id}' not supported by this image",
    }


def dispatch_spec(spec: dict, options: dict, output_dir: Path) -> dict:
    """Run a module from an inline execution spec embedded in job_config.json.

    This is the DB-driven path: the worker reads the module definition from the
    database and embeds it as `execution_spec` in the job config, so the container
    does not need to have that module registered locally. The spec must be a valid
    YAML module definition dict (same shape as a .yaml file in modules/).

    Python handlers registered locally still take precedence if the module_id
    matches — a container-local override always wins.
    """
    module_id = spec.get("id", "")
    if module_id in _python_handlers:
        return _python_handlers[module_id](options, output_dir)
    return run_yaml_module(spec, options, output_dir)
