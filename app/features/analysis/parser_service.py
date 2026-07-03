"""Dispatcher that maps module parser_name → parser function → ParsedResult.

Usage:

    result = parse_module_output(
        parser_name  = module.parser_name,   # from module_registry
        stdout_path  = run_result.stdout_path,
        stderr_path  = run_result.stderr_path,
        exit_code    = run_result.exit_code,
    )

The parser_name comes directly from module_registry.AnalysisModule.parser_name,
which is auto-generated as "{module_id.split('.')[-1]}_parser".

If no parser is registered for a given parser_name, parse_module_output
returns a ParsedResult with an empty summary and a note — it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.features.analysis.parsers import (
    file_info_parser,
    hashing_parser,
    strings_parser,
    yara_parser,
)

# Signature every parser module must expose.
ParserFn = Callable[[str, str, int], dict]

# Maps parser_name (from module_registry) → parse function.
# Add a new entry here whenever a new parser module is created.
_REGISTRY: dict[str, ParserFn] = {
    "file_identification_parser": file_info_parser.parse,
    "hash_calculation_parser":    hashing_parser.parse,
    "strings_extraction_parser":  strings_parser.parse,
    "yara_scan_parser":           yara_parser.parse,
}


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

    # If the tool exited non-zero and produced no stdout, don't try to parse.
    if exit_code != 0 and not stdout.strip():
        base.summary = {
            "error":  f"Tool exited with code {exit_code}",
            "stderr": stderr or "",
        }
        return base

    try:
        result        = parser_fn(stdout, stderr or "", exit_code)
        base.summary  = result.get("summary",  {})
        base.iocs     = result.get("iocs",     [])
        base.findings = result.get("findings", [])
        base.artifacts = result.get("artifacts", [])
    except Exception as exc:
        base.summary = {"error": f"Parser raised: {exc}"}

    return base
