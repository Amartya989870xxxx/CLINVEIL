"""Phase 2.1: reproduction + regression tests for the independent Phase 2 audit.

Each test is named after the audit finding it reproduces (B1…E4, see
docs/evaluation/PHASE2_REMEDIATION.md). They were run against the unmodified
Phase 2 code (``ac37504``) first to record which findings reproduce, then kept as
regression tests. All identities are invented; no practice data is used.
"""

from __future__ import annotations

import base64
import html
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET

import pytest

from conftest import sanitize_documents, sanitize_text

PAT, PAT_G, PAT_S = "Orvila Tamsen", "Orvila", "Tamsen"
REL = "Kelvar Dunmore"
UHID, PHONE, AADHAAR = "TST/26/000101", "9876543210", "2345 6789 0123"
XHTML = "http://www.w3.org/1999/xhtml"


def _fhir_bundle(extra_entries: list[dict], patient_extra: dict | None = None) -> dict:
    patient = {
        "resourceType": "Patient",
        "id": "p-1",
        "name": [{"text": PAT}],
        "identifier": [{"system": "https://hosp.example/uhid", "value": UHID}],
        "telecom": [{"system": "phone", "value": PHONE}],
        **(patient_extra or {}),
    }
    entries = [{"fullUrl": "urn:uuid:p-1", "resource": patient}]
    for i, res in enumerate(extra_entries):
        entries.append({"fullUrl": f"urn:uuid:r-{i}", "resource": {"id": f"r-{i}", **res}})
    return {"resourceType": "Bundle", "id": "b-1", "type": "document", "entry": entries}


def _run_bundle(bundle: dict, **more: bytes) -> tuple[dict, str]:
    files = {"fhir/bundle.json": json.dumps(bundle, ensure_ascii=False).encode(), **more}
    out = sanitize_documents(files)
    text = out["fhir/bundle.json"]
    return json.loads(text), text


SUBJ = {"reference": "urn:uuid:p-1"}


# --------------------------------------------------------------------------- B1 non-Patient FHIR resources
def test_B1_non_patient_fhir_free_text_and_ids_are_detected():
    bundle = _fhir_bundle(
        [
            {
                "resourceType": "Observation",
                "status": "final",
                "subject": SUBJ,
                "code": {"coding": [{"system": "http://loinc.org", "code": "718-7", "display": "Hemoglobin"}]},
                "valueQuantity": {"value": 9.4, "unit": "g/dL", "system": "http://unitsofmeasure.org", "code": "g/dL"},
                "note": [{"text": f"Pt. {PAT}, Mob: +91 98765 43210, Aadhaar: {AADHAAR}"}],
            },
            {
                "resourceType": "DiagnosticReport",
                "status": "final",
                "subject": SUBJ,
                "conclusion": f"Discussed with S/o {REL} ({PHONE}). Hb 9.4 g/dL, iron deficiency.",
            },
            {"resourceType": "Composition", "status": "final", "subject": SUBJ, "title": f"Discharge summary of {PAT}"},
            {
                "resourceType": "DocumentReference",
                "status": "current",
                "subject": SUBJ,
                "description": f"Scanned letter for {PAT}",
            },
            {
                "resourceType": "MedicationRequest",
                "status": "active",
                "intent": "order",
                "subject": SUBJ,
                "medicationCodeableConcept": {"text": "Tab Dolo 650"},
                "dosageInstruction": [{"text": "1-0-1 x 5 days"}],
                "note": [{"text": f"Explained to {PAT}"}],
            },
            {
                "resourceType": "Condition",
                "subject": SUBJ,
                "code": {"text": "Parkinson's disease"},
                "note": [{"text": f"{PAT} reports C/O fever x 3 days"}],
            },
            {
                "resourceType": "Coverage",
                "status": "active",
                "beneficiary": SUBJ,
                "subscriberId": "PMJAY-UP-9876543210",
            },
        ]
    )
    out, text = _run_bundle(bundle)
    for leaked in (PAT_G, PAT_S, "Kelvar", "Dunmore", PHONE, "98765", "6789", "PMJAY", "000101"):
        assert leaked not in text, leaked
    for kept in (
        "718-7",
        "Hemoglobin",
        "g/dL",
        "9.4",
        "Tab Dolo 650",
        "1-0-1 x 5 days",
        "Parkinson's disease",
        "C/O fever x 3 days",
        "iron deficiency",
        "final",
        "active",
        "order",
    ):
        assert kept in text, kept
    from clinveil.parsing.fhir import build_index

    assert not build_index(out).unresolved and len(build_index(out).references) == 7


