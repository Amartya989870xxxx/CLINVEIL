# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""End-to-end release pipeline (two passes).

    pass 1  discover -> guard -> detect -> build IR -> seed the run-local value index
    pass 2  discover -> guard -> detect -> build IR -> analyse (semantics, detectors,
            propagation, resolution) -> rename PII paths -> sanitise -> render
            -> export -> self-check

Two passes are required because a patient's name or ID confirmed in one file
(a registration row) must be recognised wherever it reappears (a note, a
filename, a JSON key, a base64 attachment) even if that file is processed first.
Pass 1 keeps no documents in memory, only the index; files are re-read in pass 2.

Fail-safe rules:
* any per-file exception quarantines that file; the reason is a fixed code
  (:mod:`clinveil.security.errors`) or an exception type name, never a message;
* nothing is ever copied: every exported byte is rendered from the IR;
* no temporary files are written; input is opened read-only; the value index
  is never serialised;
* the release is re-verified on disk before exit 0 (false-success guard).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from clinveil.config.policy import Policy
from clinveil.detection import caches
from clinveil.detection.engine import DetectionEngine, DetectionStats
from clinveil.detection.value_index import SensitiveValueIndex
from clinveil.export.release import (
    FileEntry,
    ReleaseCounts,
    build_report,
    write_records,
    write_report,
    write_sanitized,
)
from clinveil.ingestion.detect import detect
from clinveil.ingestion.discovery import discover, sha256_file
from clinveil.ingestion.limits import IngestLimits
from clinveil.models.records import RecordRef
from clinveil.parsing.builder import build_document
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.processors import RunStats, Sanitizer, sanitized_relpath
from clinveil.security.errors import QuarantineError, safe_reason
from clinveil.security.secrets import ReleaseSecret
from clinveil.utils.resources import peak_rss_mb
from clinveil.validation.contract import check_release

_EMPTY_SHA = hashlib.sha256(b"").hexdigest()


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
    try:
        return _run(input_dir, output_dir, secret, policy)
    finally:
        caches.clear_all()  # memo caches hold input fragments: they never outlive the run


def _run(input_dir: Path, output_dir: Path, secret: ReleaseSecret, policy: Policy) -> RunSummary:
    t0 = time.monotonic()
    sanitized_root = output_dir / "sanitized"
    sanitized_root.mkdir(parents=True, exist_ok=True)
    limits = IngestLimits.from_policy(policy)

    stats = RunStats()
    sanitizer = Sanitizer(Pseudonymizer(secret, policy.date_shift_max_days), stats)
    index = _seed_index(input_dir, policy, limits)
    detection_stats = DetectionStats()
    engine = DetectionEngine(index, detection_stats)
    files: list[FileEntry] = []
    records: list[RecordRef] = []
    input_shas: list[str] = []
    discovered = list(discover(input_dir))
    reserved = {f.rel for f in discovered}
    taken: set[str] = set()
    renamed = 0

    for f in discovered:
        entry = FileEntry(input_sha256="")
        try:
            if f.broken:
                entry.input_sha256 = _EMPTY_SHA  # nothing exists to read: the SHA-256 of zero bytes
                raise QuarantineError("broken_symlink")
            if f.escapes_root:
                # Never parsed, never exported. The official contract identifies every input by the
                # SHA-256 of the bytes behind its path (validate_output follows the link), so a regular,
                # size-capped target is stream-hashed; anything larger is not read at all.
                entry.input_sha256 = sha256_file(f.path) if 0 <= f.size <= policy.max_file_bytes else _EMPTY_SHA
                raise QuarantineError("symlink_outside_input")
            if f.size > policy.max_file_bytes:
                entry.input_sha256 = sha256_file(f.path)
                raise QuarantineError("file_too_large")
            raw = f.path.read_bytes()
            entry.input_sha256 = hashlib.sha256(raw).hexdigest()
            detection = detect(raw, f.path.suffix.lower(), limits)  # raises QuarantineError for anything unsafe
            doc = build_document(f.rel, entry.input_sha256, len(raw), f.path.suffix.lower(), detection, limits)
            analysis = engine.analyze(doc)
            out_rel = sanitized_relpath(doc, analysis, reserved, taken)
            renamed += out_rel != f.rel
            result, refs = sanitizer.sanitize(doc, out_rel, analysis)
            write_sanitized(sanitized_root, out_rel, result)
            entry.output, entry.status = f"sanitized/{out_rel}", "sanitized"
            records.extend(refs)
        except Exception as exc:  # noqa: BLE001 - fail safe: quarantine, never copy, never echo content
            entry.output, entry.status, entry.reason = None, "quarantined", safe_reason(exc)
        files.append(entry)
        input_shas.append(entry.input_sha256)
    del index  # the run-local value index never outlives the run

    exported = {e.output for e in files if e.output}
    records = [r for r in records if r.file in exported]
    write_records(output_dir, records)

    counts = ReleaseCounts(
        identifiers_detected=stats.identifiers,
        records_generalized=stats.generalized,
        records_suppressed=stats.suppressed,
    )
    report = build_report(files, records, counts, time.monotonic() - t0, peak_rss_mb(), entities=stats.entities)
    write_report(output_dir, report)
    _write_detection_summary(output_dir, detection_stats, stats, renamed)

    n_san = report["counts"]["files_sanitized"]
    return RunSummary(
        files_total=len(files),
        files_sanitized=n_san,
        files_quarantined=len(files) - n_san,
        records=len(records),
        problems=tuple(check_release(output_dir, input_shas)),
    )


def _seed_index(input_dir: Path, policy: Policy, limits: IngestLimits) -> SensitiveValueIndex:
    """Pass 1: collect high-confidence personal values from every ingestible file."""
    index = SensitiveValueIndex()
    seeder = DetectionEngine(None)
    for f in discover(input_dir):
        if f.broken or f.escapes_root or f.size > policy.max_file_bytes:
            continue
        try:
            raw = f.path.read_bytes()
            detection = detect(raw, f.path.suffix.lower(), limits)
            doc = build_document(
                f.rel, hashlib.sha256(raw).hexdigest(), len(raw), f.path.suffix.lower(), detection, limits
            )
            seeder.seed(doc, index)
        except Exception:  # noqa: BLE001, S112 - the file is quarantined (with a reason) in pass 2
            continue
    return index


def _write_detection_summary(output_dir: Path, det: DetectionStats, stats: RunStats, renamed: int) -> None:
    """Counts only (no values, names or paths): what was found, by what, where, and what was applied."""
    summary = {
        "schema": "clinveil-detection-summary/1",
        **det.as_dict(),
        "redactions_applied": stats.identifiers,
        "redactions_by_entity": dict(sorted(stats.entities.items())),
        "generalized": stats.generalized,
        "payloads_rewritten": stats.payloads_rewritten,
        "attachments_withheld": stats.attachments_withheld,
        "files_renamed": renamed,
    }
    logs = output_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "detection_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
