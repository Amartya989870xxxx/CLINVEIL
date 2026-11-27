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
import re
import uuid
from dataclasses import dataclass, field

from clinveil.detection.engine import DocumentAnalysis
from clinveil.detection.resolve import apply_spans
from clinveil.detection.semantics import Sem
from clinveil.ingestion.decoding import encode_text
from clinveil.models.channels import Channel
from clinveil.models.document import Base64Segment, Document, Field, FieldKind, Format
from clinveil.models.findings import DIRECT, Action, EntityType, Finding
from clinveil.models.records import RecordRef
from clinveil.parsing.attachments import is_declared_data_key
from clinveil.parsing.json_format import pointer
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.privacy.transform import band_age_text, numeric_date_order_evidence, pin_prefix, shift_date_text
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


def _replacement(
    value: str, f: Finding, *, filename: bool, fhir_date: bool, pseudonym: str | None = None, pin_ok: bool = False
) -> str:
    if pseudonym is not None:
        return pseudonym
    if f.action is Action.GENERALIZE and fhir_date:
        return value[f.start : f.start + 4]  # birth year: still a valid FHIR date
    if f.entity is EntityType.PIN and pin_ok and not filename:
        prefix = pin_prefix(value[f.start : f.end])  # Phase 4: true 3-digit prefix, rest suppressed
        if prefix is not None:
            return prefix
    return (FILENAME_WORD if filename else PLACEHOLDER)[f.entity]


def effective(
    value: str,
    findings: list[Finding],
    *,
    filename: bool = False,
    fhir_date: bool = False,
    psn_target: tuple[int, str] | None = None,
    pin_ok: bool = False,
) -> list[tuple[Finding, str | None]]:
    """Findings whose replacement really changes the text (``1980`` -> ``1980`` is no transformation)."""
    out: list[tuple[Finding, str | None]] = []
    for idx, f in enumerate(findings):
        psn = psn_target[1] if (psn_target is not None and idx == psn_target[0]) else None
        if (
            _replacement(value, f, filename=filename, fhir_date=fhir_date, pseudonym=psn, pin_ok=pin_ok)
            != value[f.start : f.end]
        ):
            out.append((f, psn))
    return out


def replacement_text(
    value: str,
    findings: list[Finding],
    *,
    filename: bool = False,
    fhir_date: bool = False,
    psn_target: tuple[int, str] | None = None,
) -> str:
    spans = [
        (
            f.start,
            f.end,
            _replacement(
                value,
                f,
                filename=filename,
                fhir_date=fhir_date,
                pseudonym=psn_target[1] if (psn_target is not None and idx == psn_target[0]) else None,
            ),
        )
        for idx, f in enumerate(findings)
    ]
    return apply_spans(value, spans)


_DATE_LABEL_RE = re.compile(
    r"(?i)(?:^|[^a-z])(?:date|dated|dt|datetime|tarikh|तारीख|दिनांक)(?:$|[^a-z])|[a-z]date(?:time)?$"
)
_NOT_DATE_LABEL_RE = re.compile(r"(?i)birth|dob|जन्म|generated|updated|export|created")
_FULL_DATE_VALUE_RE = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+(?:Z|[+\-]\d{2}:?\d{2})?)?|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}"
    r"|\d{1,2}[ \-][A-Za-z]{3,9}[ \-]\d{4})\s*$"
)


def _field_name(f: Field) -> str:
    """The field's own name: a JSON member key or a column label. Birth / export / audit dates are excluded."""
    name = f.path[-1] if f.path and isinstance(f.path[-1], str) else (f.label or "")
    name = str(name)
    return "" if _NOT_DATE_LABEL_RE.search(name) else name