# --------------------------------------------------------------------------- B2 XHTML narrative
def _patient_div(div: str) -> tuple[str, str]:
    out, _ = _run_bundle(_fhir_bundle([], {"text": {"status": "generated", "div": div}}))
    new = out["entry"][0]["resource"]["text"]["div"]
    ET.fromstring(new)  # noqa: S314 - parses our own test output (well-formedness check), not untrusted data
    return new, html.unescape(new)


def test_B2_xhtml_address_keeps_markup():
    new, plain = _patient_div(f'<div xmlns="{XHTML}"><p>Address: H.No. 47, Bhatpurwa Kheda</p></div>')
    assert new.endswith("</p></div>") and f'xmlns="{XHTML}"' in new
    assert "Bhatpurwa" not in plain and "H.No. 47" not in plain


def test_B2_B4_html_entities_in_narrative_are_decoded_for_detection():
    div = f'<div xmlns="{XHTML}"><p>&#79;rvila Tamsen &amp; mob &#x39;&#x38;&#x37;&#x36;&#x35;43210</p></div>'
    new, plain = _patient_div(div)
    assert "Orvila" not in plain and "Tamsen" not in plain and PHONE not in plain
    assert "&amp;" in new or "&#38;" in new  # the literal ampersand stays escaped


# --------------------------------------------------------------------------- B3 fuzzy PRESERVED bypass
def test_B3_fields_classified_as_preserved_still_get_pii_detection():
    csv = (
        "MRN,Patient Name,Diet,Mode,Religion\n"
        f"{UHID},{PAT},Diet explained to S/o Kelvan Vexpal {PHONE},"
        f"Mode of arrival: brought by {REL} 9123456780,Hindu\n"
        "TST/26/000102,Kirti Lanmore,Normal,Emergency,Sikh\n"
    )
    out = sanitize_documents({"reg/visits.csv": csv.encode()})["reg/visits.csv"]
    for leaked in ("Vexpal", PHONE, "Kelvar", "Dunmore", "9123456780"):
        assert leaked not in out, leaked
    for kept in ("Hindu", "Normal", "Emergency", "Sikh", "Diet explained to", "Mode of arrival"):
        assert kept in out, kept


# --------------------------------------------------------------------------- B4 encoded / Indic channels
def test_B4_percent_encoded_paths():
    meta = {"_meta": {"source": "file:///exports/Orvila%20Tamsen/TST%2F26%2F004417.json"}, "rows": [{"a": 1}]}
    out = sanitize_documents(
        {
            "reg/r.csv": f"MRN,Patient Name\nTST/26/004417,{PAT}\n".encode(),
            "opd/x.json": json.dumps(meta).encode(),
        }
    )["opd/x.json"]
    src = json.loads(out)["_meta"]["source"]
    decoded = urllib.parse.unquote(src)
    assert "Tamsen" not in decoded and "Orvila" not in decoded and "004417" not in decoded
    assert src.startswith("file:///exports/")


@pytest.mark.parametrize("digits", ["৯৮৭৬৫৪৩২১০", "੯੮੭੬੫੪੩੨੧੦", "૯૮૭૬૫૪૩૨૧૦", "௯௮௭௬௫௪௩௨௧௦", "౯౮౭౬౫౪౩౨౧౦"])
def test_B4_non_devanagari_indic_digits(digits):
    assert digits not in sanitize_text(f"मोबाइल: {digits}")


def test_B4_url_safe_and_digit_only_base64():
    urlsafe = base64.urlsafe_b64encode(f"Referral. Name: {PAT}?? phone {PHONE}>>".encode()).decode().rstrip("=")
    assert "-" in urlsafe or "_" in urlsafe
    note = f"Scanned form: {urlsafe} end"
    out = sanitize_text(note)
    decoded_parts = [
        base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8", "ignore")
        for tok in out.split()
        if len(tok) >= 24
    ]
    assert all(PAT_G not in d and PHONE not in d for d in decoded_parts)
    declared = {"attachment": {"contentType": "text/plain", "data": base64.b64encode(PHONE.encode()).decode()}}
    res = json.loads(sanitize_documents({"forms/f.json": json.dumps(declared).encode()})["forms/f.json"])
    assert PHONE not in base64.b64decode(res["attachment"]["data"]).decode()


