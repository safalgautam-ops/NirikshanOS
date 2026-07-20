#!/usr/bin/env python3
"""Runs the entire automated test suite in one command and prints a single,
consolidated result: total passed/failed, a breakdown by the 5 testing
types (unit / functional / integration / security / E2E), and the full
detail of anything that failed.

Usage (from the repo root):
    python3 tests/run_all.py

What it actually does, step by step:
  1. Re-provisions the disposable nirikshan_test database from scratch
     (tests/provision_test_db.sh) - every run starts from an identical,
     clean schema, so results are reproducible.
  2. Runs the unit/functional/integration/security tiers inside the `web`
     container (they need the real app package, asyncmy, and network
     access to mysql/redis - all already set up there).
  3. Runs the E2E tier from the host (Playwright + a real browser hitting
     the live http://localhost stack, already set up on this machine).
  4. Parses both tiers' JUnit XML reports and prints one final summary.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "tests" / ".reports"

# Maps each test tier to (junit report path, category label). Order here is
# the order results are shown in.
CATEGORY_LABELS = {
    "unit": "Unit Testing",
    "functional": "Functional / Route Testing",
    "integration": "Integration Testing",
    "security": "Security / Penetration Testing",
    "e2e": "End-to-End (E2E) Testing",
}


@dataclass
class TestResult:
    name: str
    category: str
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    message: str = ""


@dataclass
class Summary:
    results: list[TestResult] = field(default_factory=list)

    def add_from_junit(self, xml_path: Path) -> None:
        if not xml_path.exists():
            return
        tree = ET.parse(xml_path)
        for testcase in tree.getroot().iter("testcase"):
            classname = testcase.get("classname", "")
            name = testcase.get("name", "")
            # classname looks like "tests.unit.test_passwords" - the
            # second segment is the category directory.
            parts = classname.split(".")
            category = parts[1] if len(parts) > 1 else "unknown"

            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")
            if failure is not None:
                outcome, message = "failed", (failure.get("message") or failure.text or "").strip().splitlines()[0:1]
                message = message[0] if message else ""
            elif error is not None:
                outcome, message = "error", (error.get("message") or error.text or "").strip().splitlines()[0:1]
                message = message[0] if message else ""
            elif skipped is not None:
                outcome, message = "skipped", (skipped.get("message") or "").strip()
            else:
                outcome, message = "passed", ""

            full_name = f"{classname.replace('tests.', '', 1)}::{name}"
            self.results.append(TestResult(name=full_name, category=category, outcome=outcome, message=message))


def run(cmd: list[str], **kwargs) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT, **kwargs).returncode


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("STEP 1/3 - provisioning a fresh nirikshan_test database")
    print("=" * 78)
    rc = run(["bash", "tests/provision_test_db.sh"])
    if rc != 0:
        print("!! database provisioning failed - aborting before running any tests")
        return rc

    print()
    print("=" * 78)
    print("STEP 2/3 - unit + functional + integration + security (inside web container)")
    print("=" * 78)
    backend_xml = REPORTS_DIR / "backend.xml"
    run([
        "docker", "compose", "exec", "-T", "web", "python3", "-m", "pytest",
        "tests/unit", "tests/functional", "tests/integration", "tests/security",
        "-v", f"--junitxml=tests/.reports/backend.xml",
    ])

    print()
    print("=" * 78)
    print("STEP 3/3 - end-to-end (real browser, from this host)")
    print("=" * 78)
    e2e_xml = REPORTS_DIR / "e2e.xml"
    run([
        sys.executable, "-m", "pytest", "tests/e2e",
        "--confcutdir=tests/e2e", "-v", f"--junitxml={e2e_xml}",
    ])

    summary = Summary()
    summary.add_from_junit(backend_xml)
    summary.add_from_junit(e2e_xml)

    report_lines = _render_report(summary)
    report_text = "\n".join(report_lines)
    print()
    print(report_text)

    (REPORTS_DIR / "summary.txt").write_text(report_text + "\n")

    any_failed = any(r.outcome in ("failed", "error") for r in summary.results)
    return 1 if any_failed else 0


def _render_report(summary: Summary) -> list[str]:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("FINAL TEST REPORT")
    lines.append("=" * 78)

    total = len(summary.results)
    passed = sum(1 for r in summary.results if r.outcome == "passed")
    failed = sum(1 for r in summary.results if r.outcome in ("failed", "error"))
    skipped = sum(1 for r in summary.results if r.outcome == "skipped")

    lines.append(f"TOTAL: {total}   PASSED: {passed}   FAILED: {failed}   SKIPPED: {skipped}")
    lines.append("")

    lines.append(f"{'Category':32} {'Total':>6} {'Passed':>7} {'Failed':>7}")
    lines.append("-" * 78)
    for key, label in CATEGORY_LABELS.items():
        cat_results = [r for r in summary.results if r.category == key]
        cat_total = len(cat_results)
        cat_passed = sum(1 for r in cat_results if r.outcome == "passed")
        cat_failed = sum(1 for r in cat_results if r.outcome in ("failed", "error"))
        lines.append(f"{label:32} {cat_total:>6} {cat_passed:>7} {cat_failed:>7}")
    lines.append("")

    lines.append("PASSED:")
    for r in summary.results:
        if r.outcome == "passed":
            lines.append(f"  [PASS] {r.name}")
    lines.append("")

    failures = [r for r in summary.results if r.outcome in ("failed", "error")]
    if failures:
        lines.append("FAILED - problems that arose:")
        for r in failures:
            lines.append(f"  [FAIL] {r.name}")
            if r.message:
                lines.append(f"         -> {r.message}")
    else:
        lines.append("FAILED: none.")
    lines.append("")
    lines.append("=" * 78)

    return lines


if __name__ == "__main__":
    sys.exit(main())
