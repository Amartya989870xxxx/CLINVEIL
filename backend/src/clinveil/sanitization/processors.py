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
* CSV headers that held personal values are de-duplicated (``[MRN] [NAME] #2``);
* a binary payload (scan, photo, PDF) cannot be sanitised: it is *withheld*. A JSON
  object member that is entirely the payload is removed with its key (FHIR
  ``Attachment.data``, ``Binary.data`` and ``valueBase64Binary`` are optional;
  ``contentType`` and the rest of the resource stay) and, for a declared attachment, its
  ``hash`` and ``size`` go too. A payload that is an array element, or is embedded in
  text, is replaced by ``[ATTACHMENT-WITHHELD]`` so array lengths and positions are kept.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field

from clinveil.detection.engine import DocumentAnalysis
from clinveil.detection.resolve import apply_spans
from clinveil.ingestion.decoding import encode_text
from clinveil.linking.linker import link_record
from clinveil.models.document import Base64Segment, Document, Field, FieldKind, Format
from clinveil.models.findings import Action, EntityType, Finding
from clinveil.models.records import RecordRef
from clinveil.parsing.json_format import pointer
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.render import WITHHELD, render

WITHHELD_TEXT = "[ATTACHMENT-WITHHELD]"

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
    identifiers: int = 0  # transformations actually applied to the release (unchanged spans never count)
    generalized: int = 0  # distinct records in which at least one value was generalised
    suppressed: int = 0
    payloads_rewritten: int = 0
    attachments_withheld: int = 0
    entities: dict[str, int] = field(default_factory=dict)  # applied redactions by entity type
    _generalized_records: set[tuple[str, str]] = field(default_factory=set, repr=False)

    def count(self, findings: list[Finding]) -> None:
        for f in findings:
            self.identifiers += 1
            self.entities[f.entity.value] = self.entities.get(f.entity.value, 0) + 1

    def generalized_in(self, document: str, record: str | None) -> None:
        key = (document, record or "")
        if key not in self._generalized_records:
            self._generalized_records.add(key)
            self.generalized += 1


def _replacement(value: str, f: Finding, *, filename: bool, fhir_date: bool) -> str:
    if f.action is Action.GENERALIZE and fhir_date:
        return value[f.start : f.start + 4]  # birth year: still a valid FHIR date
    return (FILENAME_WORD if filename else PLACEHOLDER)[f.entity]


def effective(value: str, findings: list[Finding], *, filename: bool = False, fhir_date: bool = False) -> list[Finding]:
    """Findings whose replacement really changes the text (``1980`` -> ``1980`` is no transformation)."""
    return [
        f for f in findings if _replacement(value, f, filename=filename, fhir_date=fhir_date) != value[f.start : f.end]
    ]


def replacement_text(value: str, findings: list[Finding], *, filename: bool = False, fhir_date: bool = False) -> str:
    spans = [(f.start, f.end, _replacement(value, f, filename=filename, fhir_date=fhir_date)) for f in findings]
    return apply_spans(value, spans)


class Sanitizer:
    def __init__(self, pseudonymizer: Pseudonymizer, stats: RunStats) -> None:
        self._psn = pseudonymizer
        self.stats = stats

    def _reencode(self, text: str, seg: Base64Segment) -> str:
        raw = encode_text(text, seg.encoding)
        out = (base64.urlsafe_b64encode(raw) if seg.urlsafe else base64.b64encode(raw)).decode("ascii")
        return out if seg.padded else out.rstrip("=")

    def _new_value(self, f: Field, analysis: DocumentAnalysis, children: dict[str, Field]) -> object:
        own = analysis.findings.get(f.address, [])
        if f.kind is FieldKind.JSON_NUMBER:
            if own:
                self.stats.count(own)
                return 0
            return None
        value: str = f.value
        if not f.segments:
            applied = effective(value, own, fhir_date=f.fhir is not None)
            if not applied:
                return None
            self.stats.count(applied)
            if any(x.action is Action.GENERALIZE for x in applied):
                self.stats.generalized_in(applied[0].document, f.record)
            return replacement_text(value, applied, fhir_date=f.fhir is not None)
        if (
            f.kind is FieldKind.JSON_STRING
            and f.path
            and isinstance(f.path[-1], str)  # an object member; array elements keep their slot (see below)
            and len(f.segments) == 1
            and f.segments[0].withheld
            and not value[: f.segments[0].start].strip()
            and not value[f.segments[0].end :].strip()
        ):
            self.stats.attachments_withheld += 1
            return WITHHELD  # the whole value is a binary payload: drop the key
        spans: list[tuple[int, int, str]] = []
        outside = [x for x in own if not any(x.start < s.end and s.start < x.end for s in f.segments)]
        self.stats.count(outside)
        for x in outside:
            spans.append((x.start, x.end, PLACEHOLDER[x.entity]))
        for seg in f.segments:
            if seg.withheld:
                self.stats.attachments_withheld += 1
                spans.append((seg.start, seg.end, WITHHELD_TEXT))
                continue
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
                self.stats.count(effective(f.value, analysis.findings.get(f.address, []), filename=True))
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
            if new is WITHHELD and f.segments[0].declared_type is not None:
                # the attachment's integrity metadata describes the removed bytes: Attachment.hash is a
                # SHA-1 fingerprint of the image (it could confirm a known photo), Attachment.size is stale
                parent = _parent(doc.native, f.path)
                for k in ("hash", "size"):
                    if isinstance(parent, dict) and k in parent:
                        replacements[pointer((*f.path[:-1], k))] = WITHHELD
        if doc.source.format is Format.FHIR:
            replacements.update(fhir_id_rewrites(doc, analysis))
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


def _parent(root: object, path: tuple) -> object:
    node = root
    for part in path[:-1]:
        try:
            node = node[part]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return None
    return node


_RID_NS = uuid.UUID("8f1d6f2e-4c1b-5a7e-9d3c-2b6a1e0f5c47")  # fixed namespace: new ids carry no input data


def fhir_id_rewrites(doc: Document, analysis: DocumentAnalysis) -> dict[str, str]:
    """Rewrite identifying FHIR ids together with their ``fullUrl`` s and every reference to them.

    An entry is renamed when the detector flagged its ``resource.id`` or ``fullUrl`` (an
    embedded UHID/MRN, a name, a confirmed value). The new id is ``rid-<entry index>``
    (a valid FHIR id); a ``fullUrl`` ending in the old id keeps its base, otherwise it
    becomes a ``urn:uuid`` derived only from the entry index. References that resolved
    to a renamed entry are rewritten to match, so the Bundle still resolves; a flagged
    reference that resolved to nothing has its id segment replaced (``rid-x<n>``).
    """
    idx = doc.fhir
    if idx is None:
        return {}
    flagged = {a for a, f in analysis.findings.items() if any(x.detector == "fhir_id" for x in f)}
    if not flagged:
        return {}
    out: dict[str, str] = {}
    renamed: dict[
        int, tuple[str | None, str | None, str, str | None]
    ] = {}  # entry -> (old id, old url, new id, new url)
    entries = idx.entries if idx.is_bundle else []
    for e in entries:
        id_ptr = pointer(("entry", e.index, "resource", "id"))
        url_ptr = pointer(("entry", e.index, "fullUrl"))
        if id_ptr not in flagged and url_ptr not in flagged:
            continue
        new_id = f"rid-{e.index}"
        new_url = e.full_url
        if e.full_url:
            if e.resource_id and e.full_url.endswith("/" + e.resource_id):
                new_url = e.full_url[: -len(e.resource_id)] + new_id
            elif url_ptr in flagged:
                new_url = f"urn:uuid:{uuid.uuid5(_RID_NS, str(e.index))}"
            if new_url != e.full_url:
                out[url_ptr] = new_url
        if e.resource_id is not None:
            out[id_ptr] = new_id
        renamed[e.index] = (e.resource_id, e.full_url, new_id, new_url)
    if not idx.is_bundle and "/id" in flagged:
        out["/id"] = "rid-0"
    stray = 0
    for r in idx.references:
        if r.contained:
            continue
        if r.target_entry in renamed:
            old_id, old_url, new_id, new_url = renamed[r.target_entry]
            if old_url is not None and r.value == old_url and new_url is not None:
                out[r.pointer] = new_url
            elif old_id and r.value.endswith("/" + old_id):
                out[r.pointer] = r.value[: -len(old_id)] + new_id
        elif r.pointer in flagged:
            stray += 1
            cut = max(r.value.rfind("/"), r.value.rfind(":")) + 1
            out[r.pointer] = r.value[:cut] + f"rid-x{stray}"
    return out
