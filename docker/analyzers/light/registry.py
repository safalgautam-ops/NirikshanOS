"""Discovers and registers bundled module definitions from the modules/ directory.

Two dispatch paths exist in run_analysis.py:
  Local registry  — module YAML/Python bundled in the image (modules/ dir).
  Inline spec     — module definition embedded in job_config by the worker (DB-driven).
                    Used for all custom modules created through the admin IDE.

The inline spec path is the primary one for all admin-created modules.
The local registry is a fallback for built-in modules bundled with this image.
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
    if not _MODULES_DIR.exists():
        return
    for path in sorted(_MODULES_DIR.iterdir()):
        if path.name.startswith("_"):
            continue
        if path.suffix in (".yaml", ".yml"):
            try:
                defn = yaml.safe_load(path.read_text())
                if defn and "id" in defn:
                    _yaml_defs[defn["id"]] = defn
                    print(f"[registry] loaded yaml module: {defn['id']}")
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
            except Exception as exc:
                print(f"[registry] failed to load {path.name}: {exc}")


_discover()

SUPPORTED_MODULES: frozenset[str] = frozenset(_python_handlers) | frozenset(_yaml_defs)


def dispatch(module_id: str, options: dict, output_dir: Path) -> dict:
    if module_id in _python_handlers:
        return _python_handlers[module_id](options, output_dir)
    if module_id in _yaml_defs:
        return run_yaml_module(_yaml_defs[module_id], options, output_dir)
    return {
        "status":      "skipped",
        "exit_code":   None,
        "stdout_file": None,
        "stderr_file": None,
        "error":       f"Module '{module_id}' not found in this image",
    }


def dispatch_spec(spec: dict, options: dict, output_dir: Path) -> dict:
    """Run a module from an inline execution_spec embedded in job_config.json.

    This is the DB-driven path used for all custom IDE-created modules.
    Local Python handlers still win if the module_id matches a bundled handler.
    """
    module_id = spec.get("id", "")
    if module_id in _python_handlers:
        return _python_handlers[module_id](options, output_dir)
    return run_yaml_module(spec, options, output_dir)