class Sanitizer:
    def __init__(
        self, pseudonymizer: Pseudonymizer, stats: RunStats, *, age_band_years: int = 5, min_group_size: int = 5
    ) -> None:
        self._psn = pseudonymizer
        self.stats = stats
        self._age_band_years = age_band_years
        self._pending_psns: dict[str, str] = {}
        self._pending_multi: frozenset[str] = frozenset()
        self._shift_keys: dict[str | None, str] = {}
        self._pin_suppressed: set[str | None] = set()
        self._date_order: str | None = None
        self.min_group_size = min_group_size

    def _rare_pin_records(self, doc: Document, analysis: DocumentAnalysis) -> set[str | None]:
        """Rare-cell protection for the PIN prefix (Phase 4, ``min_group_size``).

        Quasi-identifier combination per record in this document: (5-year age band, gender, true 3-digit PIN
        prefix). A record whose combination is shared by fewer than ``min_group_size`` records of the document
        keeps NO PIN digits (full ``[PIN]`` suppression). Missing age or gender is treated as its own value, so
        small documents are suppressed (conservative). Records without a PIN are unaffected.
        """
        qi: dict[str | None, list[object]] = {}
        for f in doc.fields:
            if f.channel is not Channel.CONTENT or not isinstance(f.value, str):
                continue
            rec = qi.setdefault(f.record, [None, None, None])
            sem = analysis.semantics.get(f.address)
            if sem is not None and sem.sem is Sem.AGE and rec[0] is None:
                rec[0] = band_age_text(f.value, self._age_band_years)
            elif sem is not None and sem.sem is Sem.GENDER and rec[1] is None:
                rec[1] = f.value.strip()[:1].casefold() or None
            for x in analysis.findings.get(f.address, ()):
                if x.entity is EntityType.PIN and rec[2] is None:
                    rec[2] = pin_prefix(f.value[x.start : x.end])
        counts: dict[tuple, int] = {}
        for v in qi.values():
            if v[2] is not None:
                counts[tuple(v)] = counts.get(tuple(v), 0) + 1
        return {r for r, v in qi.items() if v[2] is not None and counts[tuple(v)] < self.min_group_size}

    def _shift_days(self, record: str | None, doc_rel: str) -> int:
        # Linked record: the keyed PER-PATIENT shift (keyed on its pseudonym, itself keyed by the secret), so one
        # patient's dates move together across files. Unlinked record: an independent keyed PER-RECORD shift, so
        # uncertain identities never share a patient offset. No mapping is stored or written.
        key = self._shift_keys.get(record) or f"rec|{doc_rel}|{record or ''}"
        return self._psn.date_shift_days(key)

    def _phase4_value(self, f: Field, analysis: DocumentAnalysis, doc_rel: str) -> str | None:
        """Structured clinical date -> shifted; structured age -> 5-year band (Phase 4). ``None``: unchanged."""
        if f.channel is not Channel.CONTENT or f.kind not in (FieldKind.CELL, FieldKind.JSON_STRING):
            return None
        if not isinstance(f.value, str) or f.segments:
            return None
        sem = analysis.semantics.get(f.address)
        if sem is None or sem.sem not in (Sem.DATE, Sem.AGE, Sem.GENDER, Sem.DOB):
            # a field NAMED as a date ("date", "visit_date", "Sample Date") whose WHOLE value is one full date
            if _DATE_LABEL_RE.search(_field_name(f)) and _FULL_DATE_VALUE_RE.match(f.value):
                return shift_date_text(f.value, self._shift_days(f.record, doc_rel), self._date_order)
            return None
        if sem.sem is Sem.DATE:
            return shift_date_text(f.value, self._shift_days(f.record, doc_rel), self._date_order)
        if sem.sem in (Sem.AGE, Sem.GENDER):  # GENDER: combined "73/F" columns
            return band_age_text(f.value, self._age_band_years)
        return None

    def _is_free_text(self, f: Field, analysis: DocumentAnalysis) -> bool:
        if f.channel is not Channel.CONTENT or f.segments or not isinstance(f.value, str):
            return False
        if f.kind is FieldKind.TEXT:
            return True
        sem = analysis.semantics.get(f.address)
        return sem is not None and sem.sem is Sem.FREE_TEXT and f.kind in (FieldKind.CELL, FieldKind.JSON_STRING)

    def _shift_free_text(self, text: str, f: Field, analysis: DocumentAnalysis, doc_rel: str) -> str | None:
        """Free-text clinical dates (full dates only: ISO, numeric with 4-digit year, day-month-name-year) move by the
        record's offset; ambiguous day/month dates with no order evidence in the document are left as written."""
        if not self._is_free_text(f, analysis):
            return None
        return shift_date_text(text, self._shift_days(f.record, doc_rel), self._date_order)

    def _infer_date_order(self, doc: Document, analysis: DocumentAnalysis) -> str | None:
        """Document-level day/month order from unambiguous numeric dates (DATASET.md: one source is month-first)."""
        dmy = mdy = False
        for f in doc.fields:
            if f.channel is not Channel.CONTENT or not isinstance(f.value, str):
                continue
            sem = analysis.semantics.get(f.address)
            if not (self._is_free_text(f, analysis) or (sem is not None and sem.sem is Sem.DATE)):
                continue
            a, b = numeric_date_order_evidence(f.value)
            dmy, mdy = dmy or a, mdy or b
        if dmy and not mdy:
            return "dmy"
        if mdy and not dmy:
            return "mdy"
        return None

    def set_document_pseudonyms(self, psns: dict[str, str], multi_locs: frozenset[str] = frozenset()) -> None:
        """Bind resolved pseudonyms for the next ``sanitize`` call (keeps 3-arg signature intact)."""
        self._pending_psns = psns
        self._pending_multi = multi_locs

    def _reencode(self, text: str, seg: Base64Segment) -> str:
        raw = encode_text(text, seg.encoding)
        out = (base64.urlsafe_b64encode(raw) if seg.urlsafe else base64.b64encode(raw)).decode("ascii")
        return out if seg.padded else out.rstrip("=")

    def _new_value(
        self,
        f: Field,
        analysis: DocumentAnalysis,
        children: dict[str, Field],
        psn_target: tuple[int, str] | None = None,
        doc_rel: str = "",
    ) -> object:
        own = analysis.findings.get(f.address, [])
        if f.kind is FieldKind.JSON_NUMBER:
            # a PII number becomes 0 (type kept). A value that is ALREADY 0 is not transformed, so it is
            # neither replaced nor counted (F4): findings stay detections, counts stay applied changes
            if own and f.value != 0:
                self.stats.count(own)
                return 0
            # JSON numeric ages are NOT banded: a band string would change the value type (Phase 2 contract) and a
            # numeric lower bound would publish an untruthful exact age. Documented limitation.
            return None
        value: str = f.value
        if not own:
            p4 = self._phase4_value(f, analysis, doc_rel)
            if p4 is not None and p4 != value:
                self.stats.generalized_in(doc_rel, f.record)
                return p4
        if not f.segments:
            pin_ok = f.record not in self._pin_suppressed
            applied_pairs = effective(value, own, fhir_date=f.fhir is not None, psn_target=psn_target, pin_ok=pin_ok)
            if not applied_pairs:
                return self._shift_free_text(value, f, analysis, doc_rel)
            applied = [p[0] for p in applied_pairs]
            self.stats.count(applied)
            if any(x.action is Action.GENERALIZE for x in applied):
                self.stats.generalized_in(applied[0].document, f.record)
            spans = [
                (
                    x.start,
                    x.end,
                    _replacement(value, x, filename=False, fhir_date=f.fhir is not None, pseudonym=psn, pin_ok=pin_ok),
                )
                for x, psn in applied_pairs
            ]
            out = apply_spans(value, spans)
            return self._shift_free_text(out, f, analysis, doc_rel) or out
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
        outside_idx = [
            (idx, x) for idx, x in enumerate(own) if not any(x.start < s.end and s.start < x.end for s in f.segments)
        ]
        self.stats.count([x for _, x in outside_idx])
        for idx, x in outside_idx:
            psn = psn_target[1] if (psn_target is not None and idx == psn_target[0]) else None
            spans.append((x.start, x.end, psn if psn is not None else PLACEHOLDER[x.entity]))
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

    def sanitize(
        self,
        doc: Document,
        out_rel: str,
        analysis: DocumentAnalysis,
        record_pseudonyms: dict[str, str] | None = None,
    ) -> tuple[str, list[RecordRef]]:
        children = {f.address: f for f in doc.fields if f.kind is FieldKind.BASE64_TEXT}
        psn_map = record_pseudonyms if record_pseudonyms is not None else self._pending_psns
        multi_locs = self._pending_multi if record_pseudonyms is None else frozenset(psn_map)
        self._pending_psns = {}
        self._pending_multi = frozenset()
        # Select one schema-preserving in-record slot per linked record to receive PSN-XXXXXX
        psn_slots, placed_records = _select_pseudonym_slots(doc, analysis, psn_map, multi_locs)
        self._shift_keys = {loc: f"psn|{p}" for loc, p in psn_map.items()}
        self._pin_suppressed = self._rare_pin_records(doc, analysis)
        self._date_order = self._infer_date_order(doc, analysis)
        self.stats.suppressed += len(self._pin_suppressed)
        replacements: dict[str, object] = {}
        headers_seen: dict[str, int] = {}
        for f in doc.fields:
            if f.kind is FieldKind.FILENAME:
                # applied by sanitized_relpath (the rename happens before sanitize): count them here
                eff = effective(f.value, analysis.findings.get(f.address, []), filename=True)
                self.stats.count([p[0] for p in eff])
                continue
            if f.kind is FieldKind.BASE64_TEXT:
                continue
            new = self._new_value(f, analysis, children, psn_target=psn_slots.get(f.address), doc_rel=doc.source.rel)
            if f.kind is FieldKind.HEADER:
                name = new if new is not None else f.value
                n = headers_seen.get(name, 0) + 1
                headers_seen[name] = n
                if n > 1 and new is not None:
                    new = f"{name} #{n}"
            if new is not None and new != f.value:
                replacements[f.address] = new
            if f.segments and new is not None and new != f.value and _is_payload_member(f):
                # the payload was rewritten or withheld: its integrity metadata describes the ORIGINAL bytes
                # (Attachment.hash is a SHA-1 of them, usable to confirm a known photo or document;
                # Attachment.size is stale). Dropped, with or without a declared contentType (F2).
                parent = _parent(doc.native, f.path)
                for k in ("hash", "size"):
                    if isinstance(parent, dict) and k in parent:
                        replacements[pointer((*f.path[:-1], k))] = WITHHELD
        if doc.source.format is Format.FHIR:
            replacements.update(fhir_id_rewrites(doc, analysis))
        # Plain-text fallback: if a linked text document had no in-body PII span (e.g. linked via filename),
        # prepend a standard "Patient: PSN-XXXXXX" header line so pseudonym consistency still holds.
        if doc.source.format is Format.TEXT and "doc" in psn_map and "doc" not in placed_records:
            current = replacements.get("doc", doc.native)
            if isinstance(current, str):
                replacements["doc"] = f"Patient: {psn_map['doc']}\n{current}"
                placed_records.add("doc")
        rendered = render(doc, replacements)
        return rendered, self._records(doc, out_rel, psn_map, placed_records)

    def _records(
        self,
        doc: Document,
        out_rel: str,
        psn_map: dict[str, str],
        placed_records: set[str],
    ) -> list[RecordRef]:
        file = f"sanitized/{out_rel}"
        return [
            RecordRef(
                file=file,
                loc=loc,
                patient=psn_map[loc] if (loc in psn_map and loc in placed_records) else None,
            )
            for loc in doc.records
        ]


