"""Minimal in-process release check (a subset of the official ``validate_output.py``).

Returned problem strings are fixed templates with counts only: no paths, no content.
"""

from __future__ import annotations

import csv
import io
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
    """Per-RECORD pseudonym validation (Phase 3.1).

    SPEC §6: "the ``patient`` value must actually appear inside that exported record". For each
    ``records.jsonl`` line the record is located by its locator (``row:N`` in CSV/TSV, an RFC 6901
    pointer in JSON, ``doc`` = whole file) and checked:

    * a linked record contains its OWN pseudonym (not merely somewhere in the file);
    * no record contains a DIFFERENT patient's pseudonym (no inherited / leaked pseudonyms);
    * an unlinked record contains no pseudonym;
    * ``report.counts.records_linked`` equals the number of non-null claims.
    """
    problems: list[str] = []
    bad_fmt = missing_own = foreign = unlocatable = linked = 0
    cache: dict[str, _ParsedOutput | None] = {}
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
        rel = str(rec.get("file") or "")
        if rel not in cache:
            cache[rel] = _ParsedOutput.load(out_dir / rel)
        parsed = cache[rel]
        segment = parsed.record_text(str(rec.get("out") or rec.get("loc") or "")) if parsed else None
        if segment is None:
            unlocatable += 1
        tokens = set(_PSN_TOKEN_RE.findall(segment)) if segment is not None else set()
        if psn is None:
            if tokens:
                foreign += 1
            continue
        linked += 1
        if not isinstance(psn, str) or not _PSN_RE.fullmatch(psn):
            bad_fmt += 1
            continue
        if segment is None:
            continue
        if psn not in tokens:
            missing_own += 1
        if tokens - {psn}:
            foreign += 1
    if bad_fmt:
        problems.append(f"{bad_fmt} records have malformed pseudonyms")
    if missing_own:
        problems.append(f"{missing_own} linked records do not contain their own pseudonym")
    if foreign:
        problems.append(f"{foreign} records contain another patient's pseudonym")
    if unlocatable:
        problems.append(f"{unlocatable} records cannot be located in their exported file")
    reported_linked = (report.get("counts") or {}).get("records_linked")
    if reported_linked != linked:
        problems.append("report records_linked disagrees with records.jsonl")
    return problems


_PSN_TOKEN_RE = re.compile(rf"{re.escape(PREFIX)}[{ALPHABET}]{{6}}(?![{ALPHABET}])")


class _ParsedOutput:
    """An exported file parsed just enough to cut out one record by its locator."""

    __slots__ = ("_json", "_rows", "_text")

    def __init__(self, text: str, rows: list[list[str]] | None, data: object) -> None:
        self._text, self._rows, self._json = text, rows, data

    def __repr__(self) -> str:
        return "_ParsedOutput(<redacted>)"

    @classmethod
    def load(cls, path: Path) -> _ParsedOutput | None:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None
        suffix = path.suffix.lower()
        rows: list[list[str]] | None = None
        data: object = None
        if suffix in (".csv", ".tsv"):
            delim = "\t" if suffix == ".tsv" else _sniff_delimiter(text)
            try:
                rows = list(csv.reader(io.StringIO(text), delimiter=delim))
            except csv.Error:
                rows = None
        elif suffix == ".json":
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        return cls(text, rows, data)

    def record_text(self, loc: str) -> str | None:
        if loc == "doc":
            return self._text
        if loc.startswith("row:") and self._rows is not None:
            try:
                i = int(loc[4:]) + 1  # header excluded from row numbering
            except ValueError:
                return None
            return "\x1f".join(self._rows[i]) if 0 < i < len(self._rows) else None
        if loc.startswith("/") and self._json is not None:
            node = self._json
            for part in (p.replace("~1", "/").replace("~0", "~") for p in loc.split("/")[1:]):
                if isinstance(node, list) and part.isdigit() and int(part) < len(node):
                    node = node[int(part)]
                elif isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return None
            return json.dumps(node, ensure_ascii=False)
        return None


def _sniff_delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","
