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
from clinveil.ingestion.discovery import discover, read_input, sha256_input, unread_id
from clinveil.ingestion.limits import IngestLimits
from clinveil.linking.linker import LinkingStats, RecordEvidence, extract_document_evidence, resolve_identities
from clinveil.models.records import RecordRef
from clinveil.parsing.builder import build_document, build_placeholder
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.processors import RunStats, Sanitizer, sanitized_relpath
from clinveil.security.errors import QuarantineError, safe_reason
from clinveil.security.secrets import ReleaseSecret
from clinveil.utils.resources import peak_rss_mb
from clinveil.validation.contract import check_release


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
    pseudonymizer = Pseudonymizer(secret, policy.date_shift_max_days)
    sanitizer = Sanitizer(pseudonymizer, stats)
    index, evidence = _pass1_collect(input_dir, policy, limits)
    link_result = resolve_identities(evidence, pseudonymizer)
    del evidence  # raw identity evidence never outlives resolution
    link_stats = link_result.stats
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
                entry.input_sha256 = unread_id(f)  # nothing exists to read
                raise QuarantineError("broken_symlink")
            if f.special:
                entry.input_sha256 = unread_id(f)  # a FIFO/socket/device is never opened
                raise QuarantineError("not_a_regular_file")
            if f.escapes_root:
                # The target is NEVER opened (not even to hash it). The release keeps the path covered
                # with an empty, content-free placeholder (filename PII still renamed), declared as
                # "suppressed" under a non-identifying id: see PHASE2_REMEDIATION.md, S1.
                entry.input_sha256 = unread_id(f)
                doc = build_placeholder(f.rel, entry.input_sha256, f.path.suffix.lower())
                analysis = engine.analyze(doc)
                out_rel = sanitized_relpath(doc, analysis, reserved, taken)
                renamed += out_rel != f.rel
                result, _ = sanitizer.sanitize(doc, out_rel, analysis)
                write_sanitized(sanitized_root, out_rel, result)
                entry.output, entry.status, entry.reason = f"sanitized/{out_rel}", "suppressed", "symlink_outside_input"
                files.append(entry)
                input_shas.append(entry.input_sha256)
                continue
            if f.size > policy.max_file_bytes:
                entry.input_sha256 = sha256_input(f.path, input_dir)
                raise QuarantineError("file_too_large")
            raw = read_input(f.path, input_dir, policy.max_file_bytes)
            entry.input_sha256 = hashlib.sha256(raw).hexdigest()
            detection = detect(raw, f.path.suffix.lower(), limits)  # raises QuarantineError for anything unsafe
            doc = build_document(f.rel, entry.input_sha256, len(raw), f.path.suffix.lower(), detection, limits)
            analysis = engine.analyze(doc)
            out_rel = sanitized_relpath(doc, analysis, reserved, taken)
            renamed += out_rel != f.rel
            doc_psns, doc_multi = link_result.for_document(f.rel)
            sanitizer.set_document_pseudonyms(doc_psns, doc_multi)
            result, refs = sanitizer.sanitize(doc, out_rel, analysis)
            write_sanitized(sanitized_root, out_rel, result)
            entry.output, entry.status = f"sanitized/{out_rel}", "sanitized"
            records.extend(refs)
        except Exception as exc:  # noqa: BLE001 - fail safe: quarantine, never copy, never echo content
            entry.output, entry.status, entry.reason = None, "quarantined", safe_reason(exc)
            if not entry.input_sha256:
                # the read failed before any digest existed (vanished, changed, not a regular file):
                # the report still needs an identifier, and it must not come from the path or a target
                entry.input_sha256 = unread_id(f)
        files.append(entry)
        input_shas.append(entry.input_sha256)
    del index, link_result  # the run-local value index and link mapping never outlive the run

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
    _write_detection_summary(output_dir, detection_stats, stats, renamed, link_stats)

    n_san = report["counts"]["files_sanitized"]
    return RunSummary(
        files_total=len(files),
        files_sanitized=n_san,
        files_quarantined=report["counts"]["files_quarantined"],
        records=len(records),
        problems=tuple(check_release(output_dir, input_shas)),
    )


def _pass1_collect(
    input_dir: Path, policy: Policy, limits: IngestLimits
) -> tuple[SensitiveValueIndex, list[RecordEvidence]]:
    """Pass 1: seed the run-local value index and collect normalised identity evidence per record."""
    index = SensitiveValueIndex()
    evidence: list[RecordEvidence] = []
    seeder = DetectionEngine(None)
    for f in discover(input_dir):
        if f.broken or f.special or f.escapes_root or f.size > policy.max_file_bytes:
            continue
        try:
            raw = read_input(f.path, input_dir, policy.max_file_bytes)
            detection = detect(raw, f.path.suffix.lower(), limits)
            doc = build_document(
                f.rel, hashlib.sha256(raw).hexdigest(), len(raw), f.path.suffix.lower(), detection, limits
            )
            analysis = seeder.seed_with_analysis(doc, index)
            evidence.extend(extract_document_evidence(doc, analysis))
        except Exception:  # noqa: BLE001, S112 - the file is quarantined (with a reason) in pass 2
            continue
    return index, evidence


def _write_detection_summary(
    output_dir: Path,
    det: DetectionStats,
    stats: RunStats,
    renamed: int,
    link_stats: LinkingStats | None = None,
) -> None:
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
    if link_stats is not None:
        summary["linking"] = link_stats.as_dict()
    logs = output_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "detection_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