def _select_pseudonym_slots(
    doc: Document,
    analysis: DocumentAnalysis,
    psn_map: dict[str, str],
    multi_locs: frozenset[str] = frozenset(),
) -> tuple[dict[str, tuple[int, str]], set[str]]:
    """Pick one string field & finding span per linked record to receive the keyed pseudonym.

    Preserves exact CSV column counts, JSON key paths and value types, FHIR R4 structure,
    and text line counts by placing ``PSN-XXXXXX`` into an existing patient identifier or
    patient name slot instead of a generic ``[MRN]`` / ``[NAME]`` placeholder.
    """
    if not psn_map:
        return {}, set()
    by_rec: dict[str, list[Field]] = {}
    for f in doc.fields:
        if f.record not in psn_map:
            continue
        if f.kind not in (FieldKind.CELL, FieldKind.JSON_STRING, FieldKind.TEXT):
            continue
        if f.channel is not Channel.CONTENT:
            continue
        by_rec.setdefault(f.record, []).append(f)

    slots: dict[str, tuple[int, str]] = {}
    placed: set[str] = set()
    is_fhir = doc.source.format is Format.FHIR
    for loc, psn in psn_map.items():
        fields = by_rec.get(loc, [])
        if not fields:
            continue
        allow_direct = loc in multi_locs
        best: tuple[int, str, int] | None = None  # (priority_rank_lower_is_better, field_addr, finding_idx)
        for f in fields:
            findings = analysis.findings.get(f.address, ())
            if not findings:
                continue
            sem = analysis.semantics.get(f.address)
            sem_kind = sem.sem if sem is not None else Sem.UNKNOWN
            for idx, fd in enumerate(findings):
                if fd.detector == "fhir_id":
                    continue  # handled by coordinated fhir_id_rewrites
                # Skip spans inside a base64 segment
                if f.segments and any(fd.start < s.end and s.start < fd.end for s in f.segments):
                    continue
                rank = _slot_rank(f, fd, sem_kind, is_fhir=is_fhir, allow_direct=allow_direct)
                if rank is None:
                    continue
                if best is None or rank < best[0]:
                    best = (rank, f.address, idx)
                    if rank == 0:
                        break
            if best is not None and best[0] == 0:
                break
        if best is not None:
            slots[best[1]] = (best[2], psn)
            placed.add(loc)
    return slots, placed