# --------------------------------------------------------------------------- C1 fragmented identity
def test_C1_patient_before_relationship_marker_without_registration():
    out = sanitize_text("Rani, W/o Velan Kelkar admitted with fever.")
    assert "Rani" not in out and "Velan" not in out and "Kelkar" not in out and "fever" in out


def test_C1_patient_before_marker_with_registration_using_formerly_generic_token():
    out = sanitize_documents(
        {
            "reg/r.csv": b"MRN,Patient Name\nTST/26/000201,Rani Devi\n",
            "notes/n.txt": b"Rani, W/o Velan Kelkar admitted.",
        }
    )["notes/n.txt"]
    assert "Rani" not in out


def test_C1_devanagari_patient_before_relation_word():
    out = sanitize_text("मरीज़ रानी पत्नी वेलन केलकर भर्ती हुईं")
    assert "रानी" not in out and "वेलन" not in out


# --------------------------------------------------------------------------- C2 ABHA and landlines
@pytest.mark.parametrize(
    "text, value",
    [
        ("ABHA: 91234567890123", "91234567890123"),
        ("ABHA No 91234567890123", "91234567890123"),
        ("Health ID: 91234567890123", "91234567890123"),
        ("Landline: 0522-2234567", "2234567"),
        ("Ph (0522) 2234567", "2234567"),
        ("Tel: 011-23456789", "23456789"),
    ],
)
def test_C2_abha_and_landlines(text, value):
    assert value not in sanitize_text(text)


@pytest.mark.parametrize(
    "text", ["Platelets 150000-410000 /cumm", "WBC 11000 cells", "Sample 20261015123456", "Time 0100-1200 hrs"]
)
def test_C2_no_false_identifiers(text):
    assert sanitize_text(text) == text


# --------------------------------------------------------------------------- C3 doctor protection order
@pytest.mark.parametrize(
    "doctor", ["Dr. Md. Tarif", "Dr. Mohd. Zuvair", "Dr. Shri Kelvan", "dr. kelvan", "चिकित्सक: केलवन", "डॉक्टर: अरुण"]
)
def test_C3_doctor_names_survive_even_when_a_patient_shares_the_name(doctor):
    files = {
        "reg/r.csv": "MRN,Patient Name\nTST/26/000301,Tarif Vexpal\nTST/26/000302,Zuvair Tamsen\n"
        "TST/26/000303,Kelvan Dunmore\nTST/26/000304,अरुण केलकर\nTST/26/000305,केलवन लानमोर\n".encode(),
        "notes/n.txt": f"{doctor} examined the patient. Tarif Vexpal stable.".encode(),
    }
    out = sanitize_documents(files)["notes/n.txt"]
    assert doctor in out
    assert "Vexpal" not in out


# --------------------------------------------------------------------------- C4 transliteration
def test_C4_transliteration_fixes():
    from clinveil.detection.translit import name_key

    assert name_key("ज्ञान") == name_key("Gyan")
    assert name_key("Umar") == name_key("Omar")
    assert name_key("Ishaan") == name_key("Eshaan")
    assert name_key("Bimla") == name_key("Vimla")


def test_C4_strict_key_keeps_distinct_names_apart():
    from clinveil.detection.translit import name_key_strict

    for a, b in (("Kiran", "Karan"), ("Sita", "Satya"), ("Alok", "Alka")):
        assert name_key_strict(a) != name_key_strict(b)
    assert name_key_strict("Neeta") == name_key_strict("Nita")


# --------------------------------------------------------------------------- C5 roles
def _entities(text: str) -> dict[str, str]:
    from clinveil.detection.engine import DetectionEngine
    from clinveil.ingestion.detect import detect
    from clinveil.ingestion.limits import IngestLimits
    from clinveil.parsing.builder import build_document

    raw = text.encode()
    doc = build_document("notes/n.txt", "0" * 64, len(raw), ".txt", detect(raw, ".txt", IngestLimits()), IngestLimits())
    an = DetectionEngine(None).analyze(doc)
    return {text[f.start : f.end]: f.entity.value for f in an.findings.get("doc", [])}


