"""Parser for generic.file_identification (tool: file / libmagic).

Handles two output shapes:
  - JSON  (when the container passes --json to libmagic/file)
  - Plain text  "filename: description"  (default file(1) output)
"""

from __future__ import annotations

import json

PARSER_NAME = "file_identification_parser"


def parse(stdout: str, stderr: str, exit_code: int) -> dict:
    summary: dict = {
        "file_type": None,
        "mime_type": None,
        "description": None,
    }

    # JSON output from `file --json` or libmagic binding
    try:
        data = json.loads(stdout.strip())
        # `file --json` wraps results in {"filename": [...]}
        if isinstance(data, dict) and not any(k in data for k in ("type", "mime-type")):
            # Unwrap first entry from file --json format
            first = next(iter(data.values()), None)
            if isinstance(first, list) and first:
                data = first[0]
        summary["file_type"]   = data.get("type") or data.get("file_type")
        summary["mime_type"]   = data.get("mime-type") or data.get("mime_type")
        summary["description"] = data.get("description") or data.get("type")
        return {"summary": summary, "iocs": [], "findings": [], "artifacts": []}
    except (json.JSONDecodeError, AttributeError, StopIteration):
        pass

    # Container format:
    #   "Description : JPEG image data, JFIF standard ..."
    #   "MIME type   : image/jpeg"
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("description") and " : " in stripped:
            summary["description"] = stripped.split(" : ", 1)[-1].strip()
        elif lower.startswith("mime") and " : " in stripped:
            summary["mime_type"] = stripped.split(" : ", 1)[-1].strip()
        elif not summary["description"]:
            # Plain text fallback: "/input/evidence: PDF document, version 1.4"
            if ": " in stripped:
                summary["description"] = stripped.split(": ", 1)[-1].strip()
            else:
                summary["description"] = stripped

    return {"summary": summary, "iocs": [], "findings": [], "artifacts": []}