def _slot_rank(f: Field, fd: Finding, sem_kind: Sem, *, is_fhir: bool, allow_direct: bool) -> int | None:
    """Lower rank is preferred for placing ``PSN-XXXXXX`` inside a record."""
    if is_fhir:
        if f.fhir is None:
            return None
        if f.fhir.resource_type in ("Practitioner", "PractitionerRole", "RelatedPerson", "Organization", "Location"):
            return None
        if f.fhir.resource_type == "Patient":
            if f.fhir.role == "identifier" and sem_kind is Sem.MRN:
                return 0
            if f.fhir.role == "identifier" and fd.entity in DIRECT:
                return 1
            if f.fhir.role == "name" and fd.entity is EntityType.PATIENT_NAME:
                return 2
            if allow_direct and fd.entity in DIRECT:
                return 3
            return None
        # Contained or nested Patient inside an Encounter / nested Bundle
        if fd.entity is EntityType.MRN:
            return 4
        if fd.entity is EntityType.PATIENT_NAME:
            return 5
        if allow_direct and fd.entity in DIRECT:
            return 6
        return None
    if fd.entity is EntityType.MRN and sem_kind is Sem.MRN:
        return 0
    if fd.entity is EntityType.MRN:
        return 1
    if fd.entity is EntityType.PATIENT_NAME and sem_kind is Sem.PERSON_NAME:
        return 2
    if fd.entity is EntityType.PATIENT_NAME:
        return 3
    if allow_direct and fd.entity in DIRECT:
        return 4
    return None


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


def _is_payload_member(f: Field) -> bool:
    """An object member that carries an attachment payload (``data``, ``payload``…, ``valueBase64Binary``)."""
    if not f.path or not isinstance(f.path[-1], str):
        return False
    key = f.path[-1].lower()
    return is_declared_data_key(key) or key.endswith("base64binary")


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
