# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""End-to-end release pipeline: discover -> guard -> decode -> sanitise -> export -> self-check.

Phase 0 is a behaviour-preserving refactor of the official starter: on any input
without symlinks or oversized files, ``sanitized/`` and ``records.jsonl`` are
byte-identical to ``starter/main.py`` (pinned by ``tests/regression/test_starter_parity.py``).

Hardening added over the starter (no effect on well-formed input):
* symlinks resolving outside the input root are quarantined unparsed;
* files above ``policy.max_file_bytes`` are quarantined unread (streamed hash);
* *any* per-file exception quarantines that file; reasons are fixed codes or
  exception type names, never messages (which can echo PII);
* the release is re-verified on disk before exit 0 (false-success guard).
"""

from __future__ import annotations

import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from clinveil.config.policy import Policy
from clinveil.export.release import (
    FileEntry,
    ReleaseCounts,
    build_report,
    write_records,
    write_report,
    write_sanitized,
)
from clinveil.ingestion.decoding import decode
from clinveil.ingestion.discovery import discover, sha256_file
from clinveil.models.records import RecordRef
from clinveil.parsing.csv_format import delimiter_for
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.processors import RunStats, Sanitizer
from clinveil.security.errors import QuarantineError, safe_reason
from clinveil.security.secrets import ReleaseSecret
from clinveil.utils.resources import peak_rss_mb
from clinveil.validation.contract import check_release

SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".json", ".txt")
RECURSION_LIMIT = 5000  # the practice data contains a 1,500-level-deep JSON


@dataclass(frozen=True)
class RunSummary:
    files_total: int
    files_sanitized: int
    files_quarantined: int
    records: int
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def run(input_dir: Path, output_dir: Path, secret: ReleaseSecret, policy: Policy) -> RunSummary:
    t0 = time.monotonic()
    sanitized_root = output_dir / "sanitized"
    sanitized_root.mkdir(parents=True, exist_ok=True)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), RECURSION_LIMIT))

    stats = RunStats()
    sanitizer = Sanitizer(Pseudonymizer(secret, policy.date_shift_max_days), stats)
    files: list[FileEntry] = []
    records: list[RecordRef] = []
    input_shas: list[str] = []

    for f in discover(input_dir):
        entry = FileEntry(input_sha256="")
        try:
            if f.escapes_root:
                entry.input_sha256 = sha256_file(f.path)  # hashed for the report, never parsed
                raise QuarantineError("symlink_outside_input")
            if f.size > policy.max_file_bytes:
                entry.input_sha256 = sha256_file(f.path)
                raise QuarantineError("file_too_large")
            raw = f.path.read_bytes()
            entry.input_sha256 = hashlib.sha256(raw).hexdigest()
            out_rel, refs = _process_file(sanitizer, f.path.suffix.lower(), raw, f.rel, sanitized_root)
            entry.output, entry.status = f"sanitized/{out_rel}", "sanitized"
            records.extend(refs)
        except Exception as exc:  # noqa: BLE001 - fail safe: quarantine, never copy, never echo content
            entry.output, entry.status, entry.reason = None, "quarantined", safe_reason(exc)
        files.append(entry)
        input_shas.append(entry.input_sha256)

    exported = {e.output for e in files if e.output}
    records = [r for r in records if r.file in exported]
    write_records(output_dir, records)

    counts = ReleaseCounts(
        identifiers_detected=stats.identifiers,
        records_generalized=stats.generalized,
        records_suppressed=stats.suppressed,
    )
    report = build_report(files, records, counts, time.monotonic() - t0, peak_rss_mb())
    write_report(output_dir, report)

    n_san = report["counts"]["files_sanitized"]
    return RunSummary(
        files_total=len(files),
        files_sanitized=n_san,
        files_quarantined=len(files) - n_san,
        records=len(records),
        problems=tuple(check_release(output_dir, input_shas)),
    )


def _process_file(
    sanitizer: Sanitizer, ext: str, raw: bytes, rel: str, sanitized_root: Path
) -> tuple[str, list[RecordRef]]:
    if ext not in SUPPORTED_EXTENSIONS:
        raise QuarantineError("unsupported_format")
    if not raw.strip():
        raise QuarantineError("empty_file")
    text = decode(raw)
    if text is None:
        raise QuarantineError("undecodable_text")
    # TODO(phase2): a file NAME can contain PII: rename it and report the new path
    out_rel = rel
    if ext in (".csv", ".tsv"):
        result, refs = sanitizer.process_csv(text, delimiter_for(ext), out_rel)
    elif ext == ".json":
        result, refs = sanitizer.process_json(text, out_rel)
    else:
        result, refs = sanitizer.process_text(text, out_rel)
    write_sanitized(sanitized_root, out_rel, result)
    return out_rel, refs
