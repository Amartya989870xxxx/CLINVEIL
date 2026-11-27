"""Extract normalised :class:`RecordEvidence` per record from the Phase 1/2 IR.

Reuses the already-parsed :class:`Document` and Phase 2 :class:`DocumentAnalysis`
without re-parsing any file. Enforces strict role separation:
* doctor, staff, organisation, and clinical fields never enter patient identity evidence;
* relative names enter ``relative_names`` only, never ``patient_names``;
* masked Aadhaar and non-Verhoeff 12-digit numbers never enter ``aadhaar``;
* low-confidence / ``field_weak`` findings never become global identifiers;
* **ownership (Phase 3.1, R1/R2):** an identifier, phone or e-mail is the patient's only when
  nothing attributes it to someone else. A relative-labelled field (``Father Aadhaar``,
  ``पिता आधार``, ``Guardian Mobile``), a relative JSON container (``guardian: {aadhaar: …}``)
  or a kinship cue right before the value in text (``Husband's Aadhaar …``,
  ``Aadhaar of husband: …``, ``पति का आधार …``) makes it *relative-owned*: it never enters
  the patient's identity evidence, and person-unique ones (Aadhaar, ABHA, PAN) are kept
  apart in ``relative_global_ids`` as a veto. A relation marker (``W/o <Name>``) between the
  label and the value makes the owner *ambiguous*: the value is not used at all.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from typing import Any

from clinveil.detection import views
from clinveil.detection.engine import DocumentAnalysis
from clinveil.detection.semantics import RELATIVE as _RELATIVE_LABEL_WORDS
from clinveil.detection.semantics import Sem, label_tokens
from clinveil.detection.text import digits_only
from clinveil.linking.models import DateEvidence, NameEvidence, RecordEvidence, RecordKey
from clinveil.linking.normalize import (
    build_name_evidence,
    combine_name_parts,
    extract_ages,
    extract_genders,
    iter_free_ages,
    iter_free_genders,
    normalize_aadhaar,
    normalize_abha_address,
    normalize_abha_number,
    normalize_district,
    normalize_dob,
    normalize_email,
    normalize_hospital,
    normalize_insurance,
    normalize_mrn,
    normalize_pan,
    normalize_phone,
    normalize_village,
)
from clinveil.models.channels import Channel
from clinveil.models.document import Document, Field, FieldKind, Format
from clinveil.models.findings import EntityType, Finding

_E = EntityType
_FIRST_NAME_TOKS = frozenset({"first", "firstname", "given", "givenname", "forename"})
_MIDDLE_NAME_TOKS = frozenset({"middle"})
_LAST_NAME_TOKS = frozenset({"last", "lastname", "surname", "family"})
_RELATIVE_FIELD_SEMS = frozenset({Sem.RELATIVE_NAME})
_SKIP_IDENTITY_SEMS = frozenset({Sem.DOCTOR_NAME, Sem.STAFF, Sem.CLINICAL})
#: Label tokens that make a field (CSV header, JSON key or any JSON ancestor key) relative-owned.
_KIN_LABEL_WORDS = _RELATIVE_LABEL_WORDS | frozenset(
    "uncle aunt grandfather grandmother grandson granddaughter dada dadi nana nani bhai behen beta beti "
    "bahu sasur saas chacha mama abhibhavak sanrakshak rishtedar parijan household caregiver "
    "fatherhusband father_husband".split()
)
#: Tokens indicating a personal identifier when paired with a ``family`` container/header (never ``Family Name``).
_FAMILY_ID_TOKS = frozenset(
    {
        "aadhaar",
        "aadhar",
        "abha",
        "pan",
        "phone",
        "mobile",
        "contact",
        "email",
        "id",
        "card",
        "policy",
        "insurance",
        "uid",
    }
)
_KIN_WORD_PAT = (
    r"(?:father|mother|husband|wife|spouse|guardian|parents?|son|daughter|brother|sister|"
    r"relatives?|attendant|caretaker|caregiver|escort|informant|uncle|aunt|grand(?:father|mother|son|daughter)|"
    r"nok|next\s+of\s+kin|emergency\s+contact|contact\s+person|"
    r"pita|pati|patni|mata|beta|beti|bhai|behen|bahu|sasur|saas|chacha|mama|dada|dadi|nana|nani|"
    r"abhibhavak|sanrakshak|rishtedar|parijan)"
)
_DEVA_KIN_WORD_PAT = (
    r"(?:पिता|पति|पत्नी|माता|माँ|मां|पुत्र|पुत्री|बेटा|बेटी|अभिभावक|संरक्षक|भाई|बहन|परिचारक|रिश्तेदार|परिजन|"
    r"चाचा|मामा|दादा|दादी|नाना|नानी)"
)
#: Kinship cue directly qualifying a value in text, including compound relational phrases such as
#: "Father of patient", "Husband of the patient", "Patient's husband", and "मरीज़ के पति" (NEW-2).
_KIN_CUE_RE = re.compile(
    r"(?i)(?<![\w])(?:"
    r"(?:patient(?:'s|’s)?|pt\.?(?:'s|’s)?)\s+" + _KIN_WORD_PAT + r"(?:'s|’s)?|"
    r"(?:patient|pt\.?)\s+(?:ka|ke|ki)\s+"
    + _KIN_WORD_PAT
    + r"(?:'s|’s)?|"
    + _KIN_WORD_PAT
    + r"(?:'s|’s)?(?:\s+(?:of|for|to|with)\s+(?:the\s+)?(?:patient|pt\.?)(?:'s|’s)?)?"
    r")(?![\w])|"
    r"(?:(?:मरीज़|मरीज|रोगी)\s*(?:का|के|की)\s*)?" + _DEVA_KIN_WORD_PAT
)
#: Explicit patient-ownership cue that resets an earlier relative mention ("Patient Aadhaar:", "मरीज़:").
_PATIENT_OWNER_CUE_RE = re.compile(
    r"(?i)(?<![\w])(?:patient(?:'s|’s)?|pt(?:'s|’s)?|self|own)(?![\w])|मरीज़|मरीज|रोगी|स्वयं"
)
#: Non-relative clinical/demographic line headers that end a preceding single-line relative block.
_LINE_RESET_CUE_RE = re.compile(
    r"(?i)(?:^|\n)[ \t]*(?:age|sex|gender|dob|d\.o\.b\.|uhid|mrn|address|village|ward|bed|diagnosis|c/o|complaints?|"
    r"आयु|उम्र|लिंग|पता)\b"
)
#: A relation marker between the label and the value ("Sunila W/o Arvel Aadhaar …"): owner unknown.
_REL_MARKER_RE = re.compile(r"(?i)(?<![\w/])(?:[SDW]\s?/\s?O|son\s+of|daughter\s+of|wife\s+of|husband\s+of)(?![\w])")
#: Titles, honorifics, and common abbreviations whose trailing period does NOT end a sentence (NEW-2).
_NON_SENTENCE_ABBREVS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "smt",
        "sh",
        "shri",
        "shree",
        "sri",
        "srimati",
        "shrimati",
        "km",
        "kumari",
        "kr",
        "pt",
        "late",
        "col",
        "maj",
        "capt",
        "lt",
        "gen",
        "brig",
        "rev",
        "fr",
        "sr",
        "jr",
        "st",
        "md",
        "mohd",
        "sk",
        "no",
        "nos",
        "vill",
        "vpo",
        "po",
        "ps",
        "tehsil",
        "dist",
        "distt",
        "dept",
        "hosp",
        "reg",
        "opd",
        "ipd",
        "uhid",
        "mrn",
        "ph",
        "mob",
        "tel",
        "ext",
        "approx",
        "vs",
        "etc",
        "eg",
        "ie",
        "श्री",
        "श्रीमती",
        "सुश्री",
        "कुमारी",
        "कु",
        "स्व",
        "डॉ",
        "वैद्य",
        "पं",
        "मो",
        "ग्रा",
        "पो",
        "जि",
    }
)
_INLINE_TAG_RE = re.compile(r"(?i)^</?(?:span|b|i|u|a|em|strong|sub|sup|font|small|big|code)\b")
#: Tags that join a label to its value inside one table row / definition-list entry
#: (``</td><td>``, ``</th><td>``, ``</dt><dd>``): rendered like the space after "Father:" (P33-PASS3-F1).
_CELL_JOIN_TAG_RE = re.compile(r"(?i)^<(?:/(?:td|th|dt)|td|th|dd)\b")
#: Tags that open a new section: a genuine hard clause boundary between unrelated statements.
_SECTION_TAG_RE = re.compile(r"(?i)^<(?:h[1-6]|hr|section|article)\b")
_PRE_DOT_WORD_RE = re.compile(r"([A-Za-z\u0900-\u097f]+)$")
_HARD_SEGMENT_RE = re.compile(r"[;\n|,।]")
_HARD_CLAUSE_RE = re.compile(r"[;।]|\n[ \t]*\n")
_OWNED_ENTITIES = frozenset(
    {
        EntityType.AADHAAR,
        EntityType.ABHA_NUMBER,
        EntityType.ABHA_ADDRESS,
        EntityType.PAN,
        EntityType.INSURANCE_ID,
        EntityType.EMAIL,
        EntityType.PHONE,
        EntityType.MRN,
    }
)
_HOSPITAL_HEADER_RE = re.compile(
    r"(?i)^[^\n]{2,80}(?:hospital|multispeciality|multi-speciality|charitable|sadan|clinic|medical\s+cent|health\s+cent|"
    r"pathology|diagnostics?|laboratory|अस्पताल|चिकित्सालय|सदन)"
)


def extract_document_evidence(doc: Document, analysis: DocumentAnalysis) -> list[RecordEvidence]:
    """Extract one :class:`RecordEvidence` per record in ``doc``."""
    if not doc.records:
        return []
    hospital, is_external_lab, reliable = _infer_document_hospital(doc, analysis)
    single_doc = doc.records == ["doc"]

    if doc.source.format is Format.FHIR:
        ev = _extract_fhir_document(doc, analysis, hospital, is_external_lab)
        ev.hospital_reliable = reliable
        return [ev]

    # Group fields by record locator
    by_rec: dict[str, list[Field]] = defaultdict(list)
    for f in doc.fields:
        if f.kind is FieldKind.HEADER or f.kind is FieldKind.JSON_KEY:
            continue
        if f.record in ("@file", "@filename", "@header"):
            if single_doc:
                by_rec["doc"].append(f)
            continue
        by_rec[f.record].append(f)

    # Each record starts from the DOCUMENT-level scope (FHIR / top-level facility metadata,
    # letterhead, or file path) with its reliability, and only an explicit facility value inside
    # that record overrides it (PASS1-NEW-7). Another record's facility is never inherited.
    return [
        _extract_record(doc, loc, by_rec.get(loc, []), analysis, hospital, is_external_lab, reliable)
        for loc in doc.records
    ]


_FACILITY_LABELS = frozenset(
    {
        "facility",
        "hospital",
        "lab",
        "laboratory",
        "hospital_name",
        "facility_name",
        "clinic",
        "clinic_name",
        "institution",
        "institution_name",
        "provider",
        "provider_name",
        "pathology",
    }
)
_STD_FHIR_DOMAINS = ("hl7.org", "loinc.org", "snomed.info", "abdm", "healthid", "abha", "ndhm", "aadhaar", "uidai")


def _norm_label(label: str | None) -> str:
    return re.sub(r"[\s\-]+", "_", (label or "").strip().lower())


#: Leaf keys under a facility object that carry its name (``facility.name``, ``hospital.title``, NEW-5).
_FACILITY_LEAF_LABELS = frozenset({"name", "title", "value", "display", "text", "label"})
#: Enclosing keys under which a facility is NOT the record's issuer (referral source, payer, ...).
_FACILITY_EXCLUDE_TOKS = frozenset(
    {
        "referral",
        "referred",
        "referring",
        "previous",
        "prior",
        "transfer",
        "transferred",
        "destination",
        "ordering",
        "insurer",
        "insurance",
        "payer",
        "tpa",
        "pharmacy",
        "aggregator",
    }
)
#: Data aggregators / exchanges / vendors are never a hospital issuer, whatever key holds them (NEW-5).
_AGGREGATOR_RE = re.compile(
    r"(?i)\b(?:aggregator|exchange|platform|integration|interoperability|gateway|middleware|"
    r"data\s+services?|clearing\s*house|software|vendor|hie)\b"
)


def _facility_label(f: Field) -> str | None:
    """The normalised facility key when ``f`` names a record's issuing facility, using the full
    JSON path: ``facility``/``hospital_name`` labels, or ``facility.name`` / ``hospital.title``
    style nested leaves. Facilities under referral / transfer / payer containers are ignored, and
    so are facilities owned by a relative (``guardian.facility``, ``emergency_contact.hospital``,
    ``father.facility.name``, a ``Guardian Hospital`` column, P33-F3): a relative's hospital is never
    the patient's issuing hospital and must not set or override the record's hospital scope."""
    if f.kind is FieldKind.HEADER or f.kind is FieldKind.JSON_KEY:
        return None
    lbl = _norm_label(f.label)
    if f.channel is Channel.METADATA and "path" in lbl:
        return None
    all_keys = [f.label] if f.label else []
    all_keys += [p for p in f.path if isinstance(p, str)]
    if _keys_relative_owned(all_keys):
        return None
    keys = [p for p in f.path if isinstance(p, str)]
    if keys and _norm_label(keys[-1]) == lbl:
        keys = keys[:-1]
    if any(set(label_tokens(k)) & _FACILITY_EXCLUDE_TOKS for k in keys):
        return None
    if lbl in _FACILITY_LABELS:
        return lbl
    if lbl in _FACILITY_LEAF_LABELS and len(f.path) >= 2 and isinstance(f.path[-2], str):
        parent = _norm_label(f.path[-2])
        if parent in _FACILITY_LABELS:
            return parent
    return None


def _facility_from_value(label: str, value: object) -> tuple[str | None, bool] | None:
    """``(slug, is_lab)`` for an explicit facility value, or None when it names no issuer.

    A ``provider`` key must hold a recognisable hospital or lab (a provider may be a data
    aggregator or a vendor), and an aggregator / exchange / vendor value is never an issuer."""
    if not isinstance(value, str) or not value.strip():
        return None
    if _AGGREGATOR_RE.search(value):
        return None
    slug, lab = normalize_hospital(value)
    if not slug and not lab:
        return None
    if label.startswith("provider") and not lab and not _HOSPITAL_WORD_RE.search(value):
        return None
    return slug, lab


def _resolve_facilities(found: list[tuple[str | None, bool]]) -> tuple[str | None, bool, bool] | None:
    """Combine explicit facility values: one hospital -> it (reliable); several different hospitals
    -> ambiguous ``(None, False, False)``; labs only -> the lab. None when nothing was found."""
    hosp = {slug for slug, lab in found if slug and not lab}
    if len(hosp) == 1:
        return next(iter(hosp)), False, True
    if len(hosp) > 1:
        return None, False, False
    labs = {slug for slug, lab in found if lab and slug}
    if any(lab for _, lab in found):
        only = next(iter(labs)) if len(labs) == 1 else None
        return only, True, only is not None
    return None


# --------------------------------------------------------------------------- ownership attribution
def field_is_relative_owned(f: Field, sem_kind: Sem) -> bool:
    """A field whose value belongs to a relative: relative semantics, a kinship word, or an
    explicit relative-contact container (``emergency_contact``, ``contact_person``, ``family`` ID)
    in its label or enclosing JSON key path (Phase 3.1/3.2, R1/R2/F4).

    Never matches patient surname labels such as ``Family Name`` or ``name.family``, nor ER
    clinical/MRN fields such as ``Emergency Admission No``.
    """
    if sem_kind is Sem.RELATIVE_NAME:
        return True
    keys = [f.label] if f.label else []
    keys += [p for p in f.path if isinstance(p, str)]
    return _keys_relative_owned(keys)


def _keys_relative_owned(keys: list[str]) -> bool:
    """A label / JSON key path that places a value inside a relative-owned container (kinship word,
    ``emergency_contact``, ``contact_person``, or a ``family`` identifier container)."""
    tok_sets = [set(label_tokens(k)) for k in keys if k]
    if any(kt & _KIN_LABEL_WORDS for kt in tok_sets):
        return True
    for kt in tok_sets:
        if "emergency" in kt and "contact" in kt:
            return True
        if "contact" in kt and "person" in kt:
            return True
    all_toks = set().union(*tok_sets) if tok_sets else set()
    return bool(any("family" in kt and not (kt & {"name", "naam"}) for kt in tok_sets) and (all_toks & _FAMILY_ID_TOKS))


def _is_sentence_period(text: str, dot_idx: int) -> bool:
    """True when ``text[dot_idx] == '.'`` is a real sentence terminator, not a title or initial (NEW-2)."""
    if dot_idx + 1 >= len(text) or not re.match(r"\s+[A-Z\u0900-\u097f]", text[dot_idx + 1 :]):
        return False
    if dot_idx >= 2 and text[dot_idx - 2] == ".":
        return False
    m = _PRE_DOT_WORD_RE.search(text[max(0, dot_idx - 16) : dot_idx])
    if not m:
        return True
    word = m.group(1)
    if len(word) == 1 and word.isalpha():
        return False
    return word.casefold() not in _NON_SENTENCE_ABBREVS and word not in _NON_SENTENCE_ABBREVS


def _last_boundary_cut(window: str, *, include_comma_newline: bool) -> int:
    hard_re = _HARD_SEGMENT_RE if include_comma_newline else _HARD_CLAUSE_RE
    cut = max((m.end() for m in hard_re.finditer(window)), default=0)
    for i, ch in enumerate(window):
        if ch == "." and i + 1 > cut and _is_sentence_period(window, i):
            cut = i + 1
    return cut


def _non_kin_patient_cues(slice_text: str, kin_spans: list[tuple[int, int]]) -> list[re.Match[str]]:
    """Patient-owner cue matches that are NOT part of a compound kinship phrase ('Father of patient', NEW-2)."""
    return [
        m
        for m in _PATIENT_OWNER_CUE_RE.finditer(slice_text)
        if not any(not (m.end() <= ks or m.start() >= ke) for ks, ke in kin_spans)
    ]


def context_owner(text: str, start: int) -> str:
    """Owner of a value at ``text[start:]`` from the words that qualify it: ``patient``,
    ``relative`` (kinship cue in its segment/clause) or ``ambiguous`` (relation marker or
    immediately preceding single-line relative header with no patient reset, F4/NEW-2)."""
    # 1. Immediate segment (up to 100 chars after last comma/newline/semicolon/sentence boundary)
    window = text[max(0, start - 100) : start]
    seg = window[_last_boundary_cut(window, include_comma_newline=True) :]
    seg_kin = list(_KIN_CUE_RE.finditer(seg))
    seg_kin_spans = [(m.start(), m.end()) for m in seg_kin]
    last_pat = max((m.end() for m in _non_kin_patient_cues(seg, seg_kin_spans)), default=-1)
    last_kin = max((m.end() for m in seg_kin), default=-1)
    last_rel = max((m.end() for m in _REL_MARKER_RE.finditer(seg)), default=-1)
    if last_pat >= 0 and last_pat > last_kin and last_pat > last_rel:
        return "patient"
    if last_kin >= 0:
        return "relative"
    if last_rel >= 0:
        return "ambiguous"

    # 2. Broader clause (up to 120 chars; crosses commas and single newlines unless reset by a
    #    patient/demographic cue, so "Husband: Name, Aadhaar ..." and "Father: Name\nAadhaar: ..."
    #    never silently become patient-owned, F4/NEW-2).
    cwin = text[max(0, start - 120) : start]
    clause = cwin[_last_boundary_cut(cwin, include_comma_newline=False) :]
    clause_kin = list(_KIN_CUE_RE.finditer(clause))
    clause_kin_spans = [(m.start(), m.end()) for m in clause_kin]
    reset_pos = max(
        max((m.end() for m in _non_kin_patient_cues(clause, clause_kin_spans)), default=0),
        max((m.end() for m in _LINE_RESET_CUE_RE.finditer(clause)), default=0),
    )
    tail = clause[reset_pos:]
    kin_matches = list(_KIN_CUE_RE.finditer(tail))
    if kin_matches:
        between = tail[kin_matches[-1].end() :]
        if "\n" not in between:
            return "relative"
        if between.count("\n") == 1:
            return "ambiguous"
    return "patient"


def _build_owner_view(text: str) -> tuple[str, tuple[int, ...] | None]:
    """Build a decoded ownership view for HTML-entity, ``\\uXXXX``, ``%XX``, or XHTML text (NEW-2).

    Each run of consecutive tags (with the insignificant whitespace around them) becomes ONE
    separator, so XHTML structure reads like the equivalent plain text (P33-PASS3-F1):

    * inline markup only (``<span>``, ``<b>``) or a label/value cell join inside one table row or
      definition-list entry (``</td><td>``, ``</dt><dd>``): a space, as in ``Father: <name>, 42 yrs``;
    * a new section (``<h2>``, ``<hr>``, ``<section>``): a hard clause boundary (``\\n\\n``);
    * any other block boundary (``</p><p>``, ``</tr><tr>``, ``<br>``, ``</dd><dt>``): a single line
      break, so a value on the line after "Father: <name>" stays ``ambiguous`` exactly as in plain text.

    Previously every tag became its own newline, so ``</td><td>`` produced ``\\n\\n``, a hard clause
    boundary that cut the relative label off from the relative's age and Aadhaar.
    """
    view = views.decoded_view(text)
    if view is None:
        return text, None
    chars = list(view.text)
    n = len(chars)
    i = 0
    while i < n:
        if not view.tag[i]:
            i += 1
            continue
        start = i
        while start > 0 and not view.tag[start - 1] and chars[start - 1].isspace():
            start -= 1
        end = i
        sep = " "
        while end < n and (view.tag[end] or chars[end].isspace()):
            if view.tag[end]:
                raw_tag = text[view.starts[end] : view.ends[end]]
                if _SECTION_TAG_RE.match(raw_tag):
                    sep = "\n\n"
                elif sep == " " and not (_INLINE_TAG_RE.match(raw_tag) or _CELL_JOIN_TAG_RE.match(raw_tag)):
                    sep = "\n"
            end += 1
        # ``start .. end`` covers at least one character; a one-character run cannot hold "\n\n",
        # so a hard boundary falls back to ";" (also a hard clause boundary).
        if sep == "\n\n" and end - start < 2:
            sep = ";"
        for k in range(start, end):
            chars[k] = " "
        for k, ch in enumerate(sep):
            chars[start + k] = ch
        i = end
    return "".join(chars), view.starts


def _patient_owned_demographics(text: str) -> tuple[set[int], set[str]]:
    """Ages and genders mentioned in free text whose context owner is the PATIENT (P33-F2).

    Uses the same ownership attribution as identifiers (:func:`context_owner` on the decoded view of
    HTML / XHTML narratives, entities and escapes): "grandfather Bram Venn (72 yrs)", "father, 61/M"
    or "पिता: …, आयु 80" belong to a relative, and an ambiguous owner is dropped. Patient-owned values
    in the same note ("Patient: …, 7 yrs") are kept."""
    view, _starts = _build_owner_view(text)
    ages = {v for pos, v in iter_free_ages(view) if context_owner(view, pos) == "patient"}
    genders = {g for pos, g in iter_free_genders(view) if context_owner(view, pos) == "patient"}
    return ages, genders


def _finding_owner(owner_text: str, starts_map: tuple[int, ...] | None, raw_start: int) -> str:
    if starts_map is None:
        return context_owner(owner_text, raw_start)
    v_idx = bisect_left(starts_map, raw_start)
    return context_owner(owner_text, min(v_idx, len(owner_text)))


# --------------------------------------------------------------------------- hospital inference
#: A file-name stem names a hospital reliably only if it says so ("apex_hospital.csv").
_HOSPITAL_WORD_RE = re.compile(
    r"(?i)(?:hospital|hosp\b|clinic|sadan|multi-?special|chikitsalay|medical\s*college|health\s*cent|"
    r"\bphc\b|\bchc\b|aiims|dispensary|infirmary|अस्पताल|चिकित्सालय)"
)


def _infer_document_hospital(doc: Document, analysis: DocumentAnalysis) -> tuple[str | None, bool, bool]:
    """Infer the issuing hospital scope: ``(slug, is_external_lab, reliable)``.

    ``reliable`` (Phase 3.1, R5) is True for a FHIR identifier system / Organization, a facility
    field, a letterhead, or a file name that itself contains a hospital-type word. A slug guessed
    from any other file-name stem (``master``, ``nursing_adm900001``) still namespaces MRNs, but
    is NOT trusted to prove that two records come from two different hospitals.
    """
    slug, lab, reliable = _infer_document_hospital_inner(doc, analysis)
    return slug, lab, reliable


def _infer_document_hospital_inner(doc: Document, analysis: DocumentAnalysis) -> tuple[str | None, bool, bool]:
    is_lab = False
    # 1. FHIR: Patient.identifier.system (exact element, skipping standard code systems) or Organization.name
    if doc.source.format is Format.FHIR:
        for f in doc.fields:
            if f.fhir is None or not isinstance(f.value, str):
                continue
            if f.fhir.element == "Patient.identifier.system":
                low = f.value.lower()
                if not any(w in low for w in _STD_FHIR_DOMAINS):
                    slug, lab = normalize_hospital(f.value)
                    if slug:
                        return slug, lab, True
            if f.fhir.resource_type == "Organization" and f.fhir.element == "Organization.name":
                slug, lab = normalize_hospital(f.value)
                if slug:
                    return slug, lab, True

    # 2. Document-level structured facility metadata ONLY (never clinical test names or package codes):
    #    a single-record document's fields, or a multi-record document's top-level (``@file``) fields,
    #    including nested ``facility.name`` objects (NEW-5). Per-record facility values never become a
    #    document default: each record resolves its own (F5 / PASS1-NEW-7). Several different
    #    hospitals in the metadata make the document scope ambiguous (never reliable).
    lab_slug: str | None = None
    single_doc = doc.records == ["doc"]
    found: list[tuple[str | None, bool]] = []
    for f in doc.fields:
        if not single_doc and f.record not in ("@file", "@filename", "@header"):
            continue
        lbl = _facility_label(f)
        if lbl is None:
            continue
        val = _facility_from_value(lbl, f.value)
        if val is not None:
            found.append(val)
    meta = _resolve_facilities(found)
    meta_ambiguous = False
    if meta is not None:
        m_slug, m_lab, _m_rel = meta
        if m_slug and not m_lab:
            return m_slug, False, True
        if m_lab:
            is_lab = True
            lab_slug = m_slug
        else:
            meta_ambiguous = True

    # 3. Text document letterhead (first 3 non-empty lines)
    if doc.source.format is Format.TEXT and isinstance(doc.native, str) and not meta_ambiguous:
        lines = [ln.strip() for ln in doc.native.splitlines() if ln.strip()][:3]
        for ln in lines:
            if _HOSPITAL_HEADER_RE.search(ln):
                slug, lab = normalize_hospital(ln)
                if slug:
                    return slug, lab or is_lab, True

    # 4. Path/filename stem and parent directories (e.g. "registration/sanjeevani_registration.csv",
    #    "halcyon_hospital/ward_register.csv", "dir_alpha/ward_register.csv", NEW-3).
    parts = doc.source.rel.split("/")
    if any(p.lower() in ("lab", "labs", "pathology") for p in parts[:-1]):
        is_lab = True
    stem = parts[-1].rsplit(".", 1)[0]
    slug, stem_lab = normalize_hospital(stem)
    if stem_lab:
        is_lab = True
    stem_reliable = bool(_HOSPITAL_WORD_RE.search(stem)) and not meta_ambiguous

    dir_slug: str | None = None
    dir_reliable = False
    for seg in reversed(parts[:-1]):
        d_slug, d_lab = normalize_hospital(seg)
        if d_lab:
            is_lab = True
        if d_slug and not d_lab:
            dir_slug = d_slug
            dir_reliable = bool(_HOSPITAL_WORD_RE.search(seg)) and not meta_ambiguous
            break

    if slug and not is_lab:
        if stem_reliable:
            return slug, False, True
        if dir_slug and dir_reliable:
            return dir_slug, False, True
        if dir_slug and dir_slug != slug:
            return f"{dir_slug}_{slug}", False, False
        return slug, False, False
    if dir_slug and not is_lab:
        return dir_slug, False, dir_reliable
    return (lab_slug or (slug if is_lab else None)), is_lab, bool(lab_slug) or stem_reliable


# --------------------------------------------------------------------------- standard record extraction
def _extract_record(
    doc: Document,
    loc: str,
    fields: list[Field],
    analysis: DocumentAnalysis,
    hospital: str | None,
    is_external_lab: bool,
    doc_reliable: bool = False,
) -> RecordEvidence:
    aadhaar: set[str] = set()
    abha_num: set[str] = set()
    abha_addr: set[str] = set()
    pan: set[str] = set()
    insurance: set[str] = set()
    email: set[str] = set()
    local_ids: set[tuple[str, str]] = set()
    local_cores: set[tuple[str, str]] = set()
    raw_mrns: set[tuple[str, bool]] = set()
    patient_names: list[NameEvidence] = []
    relative_names: list[NameEvidence] = []
    phones: set[str] = set()
    dobs: set[DateEvidence] = set()
    birth_years: set[int] = set()
    ages: set[int] = set()
    genders: set[str] = set()
    villages: set[str] = set()
    districts: set[str] = set()
    pins: set[str] = set()
    relative_ids: set[str] = set()

    # Start from the document-level scope and its reliability; only an explicit facility value in
    # THIS record overrides it (F5 / NEW-5 / PASS1-NEW-7). A blank or missing facility cell keeps
    # the document metadata (file path, top-level facility) and never inherits another row's value;
    # conflicting explicit facilities in one record leave it unscoped.
    rec_hospital = hospital
    rec_is_lab = is_external_lab
    rec_reliable = doc_reliable and hospital is not None
    if loc != "doc":
        own: list[tuple[str | None, bool]] = []
        for f in fields:
            lbl = _facility_label(f)
            if lbl is not None:
                val = _facility_from_value(lbl, f.value)
                if val is not None:
                    own.append(val)
        resolved = _resolve_facilities(own)
        if resolved is not None:
            rec_hospital, rec_is_lab, rec_reliable = resolved

    # Collect split name parts within this record (FirstName / MiddleName / LastName), keeping
    # relative-owned containers (e.g. emergency_contact.first_name) strictly separate (NEW-1).
    split_first: list[str] = []
    split_middle: list[str] = []
    split_last: list[str] = []
    rel_split_first: list[str] = []
    rel_split_middle: list[str] = []
    rel_split_last: list[str] = []

    for f in fields:
        sem = analysis.semantics.get(f.address)
        sem_kind = sem.sem if sem is not None else Sem.UNKNOWN
        if sem_kind in _SKIP_IDENTITY_SEMS:
            continue
        text = _field_text(f)
        if text is None or not text.strip():
            continue
        is_rel_field = sem_kind in _RELATIVE_FIELD_SEMS or field_is_relative_owned(f, sem_kind)

        # Track split patient vs relative name columns / keys (NEW-1)
        if sem_kind is Sem.PERSON_NAME and f.label and f.channel is Channel.CONTENT:
            lt = set(label_tokens(f.label))
            target_first = rel_split_first if is_rel_field else split_first
            target_middle = rel_split_middle if is_rel_field else split_middle
            target_last = rel_split_last if is_rel_field else split_last
            if lt & _FIRST_NAME_TOKS and not (lt & _LAST_NAME_TOKS):
                target_first.append(text.strip())
            elif lt & _MIDDLE_NAME_TOKS:
                target_middle.append(text.strip())
            elif lt & _LAST_NAME_TOKS and not (lt & _FIRST_NAME_TOKS):
                target_last.append(text.strip())

        # Extract quasi-identifiers from preserved structured fields ONLY when not relative-owned (NEW-1)
        if not is_rel_field:
            if sem_kind is Sem.AGE:
                ages.update(extract_ages(text, structured=True))
                genders.update(extract_genders(text, structured=False))
            elif sem_kind is Sem.GENDER:
                genders.update(extract_genders(text, structured=True))
            elif sem_kind is Sem.RELATION:
                genders.update(extract_genders(text, structured=False))
            elif sem_kind is Sem.DISTRICT:
                dist = normalize_district(text)
                if dist:
                    districts.add(dist)
            elif sem_kind is Sem.DOB:
                mf = bool(f.label and "mm/dd" in f.label.lower())
                de, by = normalize_dob(text, month_first_hint=mf)
                if de:
                    dobs.add(de)
                if by:
                    birth_years.add(by)
            elif (
                f.kind in (FieldKind.TEXT, FieldKind.BASE64_TEXT) or sem_kind in (Sem.FREE_TEXT, Sem.UNKNOWN)
            ) and f.channel is Channel.CONTENT:
                own_ages, own_genders = _patient_owned_demographics(text)
                ages.update(own_ages)
                genders.update(own_genders)

        # Extract identity evidence strictly from Phase 2 resolved findings
        findings = analysis.findings.get(f.address, ())
        _consume_findings(
            text=text,
            field=f,
            sem_kind=sem_kind,
            findings=findings,
            hospital=rec_hospital,
            is_external_lab=rec_is_lab,
            aadhaar=aadhaar,
            abha_num=abha_num,
            abha_addr=abha_addr,
            pan=pan,
            insurance=insurance,
            email=email,
            local_ids=local_ids,
            local_cores=local_cores,
            raw_mrns=raw_mrns,
            patient_names=patient_names,
            relative_names=relative_names,
            phones=phones,
            dobs=dobs,
            birth_years=birth_years,
            villages=villages,
            pins=pins,
            relative_ids=relative_ids,
        )

    # Assemble split first/middle/last names into one combined full NameEvidence (highest priority)
    if split_first and split_last:
        combined = combine_name_parts(
            [*split_first, *split_middle, *split_last], confidence=0.95, source="structured_split"
        )
        if combined is not None:
            # Remove single-token fragments that are subsumed by the combined full name
            comb_set = set(combined.strict_tokens)
            patient_names = [n for n in patient_names if not (n.is_single_token and n.strict_tokens[0] in comb_set)]
            patient_names.insert(0, combined)
    if rel_split_first and rel_split_last:
        rel_combined = combine_name_parts(
            [*rel_split_first, *rel_split_middle, *rel_split_last], confidence=0.92, source="structured_split_relative"
        )
        if rel_combined is not None:
            relative_names.append(rel_combined)

    return RecordEvidence(
        record=RecordKey(doc.source.rel, loc),
        hospital=rec_hospital,
        is_external_lab=rec_is_lab,
        hospital_reliable=rec_reliable,
        aadhaar=frozenset(aadhaar),
        abha_number=frozenset(abha_num),
        abha_address=frozenset(abha_addr),
        pan=frozenset(pan),
        insurance_id=frozenset(insurance),
        email=frozenset(email),
        local_ids=frozenset(local_ids),
        local_id_cores=frozenset(local_cores),
        raw_mrns=frozenset(raw_mrns),
        patient_names=_dedup_names(patient_names),
        relative_names=_dedup_names(relative_names),
        phones=frozenset(phones),
        dobs=frozenset(dobs),
        birth_years=frozenset(birth_years),
        ages=frozenset(ages),
        genders=frozenset(genders),
        villages=frozenset(villages),
        districts=frozenset(districts),
        pins=frozenset(pins),
        relative_global_ids=frozenset(relative_ids),
    )


# --------------------------------------------------------------------------- FHIR extraction
def _extract_fhir_document(
    doc: Document,
    analysis: DocumentAnalysis,
    hospital: str | None,
    is_external_lab: bool,
) -> RecordEvidence:
    """Extract patient identity evidence from a FHIR R4 Bundle or standalone resource.

    Handles ``Patient``, ``RelatedPerson``, ``Patient.contact``, ``contained`` Patient
    resources, and nested Bundles while keeping ``Practitioner`` strictly excluded.
    If multiple distinct ``Patient`` resources with conflicting identities exist in a
    single-document Bundle, flags ``ambiguous_doc=True`` so it is not falsely merged.
    """
    aadhaar: set[str] = set()
    abha_num: set[str] = set()
    abha_addr: set[str] = set()
    pan: set[str] = set()
    insurance: set[str] = set()
    email: set[str] = set()
    local_ids: set[tuple[str, str]] = set()
    local_cores: set[tuple[str, str]] = set()
    raw_mrns: set[tuple[str, bool]] = set()
    patient_names: list[NameEvidence] = []
    relative_names: list[NameEvidence] = []
    phones: set[str] = set()
    dobs: set[DateEvidence] = set()
    birth_years: set[int] = set()
    ages: set[int] = set()
    genders: set[str] = set()
    villages: set[str] = set()
    districts: set[str] = set()
    pins: set[str] = set()
    relative_ids: set[str] = set()

    # Walk native FHIR JSON to find all Patient & RelatedPerson resources (including contained / nested Bundles)
    patients: list[dict[str, Any]] = []
    related_persons: list[dict[str, Any]] = []
    _collect_fhir_resources(doc.native, patients, related_persons)

    per_patient_evs = [_extract_single_fhir_patient(doc.source.rel, p, hospital, is_external_lab) for p in patients]
    if len(per_patient_evs) > 1 and _fhir_patients_are_ambiguous(per_patient_evs):
        return RecordEvidence(
            record=RecordKey(doc.source.rel, "doc"),
            hospital=hospital,
            is_external_lab=is_external_lab,
            ambiguous_doc=True,
        )

    for pev in per_patient_evs:
        aadhaar |= pev.aadhaar
        abha_num |= pev.abha_number
        abha_addr |= pev.abha_address
        pan |= pev.pan
        insurance |= pev.insurance_id
        email |= pev.email
        local_ids |= pev.local_ids
        local_cores |= pev.local_id_cores
        raw_mrns |= pev.raw_mrns
        patient_names.extend(pev.patient_names)
        relative_names.extend(pev.relative_names)
        phones |= pev.phones
        dobs |= pev.dobs
        birth_years |= pev.birth_years
        ages |= pev.ages
        genders |= pev.genders
        villages |= pev.villages
        districts |= pev.districts
        pins |= pev.pins
        relative_ids |= pev.relative_global_ids

    # RelatedPerson resources -> relative_names; their person-unique identifiers -> relative_ids (veto only, F4)
    for rp in related_persons:
        ev = _fhir_person_name(rp, source="fhir_related_person")
        if ev:
            relative_names.append(ev)
        for ident in rp.get("identifier") or []:
            if isinstance(ident, dict) and isinstance(ident.get("value"), str):
                _extract_fhir_relative_identifier(ident, relative_ids)

    # Also inspect findings from non-Practitioner/non-RelatedPerson narrative / text / attachment fields
    for f in doc.fields:
        if f.fhir and f.fhir.resource_type in ("Practitioner", "PractitionerRole", "Organization", "Location"):
            continue
        sem = analysis.semantics.get(f.address)
        sem_kind = sem.sem if sem is not None else Sem.UNKNOWN
        if sem_kind in _SKIP_IDENTITY_SEMS:
            continue
        text = _field_text(f)
        if not text or not text.strip():
            continue
        if f.fhir and f.fhir.resource_type == "RelatedPerson":
            # RelatedPerson narratives/attachments never enter patient identity evidence (F4);
            # extract person-unique IDs into relative_ids (veto only).
            if f.fhir.role in ("narrative", "attachment") or f.kind is FieldKind.BASE64_TEXT:
                for fd in analysis.findings.get(f.address, ()):
                    if fd.confidence < 0.70:
                        continue
                    raw = views.decode_slice(text[fd.start : fd.end]).strip()
                    if raw:
                        _add_relative_id(fd.entity, raw, fd.detector, relative_ids)
            continue
        if f.fhir and f.fhir.role in ("narrative", "attachment") or f.kind is FieldKind.BASE64_TEXT:
            ages.update(_patient_owned_demographics(text)[0])
            _consume_findings(
                text=text,
                field=f,
                sem_kind=sem_kind,
                findings=analysis.findings.get(f.address, ()),
                hospital=hospital,
                is_external_lab=is_external_lab,
                aadhaar=aadhaar,
                abha_num=abha_num,
                abha_addr=abha_addr,
                pan=pan,
                insurance=insurance,
                email=email,
                local_ids=local_ids,
                local_cores=local_cores,
                raw_mrns=raw_mrns,
                patient_names=patient_names,
                relative_names=relative_names,
                phones=phones,
                dobs=dobs,
                birth_years=birth_years,
                villages=villages,
                pins=pins,
                relative_ids=relative_ids,
            )

    return RecordEvidence(
        record=RecordKey(doc.source.rel, "doc"),
        hospital=hospital,
        is_external_lab=is_external_lab,
        aadhaar=frozenset(aadhaar),
        abha_number=frozenset(abha_num),
        abha_address=frozenset(abha_addr),
        pan=frozenset(pan),
        insurance_id=frozenset(insurance),
        email=frozenset(email),
        local_ids=frozenset(local_ids),
        local_id_cores=frozenset(local_cores),
        raw_mrns=frozenset(raw_mrns),
        patient_names=_dedup_names(patient_names),
        relative_names=_dedup_names(relative_names),
        phones=frozenset(phones),
        dobs=frozenset(dobs),
        birth_years=frozenset(birth_years),
        ages=frozenset(ages),
        genders=frozenset(genders),
        villages=frozenset(villages),
        districts=frozenset(districts),
        pins=frozenset(pins),
        relative_global_ids=frozenset(relative_ids),
    )


def _extract_single_fhir_patient(
    rel: str,
    pat: dict[str, Any],
    hospital: str | None,
    is_external_lab: bool,
) -> RecordEvidence:
    """Extract an independent :class:`RecordEvidence` from one FHIR ``Patient`` resource (F3)."""
    aadhaar: set[str] = set()
    abha_num: set[str] = set()
    abha_addr: set[str] = set()
    pan: set[str] = set()
    email: set[str] = set()
    local_ids: set[tuple[str, str]] = set()
    local_cores: set[tuple[str, str]] = set()
    raw_mrns: set[tuple[str, bool]] = set()
    patient_names: list[NameEvidence] = []
    relative_names: list[NameEvidence] = []
    phones: set[str] = set()
    dobs: set[DateEvidence] = set()
    birth_years: set[int] = set()
    genders: set[str] = set()
    villages: set[str] = set()
    districts: set[str] = set()
    pins: set[str] = set()

    for nm in pat.get("name") or []:
        if not isinstance(nm, dict):
            continue
        given = [g for g in (nm.get("given") or []) if isinstance(g, str)]
        fam = nm.get("family") if isinstance(nm.get("family"), str) else ""
        if given or fam:
            ev = combine_name_parts([*given, fam], confidence=0.97, source="fhir_patient")
            if ev:
                patient_names.append(ev)
        if isinstance(nm.get("text"), str):
            ev = build_name_evidence(nm["text"], confidence=0.97, source="fhir_patient")
            if ev:
                patient_names.append(ev)
    for ident in pat.get("identifier") or []:
        if not isinstance(ident, dict) or not isinstance(ident.get("value"), str):
            continue
        val = ident["value"]
        sys_url = str(ident.get("system", ""))
        low = sys_url.lower()
        if any(w in low for w in ("aadhaar", "aadhar", "uidai")):
            a = normalize_aadhaar(val)
            if a:
                aadhaar.add(a)
        elif any(w in low for w in ("abdm", "healthid", "abha", "ndhm")):
            ab = normalize_abha_number(val)
            if ab:
                abha_num.add(ab)
            aba = normalize_abha_address(val)
            if aba:
                abha_addr.add(aba)
        elif any(w in low for w in ("incometax", "/pan", "pan")):
            p = normalize_pan(val)
            if p:
                pan.add(p)
        else:
            id_hosp = hospital
            if sys_url:
                slug, _ = normalize_hospital(sys_url)
                if slug:
                    id_hosp = slug
            _add_mrn(val, id_hosp, is_external_lab, local_ids, local_cores, raw_mrns)
    for tel in pat.get("telecom") or []:
        if not isinstance(tel, dict) or not isinstance(tel.get("value"), str):
            continue
        if str(tel.get("system", "")).lower() == "email":
            em = normalize_email(tel["value"])
            if em:
                email.add(em)
        else:
            ph = normalize_phone(tel["value"])
            if ph:
                phones.add(ph)
    if isinstance(pat.get("birthDate"), str):
        de, by = normalize_dob(pat["birthDate"])
        if de:
            dobs.add(de)
        if by:
            birth_years.add(by)
    if isinstance(pat.get("gender"), str):
        genders.update(extract_genders(pat["gender"], structured=True))
    for addr in pat.get("address") or []:
        if not isinstance(addr, dict):
            continue
        if isinstance(addr.get("city"), str):
            v = normalize_village(addr["city"])
            if v:
                villages.add(v)
        if isinstance(addr.get("district"), str):
            d = normalize_district(addr["district"])
            if d:
                districts.add(d)
        if isinstance(addr.get("postalCode"), str):
            pin = digits_only(addr["postalCode"])
            if len(pin) == 6:
                pins.add(pin)
    for contact in pat.get("contact") or []:
        if not isinstance(contact, dict):
            continue
        cname = contact.get("name")
        if isinstance(cname, dict):
            ev = _fhir_name_dict(cname, source="fhir_contact")
            if ev:
                relative_names.append(ev)
    for ext in pat.get("extension") or []:
        if not isinstance(ext, dict):
            continue
        url = str(ext.get("url", "")).lower()
        val = ext.get("valueString")
        if (
            isinstance(val, str)
            and "name" in url
            and any(w in url for w in ("mother", "father", "spouse", "guardian", "husband", "wife", "relative"))
        ):
            ev = build_name_evidence(val, confidence=0.92, source="fhir_extension")
            if ev:
                relative_names.append(ev)
    return RecordEvidence(
        record=RecordKey(rel, "doc"),
        hospital=hospital,
        is_external_lab=is_external_lab,
        hospital_reliable=hospital is not None and not is_external_lab,
        aadhaar=frozenset(aadhaar),
        abha_number=frozenset(abha_num),
        abha_address=frozenset(abha_addr),
        pan=frozenset(pan),
        email=frozenset(email),
        local_ids=frozenset(local_ids),
        local_id_cores=frozenset(local_cores),
        raw_mrns=frozenset(raw_mrns),
        patient_names=_dedup_names(patient_names),
        relative_names=_dedup_names(relative_names),
        phones=frozenset(phones),
        dobs=frozenset(dobs),
        birth_years=frozenset(birth_years),
        genders=frozenset(genders),
        villages=frozenset(villages),
        districts=frozenset(districts),
        pins=frozenset(pins),
    )


def _fhir_patients_are_ambiguous(per_patient_evs: list[RecordEvidence]) -> bool:
    """Return True unless every ``Patient`` resource in a multi-Patient FHIR Bundle is positively
    the same person (F3 / NEW-6B).

    Every Patient holding ANY identity field takes part (a partial Patient with only a gender, an
    age or a phone no longer vanishes from the check). A pair is acceptable when it is a confident
    match, or when one Patient is a partial duplicate whose every value already appears in the other
    (it adds no new identity evidence); any hard conflict, R7 contradiction or unconfirmed pair makes
    the Bundle ambiguous, so its evidence is never pooled.
    """
    from clinveil.linking.matcher import ClusterProfile, _distinct_mrns_same_issuer, compare_profiles, hard_conflicts
    from clinveil.linking.models import MatchOutcome

    non_empty = [ev for ev in per_patient_evs if ev.has_any_evidence]
    if len(non_empty) <= 1:
        return False
    profiles = [ClusterProfile.from_record(ev) for ev in non_empty]
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            pi, pj = profiles[i], profiles[j]
            if hard_conflicts(pi, pj) or _distinct_mrns_same_issuer(pi, pj):
                return True
            if compare_profiles(pi, pj).outcome is MatchOutcome.CONFIDENT_MATCH:
                continue
            if _evidence_subset(non_empty[i], non_empty[j]) or _evidence_subset(non_empty[j], non_empty[i]):
                continue
            return True
    return False


_SUBSET_FIELDS = (
    "aadhaar",
    "abha_number",
    "abha_address",
    "pan",
    "insurance_id",
    "email",
    "local_ids",
    "local_id_cores",
    "raw_mrns",
    "phones",
    "dobs",
    "ages",
    "genders",
    "villages",
    "districts",
    "pins",
    "relative_global_ids",
)


def _evidence_subset(small: RecordEvidence, big: RecordEvidence) -> bool:
    """Every identity value of ``small`` also appears in ``big`` (names compared exactly)."""
    if any(not getattr(small, f) <= getattr(big, f) for f in _SUBSET_FIELDS):
        return False
    if not small.all_birth_years() <= big.all_birth_years():
        return False
    big_names = {n.strict_tokens for n in big.patient_names}
    big_rel = {n.strict_tokens for n in big.relative_names}
    return all(n.strict_tokens in big_names for n in small.patient_names) and all(
        n.strict_tokens in big_rel for n in small.relative_names
    )


def _extract_fhir_relative_identifier(ident: dict[str, Any], relative_ids: set[str]) -> None:
    """Extract person-unique identifiers from ``RelatedPerson.identifier`` (Aadhaar, ABHA, PAN; F4)."""
    val = ident["value"]
    low = str(ident.get("system", "")).lower()
    if any(w in low for w in ("aadhaar", "aadhar", "uidai")):
        _add_relative_id(_E.AADHAAR, val, "fhir", relative_ids)
        return
    if any(w in low for w in ("abdm", "healthid", "abha", "ndhm")):
        _add_relative_id(_E.ABHA_NUMBER, val, "fhir", relative_ids)
        _add_relative_id(_E.ABHA_ADDRESS, val, "fhir", relative_ids)
        return
    if any(w in low for w in ("incometax", "/pan", "pan")):
        _add_relative_id(_E.PAN, val, "fhir", relative_ids)
        return
    # Generic or missing system URL: still capture validated person-unique identifier shapes for veto
    _add_relative_id(_E.AADHAAR, val, "fhir", relative_ids)
    _add_relative_id(_E.ABHA_ADDRESS, val, "fhir", relative_ids)
    _add_relative_id(_E.PAN, val, "fhir", relative_ids)


def _collect_fhir_resources(node: Any, patients: list[dict], related: list[dict]) -> None:
    if not isinstance(node, dict):
        return
    rt = node.get("resourceType")
    if rt == "Patient":
        patients.append(node)
    elif rt == "RelatedPerson":
        related.append(node)
    elif rt == "Bundle":
        for e in node.get("entry") or []:
            if isinstance(e, dict) and isinstance(e.get("resource"), dict):
                _collect_fhir_resources(e["resource"], patients, related)
    for c in node.get("contained") or []:
        if isinstance(c, dict):
            _collect_fhir_resources(c, patients, related)


def _fhir_name_dict(nm: dict[str, Any], *, source: str) -> NameEvidence | None:
    given = [g for g in (nm.get("given") or []) if isinstance(g, str)]
    fam = nm.get("family") if isinstance(nm.get("family"), str) else ""
    if given or fam:
        ev = combine_name_parts([*given, fam], confidence=0.95, source=source)
        if ev:
            return ev
    if isinstance(nm.get("text"), str):
        return build_name_evidence(nm["text"], confidence=0.95, source=source)
    return None


def _fhir_person_name(res: dict[str, Any], *, source: str) -> NameEvidence | None:
    for nm in res.get("name") or []:
        if isinstance(nm, dict):
            ev = _fhir_name_dict(nm, source=source)
            if ev:
                return ev
    return None


# --------------------------------------------------------------------------- finding consumption
def _consume_findings(
    *,
    text: str,
    field: Field,
    sem_kind: Sem,
    findings: list[Finding] | tuple[Finding, ...],
    hospital: str | None,
    is_external_lab: bool,
    aadhaar: set[str],
    abha_num: set[str],
    abha_addr: set[str],
    pan: set[str],
    insurance: set[str],
    email: set[str],
    local_ids: set[tuple[str, str]],
    local_cores: set[tuple[str, str]],
    raw_mrns: set[tuple[str, bool]],
    patient_names: list[NameEvidence],
    relative_names: list[NameEvidence],
    phones: set[str],
    dobs: set[DateEvidence],
    birth_years: set[int],
    villages: set[str],
    pins: set[str],
    relative_ids: set[str],
) -> None:
    is_relative_field = sem_kind in _RELATIVE_FIELD_SEMS or field_is_relative_owned(field, sem_kind)
    owner_text, starts_map = _build_owner_view(text) if findings and not is_relative_field else (text, None)
    for fd in findings:
        if fd.confidence < 0.70:
            continue
        raw = views.decode_slice(text[fd.start : fd.end]).strip()
        if not raw:
            continue
        ent = fd.entity
        if ent in _OWNED_ENTITIES:
            owner = "relative" if is_relative_field else _finding_owner(owner_text, starts_map, fd.start)
            if owner == "relative":
                _add_relative_id(ent, raw, fd.detector, relative_ids)
                continue
            if owner == "ambiguous":
                continue
        if ent is _E.AADHAAR:
            if fd.detector == "field_weak":
                continue
            a = normalize_aadhaar(raw)
            if a:
                aadhaar.add(a)
        elif ent is _E.AADHAAR_MASKED:
            continue  # Masked Aadhaar is NEVER a unique linking identifier
        elif ent is _E.ABHA_NUMBER:
            if fd.detector == "field_weak":
                continue
            ab = normalize_abha_number(raw)
            if ab:
                abha_num.add(ab)
        elif ent is _E.ABHA_ADDRESS:
            aba = normalize_abha_address(raw)
            if aba:
                abha_addr.add(aba)
        elif ent is _E.PAN:
            p = normalize_pan(raw)
            if p:
                pan.add(p)
        elif ent is _E.INSURANCE_ID:
            if fd.detector == "field_weak":
                continue
            ins = normalize_insurance(raw)
            if ins:
                insurance.add(ins)
        elif ent is _E.EMAIL:
            em = normalize_email(raw)
            if em and not is_relative_field:
                email.add(em)
        elif ent is _E.MRN:
            if fd.detector in ("field_weak", "id_shape"):
                continue
            _add_mrn(raw, hospital, is_external_lab, local_ids, local_cores, raw_mrns, field.label)
        elif ent is _E.PHONE:
            ph = normalize_phone(raw)
            if ph and not is_relative_field:
                phones.add(ph)
        elif ent is _E.PATIENT_NAME:
            if fd.detector in ("field_weak", "loose_adjacent_name"):
                continue
            owner = (
                "relative"
                if is_relative_field
                else (
                    "patient"
                    if fd.detector == "name_before_relation"
                    else _finding_owner(owner_text, starts_map, fd.start)
                )
            )
            if owner == "ambiguous":
                continue
            ev = build_name_evidence(raw, confidence=fd.confidence, source=fd.detector)
            if ev:
                if owner == "relative":
                    relative_names.append(ev)
                else:
                    patient_names.append(ev)
        elif ent is _E.RELATIVE_NAME:
            if fd.detector == "field_weak":
                continue
            ev = build_name_evidence(raw, confidence=fd.confidence, source=fd.detector)
            if ev:
                relative_names.append(ev)
        elif ent is _E.DOB:
            owner = "relative" if is_relative_field else _finding_owner(owner_text, starts_map, fd.start)
            if owner != "patient":
                continue
            mf = bool(field.label and "mm/dd" in field.label.lower())
            de, by = normalize_dob(raw, month_first_hint=mf)
            if de:
                dobs.add(de)
            if by:
                birth_years.add(by)
        elif ent is _E.VILLAGE:
            owner = "relative" if is_relative_field else _finding_owner(owner_text, starts_map, fd.start)
            if owner != "patient":
                continue
            v = normalize_village(raw)
            if v:
                villages.add(v)
        elif ent is _E.PIN:
            owner = "relative" if is_relative_field else _finding_owner(owner_text, starts_map, fd.start)
            if owner != "patient":
                continue
            pin = digits_only(raw)
            if len(pin) == 6:
                pins.add(pin)


def _add_relative_id(ent: EntityType, raw: str, detector: str, relative_ids: set[str]) -> None:
    """Keep a relative's person-unique identifier apart (veto only, never patient evidence)."""
    if detector == "field_weak":
        return
    if ent is _E.AADHAAR:
        a = normalize_aadhaar(raw)
        if a:
            relative_ids.add("aadhaar|" + a)
    elif ent is _E.ABHA_NUMBER:
        ab = normalize_abha_number(raw)
        if ab:
            relative_ids.add("abha|" + ab)
    elif ent is _E.ABHA_ADDRESS:
        aba = normalize_abha_address(raw)
        if aba:
            relative_ids.add("abhaa|" + aba)
    elif ent is _E.PAN:
        p = normalize_pan(raw)
        if p:
            relative_ids.add("pan|" + p)


