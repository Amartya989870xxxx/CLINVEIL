"""Minimal in-process release check (a subset of the official ``validate_output.py``).

Returned problem strings are fixed templates with counts only: no paths, no content.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from clinveil.parsing.csv_format import delimiter_for, read_rows, sniff_delimiter
from clinveil.privacy.pseudonym import ALPHABET, PREFIX

STATUSES = frozenset({"sanitized", "quarantined", "suppressed"})
_PSN_RE = re.compile(rf"^{re.escape(PREFIX)}[{ALPHABET}]{{6}}$")


def check_release(
    out_dir: Path,
    input_shas: list[str],
    *,
    issued_pseudonyms: frozenset[str] | None = None,
) -> list[str]:
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
        problems.extend(_check_records_pseudonyms(out_dir, rj, report, issued_pseudonyms=issued_pseudonyms))
    return problems


def _check_records_pseudonyms(
    out_dir: Path,
    rj: Path,
    report: dict,
    *,
    issued_pseudonyms: frozenset[str] | None = None,
) -> list[str]:
    """Per-RECORD pseudonym validation (Phase 3.1 / 3.2).

    SPEC §6: "the ``patient`` value must actually appear inside that exported record". For each
    ``records.jsonl`` line the record is located by its locator (``row:N`` in CSV/TSV, an RFC 6901
    pointer in JSON, ``doc`` = whole file) and checked:

    * a linked record contains its OWN pseudonym (not merely somewhere in the file);
    * no record contains a DIFFERENT patient's pseudonym (when ``issued_pseudonyms`` is supplied
      by the pipeline, only tokens actually issued by this release count as foreign so pre-existing
      PSN-shaped clinical codes in unlinked notes do not cause false contract failures, F8);
    * an unlinked record contains no issued pseudonym;
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
        foreign_candidates = (tokens & issued_pseudonyms) if issued_pseudonyms is not None else tokens
        if psn is None:
            if foreign_candidates:
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
        if foreign_candidates - {psn}:
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
    """An exported file parsed just enough to cut out one record by its locator.

    The structure is chosen by the LOCATOR, never by the file extension (D14, NEW-6A): a JSON
    pointer is resolved in the parsed JSON (even when the file is named ``.csv``/``.tsv``/``.dat``),
    a ``row:N`` locator in the delimited table (the delimiter sniffed exactly as ingestion does).
    Each structure is parsed lazily, at most once; malformed content makes the record unlocatable.
    """

    __slots__ = ("_json", "_json_done", "_rows", "_rows_done", "_suffix", "_text")

    def __init__(self, text: str, suffix: str) -> None:
        self._text, self._suffix = text, suffix
        self._rows: list[list[str]] | None = None
        self._json: object = None
        self._rows_done = self._json_done = False

    def __repr__(self) -> str:
        return "_ParsedOutput(<redacted>)"

    @classmethod
    def load(cls, path: Path) -> _ParsedOutput | None:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None
        return cls(text, path.suffix.lower())

    def _table(self) -> list[list[str]] | None:
        if not self._rows_done:
            self._rows_done = True
            try:
                delim = sniff_delimiter(self._text, delimiter_for(self._suffix))
                self._rows = read_rows(self._text, delim)
            except (csv.Error, ValueError):
                self._rows = None
        return self._rows

    def _data(self) -> object:
        if not self._json_done:
            self._json_done = True
            try:
                self._json = json.loads(self._text)
            except ValueError:
                self._json = None
        return self._json

    def record_text(self, loc: str) -> str | None:
        if loc == "doc":
            return self._text
        if loc.startswith("row:"):
            rows = self._table()
            if rows is None:
                return None
            try:
                i = int(loc[4:]) + 1  # header excluded from row numbering
            except ValueError:
                return None
            return "\x1f".join(rows[i]) if 0 < i < len(rows) else None
        if loc.startswith("/"):
            node = self._data()
            if node is None:
                return None
            for part in (p.replace("~1", "/").replace("~0", "~") for p in loc.split("/")[1:]):
                if isinstance(node, list) and part.isdigit() and int(part) < len(node):
                    node = node[int(part)]
                elif isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    return None
            return json.dumps(node, ensure_ascii=False)
        return None
