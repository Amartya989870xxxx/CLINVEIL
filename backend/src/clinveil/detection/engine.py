"""Detection engine: IR fields -> semantics -> detectors -> propagation -> resolution -> Findings.

Per document:

1. **Field semantics**: CSV column headers, JSON key paths (with dynamic keys such as
   ``by_name: {"<name>": …}`` recognised as *values*), or FHIR element roles.
2. **Structured extraction**: a field whose semantics is PII (``patient_name``,
   ``Mobile``, ``Aadhaar No``, ``Address``…) yields findings over its value (names keep
   their ``S/o``/title prefix; addresses are split into components; DOB is whole).
3. **Free-text detection** for notes, remarks, narratives, decoded attachments and
   unknown fields: validated identifiers, contextual names, address components,
   DOB labels, names adjacent to phone numbers.
4. **Loose channels** (headers, keys, filenames, metadata): identifier-shaped tokens
   are values, not schema, and capitalised words adjacent to them are names.
5. **Propagation** from the run-wide :class:`SensitiveValueIndex` plus a document-local
   index of this document's own contextual names.
6. **Resolution** against clinical keep spans; typed, offset-only :class:`Finding` s.

Pass 1 (``seed``) runs steps 1-3 without an index and adds only FIELD_SEMANTICS,
LABEL and VALIDATED_PATTERN evidence at >= 0.88 confidence to the index.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from clinveil.detection import addresses, clinical, identifiers, names
from clinveil.detection.clinical import KeepSpan
from clinveil.detection.identifiers import Hit
from clinveil.detection.lexicon import NOT_NAME_WORDS, UP_DISTRICTS
from clinveil.detection.resolve import NAME_TYPES, resolve
from clinveil.detection.semantics import (
    _VOCAB as SCHEMA_WORDS,
)
from clinveil.detection.semantics import (
    FREE_TEXT,
    PRESERVED,
    STRUCTURED_PII,
    UNKNOWN,
    FieldSemantic,
    Sem,
    classify_label,
    classify_path,
    is_empty_value,
    label_tokens,
)
from clinveil.detection.text import DEVANAGARI_DIGITS, language_of, normalize_phrase, tokenize
from clinveil.detection.value_index import SensitiveValueIndex
from clinveil.models.channels import Channel
from clinveil.models.document import Document, Field, FieldKind, Format
from clinveil.models.findings import Action, EntityType, Evidence, Finding
from clinveil.parsing.json_format import pointer

E = EntityType
_SEM_ENTITY = {
    Sem.PERSON_NAME: E.PATIENT_NAME,
    Sem.RELATIVE_NAME: E.RELATIVE_NAME,
    Sem.PHONE: E.PHONE,
    Sem.EMAIL: E.EMAIL,
    Sem.AADHAAR: E.AADHAAR,
    Sem.ABHA_NUMBER: E.ABHA_NUMBER,
    Sem.ABHA_ADDRESS: E.ABHA_ADDRESS,
    Sem.PAN: E.PAN,
    Sem.MRN: E.MRN,
    Sem.INSURANCE_ID: E.INSURANCE_ID,
    Sem.HOUSE: E.HOUSE,
    Sem.LOCALITY: E.LOCALITY,
    Sem.LANDMARK: E.LANDMARK,
    Sem.VILLAGE: E.VILLAGE,
    Sem.PIN: E.PIN,
    Sem.DOB: E.DOB,
}
_EVIDENCE = {
    "field": Evidence.FIELD_SEMANTICS,
    "patient_label": Evidence.LABEL,
    "relative_label": Evidence.LABEL,
    "relation_marker": Evidence.LABEL,
    "mrn_label": Evidence.LABEL,
    "pin_label": Evidence.LABEL,
    "village_label": Evidence.LABEL,
    "dob_label": Evidence.LABEL,
    "phone": Evidence.VALIDATED_PATTERN,
    "aadhaar": Evidence.VALIDATED_PATTERN,
    "aadhaar_masked": Evidence.VALIDATED_PATTERN,
    "abha_number": Evidence.VALIDATED_PATTERN,
    "abha_address": Evidence.VALIDATED_PATTERN,
    "email": Evidence.VALIDATED_PATTERN,
    "pan": Evidence.VALIDATED_PATTERN,
    "insurance": Evidence.PATTERN,
    "mrn_shape": Evidence.PATTERN,
    "id_shape": Evidence.PATTERN,
    "gazetteer": Evidence.GAZETTEER,
    "gazetteer_weak": Evidence.GAZETTEER,
}
SEED_EVIDENCE = frozenset({Evidence.FIELD_SEMANTICS, Evidence.LABEL, Evidence.VALIDATED_PATTERN})
SEED_THRESHOLD = 0.88
_LOOSE = frozenset({Channel.HEADER, Channel.KEY, Channel.FILENAME, Channel.METADATA})
_PERSON_SHAPED_KEY = re.compile(
    r"(?:[A-Z][a-z]+|[A-Z]{2,})(?:[ _](?:[A-Z][a-z]+|[A-Z]{2,})){1,3}|"
    r"[\u0900-\u097f]+(?:\s[\u0900-\u097f]+){1,3}"
)
_RELATION_PREFIX = re.compile(
    r"(?i)^\s*(?:(?:[SDWFMC]\s?/\s?O|Mr|Mrs|Ms|Smt|Shri|Sri|Kumari|Late|"
    r"पुत्र|पुत्री|पत्नी|पति)\b\.?\s*:?\s*)+"
)
DOB_LABEL_RE = re.compile(
    r"(?i)(?:\bD\.?O\.?B\.?|\bDate\s+of\s+Birth|\bBirth\s*Date|जन्म\s*तिथि|\bJanm\s+Tithi)"
    r"\s*[:\-]?\s*(?P<d>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
)
NEAR_PHONE_RE = re.compile(
    r"(?P<n>(?:[A-Z][a-z]+|[A-Z]{2,})(?:[ ](?:[A-Z][a-z]+|[A-Z]{2,})){0,2})[ ]*(?:\([^)\n]{0,40}\)[ ]*)?,?[ ]*"
    r"(?P<kw>(?:mob(?:ile)?|ph(?:one)?|tel|contact|cell|call)\.?[ ]*[:\-]?[ ]*)?$"
)


def _is_fhir_date_dob(f: Field) -> bool:
    return f.fhir is not None and f.fhir.element.endswith("birthDate")


@dataclass
class DetectionStats:
    findings: Counter = field(default_factory=Counter)  # by entity
    detectors: Counter = field(default_factory=Counter)
    channels: Counter = field(default_factory=Counter)
    languages: Counter = field(default_factory=Counter)
    evidence: Counter = field(default_factory=Counter)
    protected: int = 0  # candidates dropped by clinical/doctor protection
    clinical_conflicts: int = 0
    files_with_pii: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings_total": sum(self.findings.values()),
            "by_entity": dict(sorted(self.findings.items())),
            "by_detector": dict(sorted(self.detectors.items())),
            "by_channel": dict(sorted(self.channels.items())),
            "by_language": dict(sorted(self.languages.items())),
            "by_evidence": dict(sorted(self.evidence.items())),
            "protected_by_clinical_rules": self.protected,
            "clinical_conflicts_overridden": self.clinical_conflicts,
            "files_with_pii": self.files_with_pii,
        }


@dataclass
class DocumentAnalysis:
    findings: dict[str, list[Finding]]  # field address -> resolved findings (offsets into that field's value)
    semantics: dict[str, FieldSemantic]

    def __repr__(self) -> str:
        return f"DocumentAnalysis(fields_with_findings={len(self.findings)})"


class DetectionEngine:
    def __init__(self, index: SensitiveValueIndex | None = None, stats: DetectionStats | None = None) -> None:
        self.index = index
        self.stats = stats or DetectionStats()

    # ------------------------------------------------------------------ public API
    def analyze(self, doc: Document, *, record_stats: bool = True) -> DocumentAnalysis:
        sems = self._semantics(doc)
        raw: dict[str, tuple[list[Hit], list[KeepSpan], str]] = {}
        for f in doc.fields:
            text = self._text_of(f)
            if text is None:
                continue
            hits, keeps = self._detect_field(doc, f, sems.get(f.address, UNKNOWN), text)
            raw[f.address] = (hits, keeps, text)
        self._doc_local_propagation(doc, raw, sems)
        out: dict[str, list[Finding]] = {}
        by_addr = {f.address: f for f in doc.fields}
        for addr, (hits, keeps, text) in raw.items():
            resolved, protected = resolve(hits, keeps, text)
            if record_stats:
                self.stats.protected += protected
            if not resolved:
                continue
            f = by_addr[addr]
            out[addr] = [self._finding(doc, f, r.hit, r.clinical_conflict) for r in resolved]
        if record_stats:
            self._record(out, raw)
        return DocumentAnalysis(out, sems)

    def seed(self, doc: Document, index: SensitiveValueIndex) -> None:
        """Pass 1: add high-confidence values of ``doc`` to ``index``."""
        analysis = self.analyze(doc, record_stats=False)
        by_addr = {f.address: f for f in doc.fields}
        for addr, findings in analysis.findings.items():
            text = self._text_of(by_addr[addr])
            for fd in findings:
                if fd.evidence in SEED_EVIDENCE and fd.confidence >= SEED_THRESHOLD and text is not None:
                    index.add(text[fd.start : fd.end], fd.entity)

    # ------------------------------------------------------------------ semantics
    def _semantics(self, doc: Document) -> dict[str, FieldSemantic]:
        sems: dict[str, FieldSemantic] = {}
        fmt = doc.source.format
        if fmt in (Format.CSV, Format.TSV):
            cols = {f.path[1]: classify_label(f.value) for f in doc.fields if f.kind is FieldKind.HEADER}
            for f in doc.fields:
                if f.kind is FieldKind.CELL:
                    sems[f.address] = cols.get(f.path[2], UNKNOWN)
        elif fmt in (Format.JSON, Format.FHIR):
            for f in doc.fields:
                if f.kind in (FieldKind.JSON_STRING, FieldKind.JSON_NUMBER):
                    sems[f.address] = self._fhir_semantic(doc, f) if fmt is Format.FHIR else self._json_semantic(f)
        return sems

    @staticmethod
    def _is_dynamic(key: str, parent_sem: FieldSemantic, parent_label: str = "") -> bool:
        """Is this JSON key a *value* (an ID, a name) rather than a schema label?"""
        if re.search(r"\d{4,}", key) or identifiers.ID_SHAPE_RE.search(key):
            return True
        raw_words = {w.casefold() for w in re.findall(r"[^\W\d_]+", key)}
        if _PERSON_SHAPED_KEY.fullmatch(key) and not raw_words & SCHEMA_WORDS:
            return True  # "Gumosh Lohal": a value, even if a token fuzzy-matches a schema word
        if classify_label(key).sem is not Sem.UNKNOWN:
            return False
        mapping = bool(set(label_tokens(parent_label)) & {"by", "index", "map", "lookup", "keyed", "dict"})
        return mapping and parent_sem.sem in STRUCTURED_PII

    def _json_semantic(self, f: Field) -> FieldSemantic:
        keys = [p for p in f.path if isinstance(p, str) and p != "#b64"]
        clean: list[str] = []
        for k in keys:
            parent = classify_path(tuple(clean)) if clean else UNKNOWN
            if self._is_dynamic(k, parent, clean[-1] if clean else ""):
                clean = []  # a value-key resets context: its value is not described by it
                continue
            clean.append(k)
        if not clean or (keys and clean[-1] != keys[-1]):
            return UNKNOWN
        sem = classify_path(tuple(clean))
        if sem.sem is Sem.UNKNOWN and any(k.startswith("_") for k in keys):
            return UNKNOWN
        return sem

    def _fhir_semantic(self, doc: Document, f: Field) -> FieldSemantic:
        ctx = f.fhir
        if ctx is None:
            return UNKNOWN
        el, role, rt = ctx.element, ctx.role, ctx.resource_type
        parent = _parent_obj(doc.native, f.path)
        key = f.path[-1] if f.path and isinstance(f.path[-1], str) else ""
        if role == "reference" or key in ("id", "fullUrl", "resourceType", "url", "status", "system", "use"):
            return FieldSemantic(Sem.NON_PII_ID, 1.0, "fhir_structural")
        if role == "narrative":
            return FREE_TEXT
        if role == "attachment":
            return FREE_TEXT
        if role == "date":
            return (
                FieldSemantic(Sem.DOB, 0.97, "fhir_birthdate")
                if el.endswith("birthDate")
                else FieldSemantic(Sem.DATE, 0.95, "fhir_date")
            )
        if key == "display" and isinstance(parent, dict):
            if "reference" in parent:
                target = _reference_target(doc, f.path[:-1])
                if target in ("Patient", "RelatedPerson", "Person"):
                    return FieldSemantic(
                        Sem.PERSON_NAME if target != "RelatedPerson" else Sem.RELATIVE_NAME,
                        0.95,
                        "fhir_subject_display",
                    )
                if target in ("Practitioner", "PractitionerRole"):
                    return FieldSemantic(Sem.DOCTOR_NAME, 0.95, "fhir_practitioner_display")
                return FieldSemantic(Sem.ORGANIZATION, 0.8, "fhir_display")
            return FieldSemantic(Sem.CLINICAL, 0.9, "fhir_coding_display")
        if rt in ("Practitioner", "PractitionerRole") and ".name" in el:
            return FieldSemantic(Sem.DOCTOR_NAME, 0.95, "fhir_practitioner")
        if rt in ("Organization", "Location", "HealthcareService") and ".name" in el:
            return FieldSemantic(Sem.ORGANIZATION, 0.95, "fhir_org")
        if role == "identifier" and key == "value":
            sysval = str(parent.get("system", "")) if isinstance(parent, dict) else ""
            if rt is None:
                return FieldSemantic(Sem.NON_PII_ID, 0.9, "fhir_bundle_identifier")
            if re.search(r"(?i)abdm|healthid|abha|ndhm", sysval):
                return FieldSemantic(Sem.ABHA_NUMBER, 0.95, "fhir_abha")
            if re.search(r"(?i)aadhaar|aadhar|uidai", sysval):
                return FieldSemantic(Sem.AADHAAR, 0.95, "fhir_aadhaar")
            return FieldSemantic(Sem.MRN, 0.95, "fhir_identifier")
        if role in ("name",) and rt in ("Patient", "Person"):
            if ".contact." in el:
                return FieldSemantic(Sem.RELATIVE_NAME, 0.95, "fhir_contact_name")
            return FieldSemantic(Sem.PERSON_NAME, 0.97, "fhir_patient_name")
        if role == "name" and rt == "RelatedPerson":
            return FieldSemantic(Sem.RELATIVE_NAME, 0.95, "fhir_related_person")
        if role == "contact":
            if el.endswith(".name.text") or ".name." in el:
                return FieldSemantic(Sem.RELATIVE_NAME, 0.95, "fhir_contact_name")
            if ".telecom." in el and key == "value":
                return FieldSemantic(Sem.PHONE, 0.95, "fhir_contact_telecom")
        if role == "telecom" and key == "value":
            is_mail = isinstance(parent, dict) and str(parent.get("system", "")).lower() == "email"
            return FieldSemantic(Sem.EMAIL if is_mail else Sem.PHONE, 0.97, "fhir_telecom")
        if role == "address":
            part = {
                "line": Sem.ADDRESS,
                "text": Sem.ADDRESS,
                "city": Sem.VILLAGE,
                "district": Sem.DISTRICT,
                "state": Sem.STATE,
                "postalCode": Sem.PIN,
                "country": Sem.STATE,
            }.get(key, Sem.ADDRESS)
            if isinstance(f.path[-1], int):  # address.line[i]
                part = Sem.ADDRESS
            return FieldSemantic(part, 0.95, f"fhir_address_{key or 'line'}")
        if key.startswith("value") and isinstance(parent, dict) and isinstance(parent.get("url"), str):
            url = parent["url"].lower()
            if "name" in url:
                rel = any(w in url for w in ("mother", "father", "spouse", "guardian", "husband", "wife", "relative"))
                return FieldSemantic(Sem.RELATIVE_NAME if rel else Sem.PERSON_NAME, 0.92, "fhir_name_extension")
        if role == "meta_source":
            return UNKNOWN
        return FieldSemantic(Sem.CLINICAL, 0.6, "fhir_other") if rt not in (None, "Patient") else UNKNOWN

    # ------------------------------------------------------------------ detection per field
    @staticmethod
    def _text_of(f: Field) -> str | None:
        if f.kind is FieldKind.JSON_NUMBER and not isinstance(f.value, bool):
            return str(f.value)
        return f.value if isinstance(f.value, str) else None

    def _detect_field(self, doc: Document, f: Field, sem: FieldSemantic, text: str) -> tuple[list[Hit], list[KeepSpan]]:
        if not text.strip():
            return [], []
        if f.kind is FieldKind.HEADER or f.kind is FieldKind.FILENAME or f.kind is FieldKind.JSON_KEY:
            return self._loose_field(doc, f, text), []
        channel = f.channel
        if sem.sem in PRESERVED and f.kind is not FieldKind.BASE64_TEXT:
            return [], []
        if f.segments:
            # the payload is analysed as its own BASE64_TEXT child; only the text around it here
            masked = list(text)
            for seg in f.segments:
                masked[seg.start : seg.end] = " " * (seg.end - seg.start)
            text = "".join(masked)
        if sem.sem in STRUCTURED_PII and f.kind is not FieldKind.BASE64_TEXT:
            structured = self._structured(text, sem)
            if structured is not None:
                hits = structured
                if self.index is not None:
                    hits = hits + self.index.match(text, channel)
                return hits, []
        return self._free_text(text, channel)

    def _structured(self, text: str, sem: FieldSemantic) -> list[Hit] | None:
        """Hits for a PII-typed field value, or None to fall back to free-text detection."""
        if is_empty_value(text):
            return []
        lead = len(text) - len(text.lstrip())
        end = len(text.rstrip())
        conf = max(0.9, min(0.97, sem.confidence + 0.05))
        s = sem.sem
        if s in (Sem.PERSON_NAME, Sem.RELATIVE_NAME):
            if not names.looks_like_person_name(text):
                return None
            m = _RELATION_PREFIX.match(text)
            start = m.end() if m else lead
            ent = E.PATIENT_NAME if s is Sem.PERSON_NAME else E.RELATIVE_NAME
            if m and s is Sem.PERSON_NAME and re.match(r"(?i)\s*[SDWFMC]\s?/\s?O", text):
                ent = E.RELATIVE_NAME  # "S/o X" under a person column names a relative
            return [Hit(start, end, ent, conf, "field")] if end > start else []
        if s is Sem.PHONE:
            if not re.search(r"\d", text) and names.looks_like_person_name(text):
                return [Hit(lead, end, E.RELATIVE_NAME, 0.85, "field")]
            found = [h for h in identifiers.find_identifiers(text) if h.entity is E.PHONE]
            if found:
                return found
            digits = sum(c.isdigit() for c in text.translate(DEVANAGARI_DIGITS))
            return [Hit(lead, end, E.PHONE, conf, "field")] if digits >= 7 else []
        if s is Sem.AADHAAR:
            masked = identifiers.AADHAAR_MASKED_RE.search(text)
            return [Hit(lead, end, E.AADHAAR_MASKED if masked else E.AADHAAR, conf, "field")]
        if s in (Sem.ADDRESS, Sem.LOCALITY) and ("," in text or "\n" in text or s is Sem.ADDRESS):
            hits = addresses.address_components(text, base_conf=0.9)
            nh, _ = names.detect_names(text)
            hits += [h for h in nh if h.detector in ("relation_marker", "relative_label", "patient_label", "title")]
            if not hits and not _is_place_only(text):
                hits = [Hit(lead, end, E.LOCALITY, 0.85, "field")]
            return hits
        if s in (Sem.VILLAGE, Sem.LOCALITY, Sem.HOUSE, Sem.LANDMARK) and _is_place_only(text):
            return []
        ent = _SEM_ENTITY.get(s)
        return [Hit(lead, end, ent, conf, "field")] if ent is not None and end > lead else None

    def _free_text(self, text: str, channel: Channel) -> tuple[list[Hit], list[KeepSpan]]:
        keeps = clinical.keep_spans(text)
        hits = list(identifiers.find_identifiers(text))
        name_hits, name_keeps = names.detect_names(text)
        hits += name_hits
        keeps += name_keeps
        hits += addresses.detect_addresses(text)
        for m in DOB_LABEL_RE.finditer(text):
            hits.append(Hit(m.start("d"), m.end("d"), E.DOB, 0.95, "dob_label"))
        hits += _names_near_phones(text, hits)
        if channel in _LOOSE:
            hits += _loose_hits(text, hits)
        if self.index is not None:
            hits += self.index.match(text, channel)
        return hits, keeps

    def _loose_field(self, doc: Document, f: Field, text: str) -> list[Hit]:
        if doc.source.format is Format.FHIR and f.kind is FieldKind.JSON_KEY:
            return []  # FHIR element names are schema, never values
        if f.kind is FieldKind.JSON_KEY:
            parent_keys = tuple(p for p in f.path[:-1] if isinstance(p, str))
            parent = classify_path(parent_keys) if parent_keys else UNKNOWN
            if self._is_dynamic(text, parent, parent_keys[-1] if parent_keys else "") and parent.sem in STRUCTURED_PII:
                structured = self._structured(text, parent)
                if structured:
                    return structured
        schema = (
            classify_label(text).sem is not Sem.UNKNOWN
            and not re.search(r"\d{3,}", text)
            and not (f.kind is FieldKind.JSON_KEY and self._is_dynamic(text, UNKNOWN))
        )
        if schema and f.kind in (FieldKind.JSON_KEY, FieldKind.HEADER):
            # an ordinary schema label: only exact multi-token / digit propagation can reveal a value in it
            return [
                h
                for h in (self.index.match(text, f.channel) if self.index is not None else [])
                if h.detector != "propagation_token"
            ]
        hits = [h for h in identifiers.find_identifiers(text)]
        hits += _loose_hits(text, hits)
        if self.index is not None:
            hits += self.index.match(text, f.channel)
        return hits

    # ------------------------------------------------------------------ propagation within a document
    def _doc_local_propagation(
        self, doc: Document, raw: dict[str, tuple[list[Hit], list[KeepSpan], str]], sems: dict[str, FieldSemantic]
    ) -> None:
        local = SensitiveValueIndex()
        for hits, _keeps, text in raw.values():
            for h in hits:
                if h.entity in NAME_TYPES and h.confidence >= 0.8 and h.detector not in ("gazetteer", "gazetteer_weak"):
                    local.add(text[h.start : h.end], h.entity)
        if not len(local):
            return
        by_addr = {f.address: f for f in doc.fields}
        for addr, (hits, _keeps, text) in raw.items():
            f = by_addr[addr]
            if sems.get(addr, UNKNOWN).sem in PRESERVED and f.kind is not FieldKind.BASE64_TEXT:
                continue
            if f.kind in (FieldKind.JSON_KEY, FieldKind.HEADER) and not hits:
                continue  # schema labels stay untouched
            for h in local.match(text, f.channel):
                hits.append(Hit(h.start, h.end, h.entity, min(h.confidence, 0.8), "propagation_local"))

    # ------------------------------------------------------------------ findings and statistics
    def _finding(self, doc: Document, f: Field, h: Hit, conflict: bool) -> Finding:
        action = Action.GENERALIZE if h.entity is E.DOB and _is_fhir_date_dob(f) else Action.REDACT
        evidence = _EVIDENCE.get(h.detector) or (
            Evidence.PROPAGATION
            if h.detector.startswith("propagation")
            else Evidence.ADDRESS_STRUCTURE
            if h.detector.startswith("address")
            else Evidence.CONTEXT
        )
        return Finding(
            entity=h.entity,
            start=h.start,
            end=h.end,
            confidence=round(h.confidence, 3),
            detector=h.detector,
            evidence=evidence,
            action=action,
            field=f.address,
            record=f.record,
            channel=f.channel,
            document=doc.source.sha256[:12],
            clinical_conflict=conflict,
        )

    def _record(self, out: dict[str, list[Finding]], raw: dict[str, tuple[list[Hit], list[KeepSpan], str]]) -> None:
        any_pii = False
        for addr, findings in out.items():
            text = raw[addr][2]
            for fd in findings:
                any_pii = True
                self.stats.findings[fd.entity.value] += 1
                self.stats.detectors[fd.detector] += 1
                self.stats.channels[fd.channel.value] += 1
                self.stats.evidence[fd.evidence.value] += 1
                window = text[max(0, fd.start - 60) : fd.end + 60]
                lang = "deva" if language_of(text[fd.start : fd.end]) == "deva" else language_of(window)
                self.stats.languages[lang] += 1
                self.stats.clinical_conflicts += fd.clinical_conflict
        self.stats.files_with_pii += any_pii


# --------------------------------------------------------------------------- helpers
def _parent_obj(root: Any, path: tuple[Any, ...]) -> Any:
    node = root
    for p in path[:-1]:
        try:
            node = node[p]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def _reference_target(doc: Document, obj_path: tuple[Any, ...]) -> str | None:
    if doc.fhir is None:
        return None
    ptr = pointer((*obj_path, "reference"))
    for r in doc.fhir.references:
        if r.pointer == ptr and r.target_entry is not None:
            for e in doc.fhir.entries:
                if e.index == r.target_entry:
                    return e.resource_type
    return None


def _is_place_only(text: str) -> bool:
    keys = normalize_phrase(text)
    return not keys or " ".join(keys) in UP_DISTRICTS


def _names_near_phones(text: str, hits: list[Hit]) -> list[Hit]:
    out = []
    for h in hits:
        if h.entity is not E.PHONE or h.confidence < 0.9:
            continue
        window_start = max(0, h.start - 60)
        m = NEAR_PHONE_RE.search(text[window_start : h.start])
        if not m:
            continue
        words = m.group("n").split()
        if any(w.casefold() in NOT_NAME_WORDS for w in words):
            continue
        if len(words) >= 2 or m.group("kw"):
            out.append(
                Hit(window_start + m.start("n"), window_start + m.end("n"), E.RELATIVE_NAME, 0.8, "phone_adjacent")
            )
    return out


_ID_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]{2,6}[-/]?\d{2,4}[-/]\d{4,8}|[A-Za-z]{2,6}\d{5,8}|"
    r"[A-Za-z]{2,6}-\d{5,8})(?![A-Za-z0-9])"
)


def _loose_hits(text: str, hits: list[Hit]) -> list[Hit]:
    """Headers/keys/filenames/metadata: ID-shaped tokens are values; adjacent capitalised words are names."""
    out: list[Hit] = []
    ids = [(m.start(), m.end()) for m in _ID_TOKEN_RE.finditer(text)]
    toks = tokenize(text)
    for i, t in enumerate(toks):
        if t.key.isdigit() and len(t.key) >= 6 and not re.fullmatch(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])?", t.key):
            near_name = any(
                abs(j - i) == 1 and toks[j].text[:1].isupper() and toks[j].key not in NOT_NAME_WORDS
                for j in range(max(0, i - 1), min(len(toks), i + 2))
                if j != i
            )
            if near_name:
                ids.append((t.start, t.end))
    for s, e in ids:
        out.append(Hit(s, e, E.MRN, 0.8, "loose_id"))
        # capitalised alphabetic tokens directly adjacent (up to 3 on each side)
        for direction in (-1, 1):
            idx = [k for k, t in enumerate(toks) if (t.end <= s if direction < 0 else t.start >= e)]
            if not idx:
                continue
            k = idx[-1] if direction < 0 else idx[0]
            taken = 0
            while 0 <= k < len(toks) and taken < 3:
                t = toks[k]
                gap = text[t.end : s] if direction < 0 and taken == 0 else None
                if not (
                    t.text.isalpha()
                    and t.text[:1].isupper()
                    and t.key not in NOT_NAME_WORDS
                    and t.key not in UP_DISTRICTS
                    and len(t.key) >= 3
                ):
                    break
                if gap is not None and len(gap) > 2:
                    break
                out.append(Hit(t.start, t.end, E.PATIENT_NAME, 0.75, "loose_adjacent_name"))
                taken += 1
                k += direction
    return out
