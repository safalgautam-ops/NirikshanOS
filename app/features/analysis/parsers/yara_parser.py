"""Parser for generic.yara_scan (tool: yara).

Handles two output shapes:
  - JSON  (yara --json flag)
  - Plain text  "RuleName /path/to/file"  (default yara output)

Each matched rule becomes a finding with severity derived from its meta.
"""

from __future__ import annotations

import json
import re

# Plain-text yara output: "RuleName /input/evidence"
# Lines starting with "0x" are string-match detail lines — we skip those.
_PLAIN_RULE_RE = re.compile(r"^([A-Za-z0-9_]+)\s+\S+$")


def _severity_from_meta(meta: dict) -> str:
    raw = str(meta.get("severity", meta.get("threat_level", ""))).lower()
    if raw in ("critical", "high"):
        return "high"
    if raw in ("medium",):
        return "medium"
    return "low"


def parse(stdout: str, stderr: str, exit_code: int) -> dict:
    matches: list[dict] = []

    # JSON output (yara --json)
    try:
        data = json.loads(stdout.strip())
        if isinstance(data, list):
            for entry in data:
                matches.append({
                    "rule":            entry.get("rule", ""),
                    "namespace":       entry.get("namespace", "default"),
                    "tags":            entry.get("tags", []),
                    "meta":            entry.get("meta", {}),
                    "strings_matched": len(entry.get("strings", [])),
                })
    except (json.JSONDecodeError, AttributeError):
        # Plain-text fallback
        for line in stdout.splitlines():
            m = _PLAIN_RULE_RE.match(line.strip())
            if m:
                matches.append({
                    "rule":            m.group(1),
                    "namespace":       "default",
                    "tags":            [],
                    "meta":            {},
                    "strings_matched": 0,
                })

    findings: list[dict] = []
    for match in matches:
        findings.append({
            "title":    f"YARA match: {match['rule']}",
            "severity": _severity_from_meta(match["meta"]),
            "detail":   match,
        })

    return {
        "summary": {
            "rules_matched": len(matches),
            "matches":       matches,
        },
        "iocs":     [],
        "findings": findings,
        "artifacts": [],
    }