def test_C5_roles_follow_context():
    ents = _entities("Tarun Vexpal, Mob: 9876543210 admitted with fever.")
    assert ents.get("Tarun Vexpal") == "PATIENT_NAME"
    ents = _entities("09:15 - Kelvar Dunmore (relative, bed 4), mob 9123456780")
    assert ents.get("Kelvar Dunmore") == "RELATIVE_NAME"


# --------------------------------------------------------------------------- C6 FHIR ids carrying hospital IDs
def test_C6_fhir_ids_with_embedded_hospital_ids_are_rewritten_consistently():
    bundle = {
        "resourceType": "Bundle",
        "id": "b-2",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "http://hosp.example/fhir/Patient/UHID-004417",
                "resource": {"resourceType": "Patient", "id": "UHID-004417", "name": [{"text": PAT}]},
            },
            {
                "fullUrl": "urn:uuid:0f4d2a9c-6b1e-4c3a-8d7f-2e9b5a1c7d40",
                "resource": {
                    "resourceType": "Encounter",
                    "id": "0f4d2a9c-6b1e-4c3a-8d7f-2e9b5a1c7d40",
                    "status": "finished",
                    "subject": {"reference": "Patient/UHID-004417"},
                },
            },
        ],
    }
    out, text = _run_bundle(bundle)
    assert "004417" not in text
    assert "0f4d2a9c-6b1e-4c3a-8d7f-2e9b5a1c7d40" in text  # ordinary UUIDs untouched
    from clinveil.parsing.fhir import build_index

    idx = build_index(out)
    assert not idx.unresolved and idx.references[0].target_entry == 0
    import re

    assert re.fullmatch(r"[A-Za-z0-9\-.]{1,64}", out["entry"][0]["resource"]["id"])


# --------------------------------------------------------------------------- D1 clinical columns
CLINICAL_COLUMNS = {
    "urea": "38 mg/dL",
    "Care Notes": "Intensive Care started",
    "Gram Stain": "Gram positive cocci",
    "Disease Name": "Parkinson's disease",
    "cell_count": "4500000",
    "birth_weight": "2.8 kg",
    "central_line": "present",
    "family_history": "Diabetes",
    "mother_tongue": "Hindi",
    "Diet": "Normal",
    "Mode": "Emergency",
    "Religion": "Hindu",
}


def test_D1_clinical_columns_are_not_pii_and_do_not_poison_other_files():
    header = "MRN,Patient Name," + ",".join(CLINICAL_COLUMNS)
    row = f"{UHID},{PAT}," + ",".join(CLINICAL_COLUMNS.values())
    prose = (
        "Urea 38 mg/dL. Intensive Care started. Gram positive cocci seen. Parkinson's disease. "
        "Birth weight 2.8 kg. Central line present. Diabetes in family. Speaks Hindi. Diet Normal. "
        "Emergency admission. Hindu."
    )
    out = sanitize_documents({"lab/panel.csv": f"{header}\n{row}\n".encode(), "notes/n.txt": prose.encode()})
    csv_out = out["lab/panel.csv"]
    for value in CLINICAL_COLUMNS.values():
        assert value in csv_out, value
    assert out["notes/n.txt"] == prose
    assert PAT_G not in csv_out


@pytest.mark.parametrize(
    "label",
    [
        "urea",
        "Care Notes",
        "Level of Care",
        "Intensive Care",
        "Primary Care",
        "Care Summary",
        "Gram Stain",
        "gram_stain",
        "Dose (gram)",
        "Disease Name",
        "Symptom Name",
        "Organism Name",
        "Vaccine Name",
        "Antibiotic Name",
        "Allergen Name",
        "Surgery Name",
        "Parameter Name",
        "cell_count",
        "white_blood_cell",
        "red_blood_cell",
        "sickle_cell",
        "stem_cell",
        "birth_weight",
        "birth_history",
        "birth_asphyxia",
        "central_line",
        "iv_line",
        "arterial_line",
        "line_infection",
        "base_line",
        "first_line",
        "family_history",
        "past_history",
        "emergency_severity",
        "emergency_medicine",
        "emergency_ward",
        "mother_tongue",
        "Diet",
        "Mode",
        "Religion",
    ],
)
def test_D1_label_is_not_a_pii_semantic(label):
    from clinveil.detection.semantics import STRUCTURED_PII, classify_label

    assert classify_label(label).sem not in STRUCTURED_PII, classify_label(label)