def _add_mrn(
    raw: str,
    hospital: str | None,
    is_external_lab: bool,
    local_ids: set[tuple[str, str]],
    local_cores: set[tuple[str, str]],
    raw_mrns: set[tuple[str, bool]],
    label: str | None = None,
) -> None:
    norm = normalize_mrn(raw, None if is_external_lab else hospital, label)
    if norm is None:
        return
    scope, canonical, typed_core, distinctive = norm
    local_ids.add((scope, canonical))
    if len(typed_core.split(":", 1)[1]) >= 5:
        local_cores.add((scope, typed_core))
    raw_mrns.add((canonical, distinctive))


def _field_text(f: Field) -> str | None:
    if f.kind is FieldKind.JSON_NUMBER and not isinstance(f.value, bool):
        return str(f.value)
    return f.value if isinstance(f.value, str) else None


def _dedup_names(items: list[NameEvidence]) -> tuple[NameEvidence, ...]:
    seen: set[tuple[str, ...]] = set()
    # Keep multi-token, higher-confidence names first
    ordered = sorted(items, key=lambda n: (-len(n.strict_tokens), -n.confidence, n.strict_tokens))
    out: list[NameEvidence] = []
    for n in ordered:
        if n.strict_tokens not in seen:
            seen.add(n.strict_tokens)
            out.append(n)
    return tuple(out)
