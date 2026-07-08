"""Dispatcher that maps module parser_name → parser function → ParsedResult.

Usage:

    result = parse_module_output(
        parser_name  = module.parser_name,   # from module_registry
        stdout_path  = run_result.stdout_path,
        stderr_path  = run_result.stderr_path,
        exit_code    = run_result.exit_code,
    )

Parsers are discovered automatically at import time by scanning the parsers/
directory. Each parser module must export:
  PARSER_NAME: str   — the key used by module_registry (e.g. "file_identification_parser")
  parse(stdout, stderr, exit_code) -> dict

Adding a new parser requires only creating the file — no registry edit.

If no parser is registered for a given parser_name, parse_module_output
returns a ParsedResult with an empty summary and a note — it never raises.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ParserFn = Callable[[str, str, int], dict]

_PARSERS_DIR = Path(__file__).parent / "parsers"


def _discover_parsers() -> dict[str, ParserFn]:
    registry: dict[str, ParserFn] = {}
    for path in sorted(_PARSERS_DIR.iterdir()):
        if path.name.startswith("_") or path.suffix != ".py":
            continue
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "PARSER_NAME") and hasattr(mod, "parse"):
                registry[mod.PARSER_NAME] = mod.parse
        except Exception:
            pass
    return registry


_REGISTRY: dict[str, ParserFn] = _discover_parsers()


@dataclass
class ParsedResult:
    parser_name: str
    summary:     dict            = field(default_factory=dict)
    iocs:        list[dict]      = field(default_factory=list)
    findings:    list[dict]      = field(default_factory=list)
    artifacts:   list[str]       = field(default_factory=list)
    raw_stderr:  str | None      = None


def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(errors="replace")


def parse_module_output(
    *,
    parser_name: str,
    stdout_path: str,
    stderr_path: str,
    exit_code: int,
) -> ParsedResult:
    """Run the correct parser and return a normalised ParsedResult.

    Never raises — errors are captured in summary["error"] so the caller
    can always store the result without its own try/except.
    """
    stderr = _read(stderr_path).strip() or None
    base   = ParsedResult(parser_name=parser_name, raw_stderr=stderr)

    parser_fn = _REGISTRY.get(parser_name)
    if parser_fn is None:
        base.summary = {"note": f"No parser registered for '{parser_name}'"}
        return base

    stdout = _read(stdout_path)

    if exit_code != 0 and not stdout.strip():
        base.summary = {
            "error":  f"Tool exited with code {exit_code}",
            "stderr": stderr or "",
        }
        return base

    try:
        result         = parser_fn(stdout, stderr or "", exit_code)
        base.summary   = result.get("summary",   {})
        base.iocs      = result.get("iocs",       [])
        base.findings  = result.get("findings",   [])
        base.artifacts = result.get("artifacts",  [])
    except Exception as exc:
        base.summary = {"error": f"Parser raised: {exc}"}

    return base