# --------------------------------------------------------------------------- D2 C/O complaint vs relative
def test_D2_care_of_complaints_never_poison_other_documents():
    files = {
        "opd/a.txt": b"C/O Left knee pain x 3 days. C/O Severe headache. C/O Acute chest pain. C/O Bilateral swelling.",
        "ds/b.txt": b"Diagnosis: Left lower lobe pneumonia. Severe anaemia. Acute gastritis. Bilateral pedal oedema.",
        "ds/c.txt": b"ECHO: Left ventricular ejection fraction 55%. Address: C/O Kelvan Vexpal, H.No. 9.",
        "ds/d.txt": b"C/O fever x 2 days.",
    }
    out = sanitize_documents(files)
    assert out["opd/a.txt"] == files["opd/a.txt"].decode()
    assert out["ds/b.txt"] == files["ds/b.txt"].decode()
    assert "Left ventricular ejection fraction 55%" in out["ds/c.txt"]
    assert "Kelvan" not in out["ds/c.txt"] and "Vexpal" not in out["ds/c.txt"]
    assert out["ds/d.txt"] == "C/O fever x 2 days."


# --------------------------------------------------------------------------- D3 Devanagari over-consumption
@pytest.mark.parametrize(
    "text, name, clinical",
    [
        ("नाम: वसुधा बुखार है", "वसुधा", "बुखार है"),
        ("नाम: वसुधा खांसी और दर्द", "वसुधा", "खांसी और दर्द"),
        ("नाम: वसुधा निदान: मधुमेह", "वसुधा", "निदान"),
        ("रोगी: वसुधा इलाज जारी, दवा दी गई", "वसुधा", "इलाज जारी, दवा दी गई"),
        ("नाम: वसुधा गोली सामान्य रक्तचाप", "वसुधा", "गोली सामान्य रक्तचाप"),
    ],
)
def test_D3_devanagari_names_stop_at_clinical_words(text, name, clinical):
    out = sanitize_text(text)
    assert name not in out and clinical in out


def test_D3_clinical_devanagari_words_never_propagate():
    out = sanitize_documents({"a/1.txt": "नाम: वसुधा बुखार है".encode(), "a/2.txt": "मरीज़ को बुखार है, खांसी भी".encode()})
    assert out["a/2.txt"] == "मरीज़ को बुखार है, खांसी भी"


# --------------------------------------------------------------------------- D4 assorted false positives
@pytest.mark.parametrize(
    "text",
    [
        "14:00 - Blood Transfusion started - no reaction",
        "14:00 - Foley Catheter inserted (16 Fr)",
        "Known Crohn's condition, Cushing's report awaited",
        "External fixator pin: 210045 checked",
        "Serial 293847561029 logged",
    ],
)
def test_D4_clinical_text_not_redacted(text):
    assert sanitize_text(text) == text


def test_D4_devanagari_district_kept_in_address():
    out = sanitize_text("पता: मकान नं. 731, ग्राम रामपुरा, उन्नाव")
    assert "उन्नाव" in out and "रामपुरा" not in out


def test_D4_date_like_codes_in_filenames_and_headers_kept():
    out = sanitize_documents({"lab/LAB-20261015.csv": b"test,Batch-202601\nHb,12.1\n"})
    assert list(out) == ["lab/LAB-20261015.csv"]
    assert out["lab/LAB-20261015.csv"].splitlines()[0] == "test,Batch-202601"


def test_D4_schema_keys_under_patient_are_not_names():
    doc = {"patient": {"name": PAT, "Blood Group": "O+", "Marital Status": "Married"}}
    out = json.loads(sanitize_documents({"x/p.json": json.dumps(doc).encode()})["x/p.json"])
    assert set(out["patient"]) == {"name", "Blood Group", "Marital Status"} and out["patient"]["Blood Group"] == "O+"


