"""Minimal in-process release check (a subset of the official ``validate_output.py``).

Returned problem strings are fixed templates with counts only: no paths, no content.
"""

from __future__ import annotations

import json
from pathlib import Path

STATUSES = frozenset({"sanitized", "quarantined", "suppressed"})


def check_release(out_dir: Path, input_shas: list[str]) -> list[str]:
    problems: list[str] = []
    san = out_dir / "sanitized"
    if not san.is_dir():
        problems.append("missing sanitized/")
    try:
        report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return problems + ["report.json missing or invalid"]
    entries = report.get("files") or []
    listed = {e.get("input_sha256") for e in entries}
    missing = sum(1 for s in set(input_shas) if s not in listed)
    if missing:
        problems.append(f"{missing} input files not listed in report")
    if len(entries) != len(input_shas):
        problems.append("report file count differs from input file count")
    bad_status = sum(1 for e in entries if e.get("status") not in STATUSES)
    if bad_status:
        problems.append(f"{bad_status} report entries with invalid status")
    absent = sum(
        1 for e in entries if e.get("status") == "sanitized" and not (out_dir / str(e.get("output") or "")).is_file()
    )
    if absent:
        problems.append(f"{absent} declared outputs do not exist")
    if not (out_dir / "records.jsonl").is_file():
        problems.append("records.jsonl missing")
    return problems
