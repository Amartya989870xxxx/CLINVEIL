# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""IR-based sanitiser: transform fields, re-encode payloads, render, enumerate records.

Phase 1 keeps the *starter's* transformation coverage (the baseline regex on CSV
cells, JSON string values and keys, and whole text documents) so that every
output change in this phase is attributable to ingestion, not detection. New in
Phase 1: decoded base64 payloads are transformed and re-encoded instead of being
passed through raw. CSV headers and filenames are represented in the IR but not
transformed yet (Phase 2 detection decides).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from clinveil.detection import baseline_regex
from clinveil.ingestion.decoding import encode_text
from clinveil.linking.linker import link_record
from clinveil.models.document import Base64Segment, Document, Field, FieldKind, Format
from clinveil.models.records import RecordRef
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.render import render

#: Field kinds the Phase 1 transformer rewrites (starter coverage).
TRANSFORMED_KINDS = frozenset({FieldKind.CELL, FieldKind.JSON_STRING, FieldKind.JSON_KEY, FieldKind.TEXT})


@dataclass
class RunStats:
    identifiers: int = 0
    generalized: int = 0
    suppressed: int = 0
    payloads_rewritten: int = 0


class Sanitizer:
    def __init__(self, pseudonymizer: Pseudonymizer, stats: RunStats) -> None:
        self._psn = pseudonymizer
        self.stats = stats

    # ------------------------------------------------------------------ primitives
    def clean_text(self, text: str) -> str:
        text, n = baseline_regex.redact(text)
        self.stats.identifiers += n
        return text

    def _reencode(self, text: str, seg: Base64Segment) -> str:
        out = base64.b64encode(encode_text(text, seg.encoding)).decode("ascii")
        return out if seg.padded else out.rstrip("=")

    def transform_field(self, f: Field, children: dict[str, Field]) -> str:
        """New value for a text field; base64 segments are decoded, cleaned, re-encoded."""
        value: str = f.value
        if not f.segments:
            return self.clean_text(value)
        parts, pos = [], 0
        for seg in f.segments:
            if seg.start > pos:
                parts.append(self.clean_text(value[pos : seg.start]))
            child = children[seg.child]
            cleaned = self.clean_text(child.value)
            if cleaned == child.value:
                parts.append(value[seg.start : seg.end])  # unchanged: keep the exact original encoding
            else:
                parts.append(self._reencode(cleaned, seg))
                self.stats.payloads_rewritten += 1
            pos = seg.end
        if pos < len(value):
            parts.append(self.clean_text(value[pos:]))
        return "".join(parts)

    # ------------------------------------------------------------------ documents
    def sanitize(self, doc: Document, out_rel: str) -> tuple[str, list[RecordRef]]:
        children = {f.address: f for f in doc.fields if f.kind is FieldKind.BASE64_TEXT}
        replacements: dict[str, str] = {}
        for f in doc.fields:
            if f.kind in TRANSFORMED_KINDS:
                new = self.transform_field(f, children)
                if new != f.value:
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
