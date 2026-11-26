"""Minimal in-process release check (a subset of the official ``validate_output.py``).

Returned problem strings are fixed templates with counts only: no paths, no content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from clinveil.privacy.pseudonym import ALPHABET, PREFIX

STATUSES = frozenset({"sanitized", "quarantined", "suppressed"})
_PSN_RE = re.compile(rf"^{re.escape(PREFIX)}[{ALPHABET}]{{6}}$")


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
    rj = out_dir / "records.jsonl"
    if not rj.is_file():
        problems.append("records.jsonl missing")
    else:
        problems.extend(_check_records_pseudonyms(out_dir, rj, report))
    return problems


def _check_records_pseudonyms(out_dir: Path, rj: Path, report: dict) -> list[str]:
    problems: list[str] = []
    bad_fmt = 0
    inconsistent = 0
    linked = 0
    file_cache: dict[str, str] = {}
    try:
        lines = rj.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["records.jsonl unreadable"]
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            return ["records.jsonl invalid json"]
        psn = rec.get("patient")
        if psn is None:
            continue
        linked += 1
        if not isinstance(psn, str) or not _PSN_RE.fullmatch(psn):
            bad_fmt += 1
            continue
        rel = str(rec.get("file") or "")
        if rel not in file_cache:
            target = out_dir / rel
            try:
                file_cache[rel] = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
            except OSError:
                file_cache[rel] = ""
        if psn not in file_cache[rel]:
            inconsistent += 1
    if bad_fmt:
        problems.append(f"{bad_fmt} records have malformed pseudonyms")
    if inconsistent:
        problems.append(f"{inconsistent} records have pseudonyms missing from exported content")
    reported_linked = (report.get("counts") or {}).get("records_linked")
    if reported_linked != linked:
        problems.append("report records_linked disagrees with records.jsonl")
    return problems
