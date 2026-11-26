"""Extract normalised :class:`RecordEvidence` per record from the Phase 1/2 IR.

Reuses the already-parsed :class:`Document` and Phase 2 :class:`DocumentAnalysis`
without re-parsing any file. Enforces strict role separation:
* doctor, staff, organisation, and clinical fields never enter patient identity evidence;
* relative names enter ``relative_names`` only, never ``patient_names``;
* masked Aadhaar and non-Verhoeff 12-digit numbers never enter ``aadhaar``;
* low-confidence / ``field_weak`` findings never become global identifiers.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from clinveil.detection import views
from clinveil.detection.engine import DocumentAnalysis
from clinveil.detection.semantics import Sem, label_tokens
from clinveil.detection.text import digits_only
from clinveil.linking.models import DateEvidence, NameEvidence, RecordEvidence, RecordKey
from clinveil.linking.normalize import (
    build_name_evidence,
    combine_name_parts,
    extract_ages,
    extract_genders,
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
_HOSPITAL_HEADER_RE = re.compile(
    r"(?i)^[^\n]{2,80}(?:hospital|multispeciality|multi-speciality|charitable|sadan|clinic|medical\s+cent|health\s+cent|"
    r"pathology|diagnostics?|laboratory|अस्पताल|चिकित्सालय|सदन)"
)


def extract_document_evidence(doc: Document, analysis: DocumentAnalysis) -> list[RecordEvidence]:
    """Extract one :class:`RecordEvidence` per record in ``doc``."""
    if not doc.records:
        return []
    hospital, is_external_lab = _infer_document_hospital(doc, analysis)
    single_doc = doc.records == ["doc"]

    if doc.source.format is Format.FHIR:
        return [_extract_fhir_document(doc, analysis, hospital, is_external_lab)]

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

    out: list[RecordEvidence] = []
    for loc in doc.records:
        out.append(_extract_record(doc, loc, by_rec.get(loc, []), analysis, hospital, is_external_lab))
    return out


_FACILITY_LABELS = frozenset(
    {
        "facility",
        "hospital",
        "lab",
        "laboratory",
        "hospital_name",
        "facility_name",
        "clinic",
        "institution",
        "provider",
        "pathology",
    }
)
_STD_FHIR_DOMAINS = ("hl7.org", "loinc.org", "snomed.info", "abdm", "healthid", "abha", "ndhm", "aadhaar", "uidai")


# --------------------------------------------------------------------------- hospital inference
def _infer_document_hospital(doc: Document, analysis: DocumentAnalysis) -> tuple[str | None, bool]:
    """Infer issuing hospital scope from structured facility fields, FHIR systems, letterhead, or path."""
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
                        return slug, lab
            if f.fhir.resource_type == "Organization" and f.fhir.element == "Organization.name":
                slug, lab = normalize_hospital(f.value)
                if slug:
                    return slug, lab

    # 2. Structured facility / hospital / lab fields ONLY (never clinical test names or package codes)
    lab_slug: str | None = None
    for f in doc.fields:
        if not isinstance(f.value, str) or not f.value.strip():
            continue
        lbl = (f.label or "").lower()
        if lbl in _FACILITY_LABELS:
            if f.channel is Channel.METADATA and "path" in lbl:
                continue
            slug, lab = normalize_hospital(f.value)
            if lab:
                is_lab = True
                if slug:
                    lab_slug = slug
            elif slug:
                return slug, False

    # 3. Text document letterhead (first 3 non-empty lines)
    if doc.source.format is Format.TEXT and isinstance(doc.native, str):
        lines = [ln.strip() for ln in doc.native.splitlines() if ln.strip()][:3]
        for ln in lines:
            if _HOSPITAL_HEADER_RE.search(ln):
                slug, lab = normalize_hospital(ln)
                if slug:
                    return slug, lab or is_lab

    # 4. Path/filename stem (e.g. "registration/sanjeevani_registration.csv", "lab/...")
    parts = doc.source.rel.split("/")
    if any(p.lower() in ("lab", "labs", "pathology") for p in parts[:-1]):
        is_lab = True
    stem = parts[-1].rsplit(".", 1)[0]
    slug, stem_lab = normalize_hospital(stem)
    if stem_lab:
        is_lab = True
    if slug and not is_lab:
        return slug, False
    return (lab_slug or (slug if is_lab else None)), is_lab


# --------------------------------------------------------------------------- standard record extraction
def _extract_record(
    doc: Document,
    loc: str,
    fields: list[Field],
    analysis: DocumentAnalysis,
    hospital: str | None,
    is_external_lab: bool,
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

    # Check if this record overrides hospital (e.g., per-row hospital column in CSV/JSON)
    rec_hospital = hospital
    rec_is_lab = is_external_lab
    for f in fields:
        if isinstance(f.value, str) and f.label and f.label.lower() in ("hospital", "facility", "hospital_name"):
            slug, lab = normalize_hospital(f.value)
            if slug:
                rec_hospital = slug
                rec_is_lab = lab
                break

    # Collect split name parts within this record (FirstName / MiddleName / LastName)
    split_first: list[str] = []
    split_middle: list[str] = []
    split_last: list[str] = []

    for f in fields:
        sem = analysis.semantics.get(f.address)
        sem_kind = sem.sem if sem is not None else Sem.UNKNOWN
        if sem_kind in _SKIP_IDENTITY_SEMS:
            continue
        text = _field_text(f)
        if text is None or not text.strip():
            continue

        # Track split patient name columns / keys
        if sem_kind is Sem.PERSON_NAME and f.label and f.channel is Channel.CONTENT:
            lt = set(label_tokens(f.label))
            if lt & _FIRST_NAME_TOKS and not (lt & _LAST_NAME_TOKS):
                split_first.append(text.strip())
            elif lt & _MIDDLE_NAME_TOKS:
                split_middle.append(text.strip())
            elif lt & _LAST_NAME_TOKS and not (lt & _FIRST_NAME_TOKS):
                split_last.append(text.strip())

        # Extract quasi-identifiers from preserved structured fields (Age, Gender, District, Relation)
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
            ages.update(extract_ages(text, structured=False))
            genders.update(extract_genders(text, structured=False))

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

    return RecordEvidence(
        record=RecordKey(doc.source.rel, loc),
        hospital=rec_hospital,
        is_external_lab=rec_is_lab,
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

    # Walk native FHIR JSON to find all Patient & RelatedPerson resources (including contained / nested Bundles)
    patients: list[dict[str, Any]] = []
    related_persons: list[dict[str, Any]] = []
    _collect_fhir_resources(doc.native, patients, related_persons)

    ambiguous_multi_patient = False
    if len(patients) > 1:
        # Check if multiple Patient resources represent distinct conflicting people
        per_p_names: list[NameEvidence] = []
        for p in patients:
            n = _fhir_person_name(p, source="fhir_patient")
            if n:
                per_p_names.append(n)
        if len(per_p_names) >= 2:
            from clinveil.linking.models import NameGrade
            from clinveil.linking.normalize import compare_names

            if any(compare_names(per_p_names[0], other) is NameGrade.CONFLICT for other in per_p_names[1:]):
                ambiguous_multi_patient = True

    if ambiguous_multi_patient:
        return RecordEvidence(
            record=RecordKey(doc.source.rel, "doc"),
            hospital=hospital,
            is_external_lab=is_external_lab,
            ambiguous_doc=True,
        )

    for pat in patients:
        # Names (given + family assembled cleanly, plus text)
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
        # Identifiers (respecting system URL for hospital scoping vs ABHA/Aadhaar)
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
            else:
                id_hosp = hospital
                if sys_url:
                    slug, _ = normalize_hospital(sys_url)
                    if slug:
                        id_hosp = slug
                _add_mrn(val, id_hosp, is_external_lab, local_ids, local_cores, raw_mrns)
        # Telecom (patient's own phone / email)
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
        # DOB & gender
        if isinstance(pat.get("birthDate"), str):
            de, by = normalize_dob(pat["birthDate"])
            if de:
                dobs.add(de)
            if by:
                birth_years.add(by)
        if isinstance(pat.get("gender"), str):
            genders.update(extract_genders(pat["gender"], structured=True))
        # Address
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
        # Patient.contact -> relative_names only (NEVER patient_names or patient phones!)
        for contact in pat.get("contact") or []:
            if not isinstance(contact, dict):
                continue
            cname = contact.get("name")
            if isinstance(cname, dict):
                ev = _fhir_name_dict(cname, source="fhir_contact")
                if ev:
                    relative_names.append(ev)
        # Extensions carrying mother/father/guardian name
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

    # RelatedPerson resources -> relative_names only
    for rp in related_persons:
        ev = _fhir_person_name(rp, source="fhir_related_person")
        if ev:
            relative_names.append(ev)

    # Also inspect findings from non-Practitioner narrative / text / attachment fields for extra IDs or cues
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
        if f.fhir and f.fhir.role in ("narrative", "attachment") or f.kind is FieldKind.BASE64_TEXT:
            ages.update(extract_ages(text, structured=False))
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
    )


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
) -> None:
    is_relative_field = sem_kind in _RELATIVE_FIELD_SEMS
    for fd in findings:
        if fd.confidence < 0.70:
            continue
        raw = views.decode_slice(text[fd.start : fd.end]).strip()
        if not raw:
            continue
        ent = fd.entity
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
            _add_mrn(raw, hospital, is_external_lab, local_ids, local_cores, raw_mrns)
        elif ent is _E.PHONE:
            ph = normalize_phone(raw)
            if ph and not is_relative_field:
                phones.add(ph)
        elif ent is _E.PATIENT_NAME:
            if is_relative_field or fd.detector in ("field_weak", "loose_adjacent_name"):
                continue
            ev = build_name_evidence(raw, confidence=fd.confidence, source=fd.detector)
            if ev:
                patient_names.append(ev)
        elif ent is _E.RELATIVE_NAME:
            if fd.detector == "field_weak":
                continue
            ev = build_name_evidence(raw, confidence=fd.confidence, source=fd.detector)
            if ev:
                relative_names.append(ev)
        elif ent is _E.DOB:
            mf = bool(field.label and "mm/dd" in field.label.lower())
            de, by = normalize_dob(raw, month_first_hint=mf)
            if de:
                dobs.add(de)
            if by:
                birth_years.add(by)
        elif ent is _E.VILLAGE:
            v = normalize_village(raw)
            if v:
                villages.add(v)
        elif ent is _E.PIN:
            pin = digits_only(raw)
            if len(pin) == 6:
                pins.add(pin)


def _add_mrn(
    raw: str,
    hospital: str | None,
    is_external_lab: bool,
    local_ids: set[tuple[str, str]],
    local_cores: set[tuple[str, str]],
    raw_mrns: set[tuple[str, bool]],
) -> None:
    norm = normalize_mrn(raw, None if is_external_lab else hospital)
    if norm is None:
        return
    scope, canonical, core, distinctive = norm
    local_ids.add((scope, canonical))
    if len(core) >= 5:
        local_cores.add((scope, core))
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