def test_D4_binary_fhir_attachment_withholds_only_the_payload():
    jpeg = base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(64)).decode()
    bundle = _fhir_bundle(
        [
            {
                "resourceType": "Observation",
                "status": "final",
                "subject": SUBJ,
                "code": {"text": "Hb"},
                "valueQuantity": {"value": 9.4, "unit": "g/dL"},
            },
            {
                "resourceType": "DocumentReference",
                "status": "current",
                "subject": SUBJ,
                "content": [{"attachment": {"contentType": "image/jpeg", "data": jpeg}}],
            },
        ]
    )
    out, text = _run_bundle(bundle)
    assert jpeg not in text and "/9j/" not in text
    att = out["entry"][2]["resource"]["content"][0]["attachment"]
    assert att.get("contentType") == "image/jpeg" and "data" not in att
    assert out["entry"][1]["resource"]["valueQuantity"]["value"] == 9.4
    from clinveil.parsing.fhir import build_index

    assert not build_index(out).unresolved


# --------------------------------------------------------------------------- E1 honest counts
def test_E1_report_counts_only_real_transformations(tmp_path):
    from conftest import run_cli

    bundle = {
        "resourceType": "Bundle",
        "id": "b",
        "type": "collection",
        "entry": [
            {"fullUrl": "urn:uuid:p", "resource": {"resourceType": "Patient", "id": "p", "birthDate": "1980"}},
            {
                "fullUrl": "urn:uuid:r",
                "resource": {
                    "resourceType": "RelatedPerson",
                    "id": "r",
                    "birthDate": "1955-06-10",
                    "patient": {"reference": "urn:uuid:p"},
                },
            },
            {"fullUrl": "urn:uuid:q", "resource": {"resourceType": "Patient", "id": "q", "birthDate": "1962-01-30"}},
        ],
    }
    inp = tmp_path / "in"
    (inp / "fhir").mkdir(parents=True)
    (inp / "fhir/b.json").write_text(json.dumps(bundle))
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    rep = json.loads((tmp_path / "out/report.json").read_text())
    out = json.loads((tmp_path / "out/sanitized/fhir/b.json").read_text())
    changed = sum(
        a["resource"]["birthDate"] != b["resource"]["birthDate"]
        for a, b in zip(bundle["entry"], out["entry"], strict=True)
    )
    assert changed == 2
    assert rep["entities"].get("DOB", 0) == changed == rep["counts"]["identifiers_detected"]
    assert rep["counts"]["records_generalized"] <= rep["counts"]["records_processed"] == 1


# --------------------------------------------------------------------------- E2 caches
def test_E2_pii_caches_are_cleared_after_a_run(tmp_path):
    from clinveil.config.policy import Policy
    from clinveil.detection import caches
    from clinveil.pipeline import run
    from clinveil.security.secrets import ReleaseSecret

    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "n.txt").write_text(f"Name: {PAT}, Mob {PHONE}")
    run(inp, tmp_path / "out", ReleaseSecret(b"k"), Policy())
    assert caches.total_cached_entries() == 0


# --------------------------------------------------------------------------- E3 symlinks
def test_E3_escaping_and_broken_symlinks(tmp_path):
    """Escaping links: target never read or hashed; broken links reported, not dropped (see S1)."""
    import hashlib

    from conftest import run_cli

    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "ok.txt").write_text("BP 120/80")
    secret = tmp_path / "outside.txt"
    secret.write_text(f"Name: {PAT}")
    (inp / "link.txt").symlink_to(secret)
    (inp / "dangling.txt").symlink_to(tmp_path / "does-not-exist.txt")
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    rep = json.loads((tmp_path / "out/report.json").read_text())
    assert hashlib.sha256(secret.read_bytes()).hexdigest() not in json.dumps(rep)  # never read, never hashed
    by_reason = {e.get("reason"): e for e in rep["files"] if e.get("reason")}
    assert by_reason["broken_symlink"]["status"] == "quarantined"
    link = by_reason["symlink_outside_input"]
    assert link["status"] == "suppressed" and link["output"] == "sanitized/link.txt"
    assert (tmp_path / "out/sanitized/link.txt").read_bytes() == b""  # content-free placeholder
    assert rep["counts"]["files_total"] == 3 and rep["counts"]["files_quarantined"] == 1
    released = "".join(p.read_text() for p in (tmp_path / "out").rglob("*") if p.is_file())
    assert PAT_G not in released


