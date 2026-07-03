"""Parser for generic.strings_extraction (tool: strings / FLOSS).

Output is one printable string per line. We scan for embedded IOCs
(URLs, IPs, email addresses) and return a summary count alongside
the full deduplicated IOC list.
"""

from __future__ import annotations

import re

_URL_RE   = re.compile(r"https?://[^\s<>\"'{}|\\^`\[\]]{4,}", re.IGNORECASE)
_IP_RE    = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")


def parse(stdout: str, stderr: str, exit_code: int) -> dict:
    lines = [l for l in stdout.splitlines() if l.strip()]

    urls   = sorted(set(_URL_RE.findall(stdout)))
    ips    = sorted(set(_IP_RE.findall(stdout)))
    emails = sorted(set(_EMAIL_RE.findall(stdout)))

    iocs: list[dict] = []
    for v in urls:
        iocs.append({"type": "url",   "value": v})
    for v in ips:
        iocs.append({"type": "ip",    "value": v})
    for v in emails:
        iocs.append({"type": "email", "value": v})

    return {
        "summary": {
            "total_strings": len(lines),
            "urls_found":    len(urls),
            "ips_found":     len(ips),
            "emails_found":  len(emails),
        },
        "iocs":     iocs,
        "findings": [],
        "artifacts": [],
    }
