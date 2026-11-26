# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Apply detection findings to the IR, re-encode payloads, render, enumerate records.

Replacement policy (deterministic, non-sensitive, schema-safe):

* text spans -> typed placeholders (``[NAME]``, ``[RELATIVE]``, ``[PHONE]``, ``[MRN]``…);
  filenames use bare words (``NAME``, ``MRN``) so paths stay simple;
* JSON numbers holding PII -> ``0`` (the value type is preserved);
* FHIR ``birthDate`` -> birth year only (``1977``): still a valid FHIR ``date`` and
  no longer the exact DOB (interim treatment until Phase 4's per-patient shift);
* a base64 payload is rebuilt from its decoded child's findings and re-encoded;
  an untouched payload keeps its original bytes;
* CSV headers that held personal values are de-duplicated (``[MRN] [NAME] #2``).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from clinveil.detection.engine import DocumentAnalysis
from clinveil.detection.resolve import apply_spans
from clinveil.ingestion.decoding import encode_text
from clinveil.linking.linker import link_record
from clinveil.models.document import Base64Segment, Document, Field, FieldKind, Format
from clinveil.models.findings import Action, EntityType, Finding
from clinveil.models.records import RecordRef
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.render import render

PLACEHOLDER = {
    EntityType.PATIENT_NAME: "[NAME]",
    EntityType.RELATIVE_NAME: "[RELATIVE]",
    EntityType.PHONE: "[PHONE]",
    EntityType.EMAIL: "[EMAIL]",
    EntityType.AADHAAR: "[AADHAAR]",
    EntityType.AADHAAR_MASKED: "[AADHAAR]",
    EntityType.ABHA_NUMBER: "[ABHA]",
    EntityType.ABHA_ADDRESS: "[ABHA]",
    EntityType.PAN: "[PAN]",
    EntityType.MRN: "[MRN]",
    EntityType.INSURANCE_ID: "[INSURANCE_ID]",
    EntityType.HOUSE: "[HOUSE]",
    EntityType.LOCALITY: "[LOCALITY]",
    EntityType.LANDMARK: "[LANDMARK]",
    EntityType.VILLAGE: "[VILLAGE]",
    EntityType.PIN: "[PIN]",
    EntityType.DOB: "[DOB]",
    EntityType.DOCTOR_NAME: "[DOCTOR]",
}
FILENAME_WORD = {e: p.strip("[]").replace("_", "-") for e, p in PLACEHOLDER.items()}


@dataclass
class RunStats:
    identifiers: int = 0  # redactions actually applied to the release
    generalized: int = 0
    suppressed: int = 0
    payloads_rewritten: int = 0
    entities: dict[str, int] = field(default_factory=dict)  # applied redactions by entity type

    def count(self, findings: list[Finding]) -> None:
        for f in findings:
            self.identifiers += 1
            self.entities[f.entity.value] = self.entities.get(f.entity.value, 0) + 1


def replacement_text(value: str, findings: list[Finding], *, filename: bool = False, fhir_date: bool = False) -> str:
    spans = []
    for f in findings:
        if f.action is Action.GENERALIZE and fhir_date:
            spans.append((f.start, f.end, value[f.start : f.start + 4]))  # birth year: valid FHIR date
        else:
            spans.append((f.start, f.end, (FILENAME_WORD if filename else PLACEHOLDER)[f.entity]))
    return apply_spans(value, spans)


class Sanitizer:
    def __init__(self, pseudonymizer: Pseudonymizer, stats: RunStats) -> None:
        self._psn = pseudonymizer
        self.stats = stats

    def _reencode(self, text: str, seg: Base64Segment) -> str:
        out = base64.b64encode(encode_text(text, seg.encoding)).decode("ascii")
        return out if seg.padded else out.rstrip("=")

    def _new_value(self, f: Field, analysis: DocumentAnalysis, children: dict[str, Field]) -> str | int | None:
        own = analysis.findings.get(f.address, [])
        if f.kind is FieldKind.JSON_NUMBER:
            if own:
                self.stats.count(own)
                return 0
            return None
        value: str = f.value
        if not f.segments:
            if not own:
                return None
            self.stats.count(own)
            if any(x.action is Action.GENERALIZE for x in own):
                self.stats.generalized += 1
            return replacement_text(value, own, fhir_date=f.fhir is not None)
        spans: list[tuple[int, int, str]] = []
        outside = [x for x in own if not any(x.start < s.end and s.start < x.end for s in f.segments)]
        self.stats.count(outside)
        for x in outside:
            spans.append((x.start, x.end, PLACEHOLDER[x.entity]))
        for seg in f.segments:
            child = children[seg.child]
            child_findings = analysis.findings.get(child.address, [])
            if child_findings:
                self.stats.count(child_findings)
                self.stats.payloads_rewritten += 1
                spans.append((seg.start, seg.end, self._reencode(replacement_text(child.value, child_findings), seg)))
        return apply_spans(value, spans) if spans else None

    def sanitize(self, doc: Document, out_rel: str, analysis: DocumentAnalysis) -> tuple[str, list[RecordRef]]:
        children = {f.address: f for f in doc.fields if f.kind is FieldKind.BASE64_TEXT}
        replacements: dict[str, object] = {}
        headers_seen: dict[str, int] = {}
        for f in doc.fields:
            if f.kind is FieldKind.FILENAME:
                # applied by sanitized_relpath (the rename happens before sanitize): count them here
                self.stats.count(analysis.findings.get(f.address, []))
                continue
            if f.kind is FieldKind.BASE64_TEXT:
                continue
            new = self._new_value(f, analysis, children)
            if f.kind is FieldKind.HEADER:
                name = new if new is not None else f.value
                n = headers_seen.get(name, 0) + 1
                headers_seen[name] = n
                if n > 1 and new is not None:
                    new = f"{name} #{n}"
            if new is not None and new != f.value:
                replacements[f.address] = new
        return render(doc, replacements), self._records(doc, out_rel)

    def _records(self, doc: Document, out_rel: str) -> list[RecordRef]:
        file = f"sanitized/{out_rel}"
        if doc.source.format in (Format.CSV, Format.TSV):
            delim = doc.source.delimiter or ","
            refs = []
            for i, row in enumerate(doc.native[1:] if doc.native else []):
                key = link_record(delim.join(row))
                # TODO(phase3): write the pseudonym INSIDE the row (patient_ref column)
                refs.append(RecordRef(file=file, loc=f"row:{i}", patient=self._psn.pseudonym(key) if key else None))
            return refs
        return [RecordRef(file=file, loc=loc, patient=None) for loc in doc.records]


def sanitized_relpath(doc: Document, analysis: DocumentAnalysis, reserved: set[str], taken: set[str]) -> str:
    """Rename path components that contain personal data; keep extensions; ensure uniqueness.

    ``reserved`` holds every original input path (an unrenamed file always keeps its
    path); ``taken`` holds output paths already assigned in this run. Collisions get a
    deterministic ``-2``, ``-3``… suffix in processing (sorted) order.
    """
    parts = doc.source.rel.split("/")
    new_parts = []
    for i, part in enumerate(parts):
        findings = analysis.findings.get(f"@filename/{i}", [])
        new_parts.append(replacement_text(part, findings, filename=True) if findings else part)
    rel = "/".join(new_parts)
    if rel != doc.source.rel:
        stem, dot, ext = rel.rpartition(".") if "." in new_parts[-1] else (rel, "", "")
        candidate, n = rel, 1
        while candidate in taken or candidate in reserved:
            n += 1
            candidate = f"{stem}-{n}{dot}{ext}" if dot else f"{rel}-{n}"
        rel = candidate
    taken.add(rel)
    return rel