# --------------------------------------------------------------------------- E4 performance
def test_E4_resolution_scales_on_many_findings():
    text = " ".join(f"Name: Orvil{chr(97 + i % 26)}{i} Mob 98765{i % 100000:05d}" for i in range(6000))
    t0 = time.perf_counter()
    out = sanitize_text(text)
    assert time.perf_counter() - t0 < 20
    assert "98765" not in out


def test_B3_guarded_ids_do_not_take_mrn_digit_cores():
    """Phase 2.1 self-review: a visit number sharing a digit core with an MRN is not an MRN."""
    files = {
        "reg/r.csv": b"MRN,Patient Name\nTST/26/00418,Orvila Tamsen\n",
        "opd/v.json": json.dumps({"visits": [{"visit_id": "OPD/26/05/00418", "note": "seen"}]}).encode(),
    }
    out = json.loads(sanitize_documents(files)["opd/v.json"])
    assert out["visits"][0]["visit_id"] == "OPD/26/05/00418"


def test_C1_devanagari_names_starting_with_ka_ki_ke_after_relation_word():
    """Found by the Phase 2.1 adversarial generator: ``(?!का|की|के)`` also rejected names like केशव."""
    out = sanitize_text("मरीज़ नुका पुत्री केशव भर्ती")
    assert "नुका" not in out and "केशव" not in out and "भर्ती" in out
    assert sanitize_text("पिता का नाम: हरेंद्र वेक्सपाल").count("पिता का नाम") == 1


def test_C3_doctor_span_does_not_swallow_the_sentence():
    """Found by the adversarial generator: a doctor keep span must end at the doctor's name."""
    files = {
        "reg/r.csv": b"MRN,Patient Name\nTST/26/000401,Makita Velesh\n",
        "notes/n.txt": b"Dr. Makith Rovand saw Makita Velesh today. dr. kelvan agreed.",
    }
    out = sanitize_documents(files)["notes/n.txt"]
    assert "Dr. Makith Rovand" in out and "dr. kelvan" in out and "Velesh" not in out


def _valid_aadhaar() -> str:
    from clinveil.detection.identifiers import verhoeff_valid

    return next(f"23456789012{d}" for d in range(10) if verhoeff_valid(f"23456789012{d}"))


@pytest.mark.parametrize("payload", ["9876543210", "aadhaar", "ABHA:91234567890123"])
def test_B4_short_undeclared_digit_only_base64(payload):
    """A bare phone/Aadhaar/ABHA in base64 is only 14-28 characters: still decoded and cleaned."""
    payload = _valid_aadhaar() if payload == "aadhaar" else payload
    number = "".join(c for c in payload if c.isdigit())
    tok = base64.b64encode(payload.encode()).decode()
    out = sanitize_text(f"ref {tok} end")
    assert number not in "".join(
        base64.b64decode(t + "=" * (-len(t) % 4)).decode("utf-8", "ignore") for t in out.split()[1:-1]
    )


def test_B4_url_safe_payloads_stay_decodable_and_clean():
    """Phase 2 split URL-safe payloads at ``-``/``_`` and re-encoded fragments: ~9% became undecodable."""
    import binascii
    import random

    rng = random.Random(3)
    checked = 0
    for _ in range(200):
        pad = "".join(rng.choice("abcdefgh?>~") for _ in range(rng.randint(0, 9)))
        phone = str(9000000000 + rng.randint(0, 99999999))
        u = base64.urlsafe_b64encode(f"{pad} Name: {PAT}, Mob: {phone} >> {pad}".encode()).decode().rstrip("=")
        if "-" not in u and "_" not in u:
            continue
        checked += 1
        tok = sanitize_text(f"scan: {u} end").split()[1]
        try:
            plain = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8")
        except (binascii.Error, ValueError) as exc:
            raise AssertionError("payload corrupted") from exc
        assert PAT_G not in plain and PAT_S not in plain and phone not in plain
    assert checked > 100
