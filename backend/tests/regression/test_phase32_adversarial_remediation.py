"""Phase 3.2: adversarial regression tests for F1–F9 from the independent Phase 3.1 audit.

All patient names, relative names, identifiers, phone numbers, and hospital names are
completely invented synthetic fixtures (zero practice-dataset overlap).
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import pytest

from clinveil.config.policy import Policy
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.linking.matcher import ClusterProfile
from clinveil.linking.models import DateEvidence, LinkingStats, RecordEvidence, RecordKey
from clinveil.linking.normalize import normalize_hospital
from clinveil.linking.pseudonyms import assign_pseudonyms
from clinveil.pipeline import run
from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.security.secrets import ReleaseSecret
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_A = _aadhaar("24158293041")
AAD_B = _aadhaar("35269304152")
AAD_C = _aadhaar("46370415263")
AAD_D = _aadhaar("57481526374")
PAN_A = "BCDPE1234K"
PAN_B = "FGHPK9876L"


def _run_link(tmp_path: Path, files: dict[str, str], *, expect_ok: bool = True):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    for rel, content in files.items():
        p = inp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    summary = run(inp, out, ReleaseSecret(TEST_SECRET.encode()), Policy())
    if expect_ok:
        assert summary.ok, summary.problems
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    # Map by content hash when unique; fall back to output path (strip sanitized/)
    sha_to_in: dict[str, list[str]] = {}
    for rel, c in files.items():
        sha_to_in.setdefault(hashlib.sha256(c.encode("utf-8")).hexdigest(), []).append(rel)
    out_to_in: dict[str, str] = {}
    for e in rep["files"]:
        out_rel = e.get("output")
        if not out_rel:
            continue
        cands = sha_to_in.get(e["input_sha256"], [])
        if len(cands) == 1:
            out_to_in[out_rel] = cands[0]
        else:
            out_to_in[out_rel] = out_rel.removeprefix("sanitized/")
    recs: dict[str, str | None] = {}
    for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[f"{out_to_in.get(r['file'], r['file'])}#{r['loc']}"] = r["patient"]
    return summary, recs


def _same(recs: dict[str, str | None], a: str, b: str) -> bool:
    return recs[a] is not None and recs[a] == recs[b]


# =========================================================================== F1: Critical MRN scope bypass
def test_F1_multi_hospital_cluster_cannot_merge_homonym_via_other_hospitals_mrn(tmp_path):
    """P1 visits Aurora (MRN-10001) & Beacon (MRN-20002), linked by Aadhaar.
    Homonym P2 at Beacon has MRN-10001 -> must NOT merge with P1 via Aurora's MRN-10001."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,Aadhaar,Father Name,Village\n"
                f"MRN-10001,Nolan Vermeer,{AAD_A},Gareth Vermeer,Keshavpur\n"
            ),
            "reg/beacon_hospital.csv": (
                "UHID,Patient Name,Aadhaar,Father Name,Village\n"
                f"MRN-20002,Nolan Vermeer,{AAD_A},Gareth Vermeer,Keshavpur\n"
                "MRN-10001,Nolan Vermeer,,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:1")


def test_F1_unknown_hospital_generic_mrn_does_not_merge_homonyms(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "uploads/batch_1.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
            ),
            "uploads/batch_2.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert not _same(recs, "uploads/batch_1.csv#row:0", "uploads/batch_2.csv#row:0")


def test_F1_non_hospital_word_stems_generic_and_prefixed_mrn_respect_homonym_vetoes(tmp_path):
    _, recs_gen = _run_link(
        tmp_path / "gen",
        {
            "reg/sunrise_opd.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
            ),
            "reg/lotus_opd.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert not _same(recs_gen, "reg/sunrise_opd.csv#row:0", "reg/lotus_opd.csv#row:0")

    _, recs_pfx = _run_link(
        tmp_path / "pfx",
        {
            "reg/stvincent_opd.csv": (
                "MRN,Patient Name,Father Name,Village\nSVH-2026-00451,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
            ),
            "reg/saraswati_opd.csv": (
                "MRN,Patient Name,Father Name,Village\nSVH-2026-00451,Nolan Vermeer,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert not _same(recs_pfx, "reg/stvincent_opd.csv#row:0", "reg/saraswati_opd.csv#row:0")


def test_F1_one_reliable_hospital_vs_unknown_hospital_generic_mrn_does_not_merge(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
            ),
            "uploads/batch_unknown.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-12345,Nolan Vermeer,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "uploads/batch_unknown.csv#row:0")


def test_F1_positive_external_lab_citing_hospital_generic_mrn_still_links(tmp_path):
    """Genuine external pathology lab citing hospital MRN with matching patient still links."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": "MRN,Patient Name,Age\nMRN-55112,Nolan Vermeer,34\n",
            "lab/horizon_pathology_lab.json": json.dumps(
                {
                    "lab": "Horizon Pathology Lab",
                    "patient": {"name": "Nolan Vermeer", "ref_mrn": "MRN-55112", "age": 34},
                    "panels": [{"test": "Hb", "value": "13.2"}],
                }
            ),
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "lab/horizon_pathology_lab.json#doc")


def test_F1_external_lab_generic_mrn_still_respects_homonym_veto(tmp_path):
    """External lab generic MRN must not override explicit father/village homonym conflict."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "MRN,Patient Name,Father Name,Village\nMRN-55112,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
            ),
            "lab/horizon_pathology_lab.json": json.dumps(
                {
                    "lab": "Horizon Pathology Lab",
                    "patient": {
                        "name": "Nolan Vermeer",
                        "ref_mrn": "MRN-55112",
                        "father_name": "Dorian Vermeer",
                        "village": "Rampur",
                    },
                    "panels": [{"test": "Hb", "value": "13.2"}],
                }
            ),
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "lab/horizon_pathology_lab.json#doc")


# =========================================================================== F2: Abbreviated-name transitive bridge
def test_F2_abbreviated_name_cannot_bridge_conflicting_full_names_across_stage_c1_passes(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": "Patient Name,DOB,Village,Age\nNolan Vermeer,1990-04-05,Keshavpur,35\n",
            "reg/beacon_hospital.csv": "Patient Name,DOB\nN. Vermeer,1990-04-05\n",
            "reg/cedar_hospital.csv": "Patient Name,Village,Age\nNathan Vermeer,Keshavpur,35\n",
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/cedar_hospital.csv#row:0")


def test_F2_abbreviated_name_in_strong_cluster_cannot_absorb_conflicting_full_name_weakly(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar,Mobile\nAUR-101,Nolan Vermeer,{AAD_A},9811122334\n",
            "reg/beacon_hospital.csv": f"UHID,Patient Name,Aadhaar,Mobile\nBCN-101,N. Vermeer,{AAD_A},9811122334\n",
            "reg/cedar_hospital.csv": "Patient Name,Mobile\nNathan Vermeer,9811122334\n",
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/cedar_hospital.csv#row:0")


def test_F2_positive_legitimate_abbreviated_and_full_name_still_link(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": "Patient Name,DOB,Mobile\nNolan Vermeer,1990-04-05,9811122334\n",
            "reg/beacon_hospital.csv": "Patient Name,DOB\nN. Vermeer,1990-04-05\n",
            "reg/cedar_hospital.csv": "Patient Name,Mobile\nNolan Vermeer,9811122334\n",
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/cedar_hospital.csv#row:0")


# =========================================================================== F3: Multi-patient FHIR Bundle
def test_F3_fhir_bundle_with_homonym_patients_and_distinct_aadhaars_abstains(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "id": "b-multi-homonym",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333331",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "birthDate": "1990-04-05",
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_A}],
                },
            },
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333332",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p2",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "birthDate": "1964-08-12",
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_B}],
                },
            },
        ],
    }
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/multi_homonym.json": json.dumps(bundle),
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar,DOB\nAUR-101,Nolan Vermeer,{AAD_A},1990-04-05\n",
            "reg/beacon_hospital.csv": f"UHID,Patient Name,Aadhaar,DOB\nBCN-202,Nolan Vermeer,{AAD_B},1964-08-12\n",
        },
    )
    assert recs["fhir/multi_homonym.json#doc"] is None
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")


def test_F3_fhir_bundle_with_one_unnamed_conflicting_patient_abstains(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "id": "b-unnamed",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333333",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_A}],
                },
            },
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333334",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p2",
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_B}],
                },
            },
        ],
    }
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/multi_unnamed.json": json.dumps(bundle),
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-101,Nolan Vermeer,{AAD_A}\n",
            "reg/beacon_hospital.csv": f"UHID,Patient Name,Aadhaar\nBCN-202,Nolan Vermeer,{AAD_B}\n",
        },
    )
    assert recs["fhir/multi_unnamed.json#doc"] is None
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")


def test_F3_positive_fhir_bundle_with_duplicate_same_patient_still_links(tmp_path):
    """A Bundle containing a top-level Patient + contained copy of the SAME patient still links."""
    bundle = {
        "resourceType": "Bundle",
        "id": "b-same-pat",
        "type": "document",
        "entry": [
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333335",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "birthDate": "1990-04-05",
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_A}],
                },
            },
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333336",
                "resource": {
                    "resourceType": "Encounter",
                    "id": "e1",
                    "status": "finished",
                    "contained": [
                        {
                            "resourceType": "Patient",
                            "id": "p1-copy",
                            "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                            "birthDate": "1990-04-05",
                            "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_A}],
                        }
                    ],
                    "subject": {"reference": "urn:uuid:33333333-3333-4333-8333-333333333335"},
                },
            },
        ],
    }
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/same_pat.json": json.dumps(bundle),
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar,DOB\nAUR-101,Nolan Vermeer,{AAD_A},1990-04-05\n",
        },
    )
    assert _same(recs, "fhir/same_pat.json#doc", "reg/aurora_hospital.csv#row:0")


# =========================================================================== F4: Relative identifier ownership
def test_F4_fhir_related_person_narrative_never_leaks_to_patient(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "id": "b-rp-div",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:11111111-1111-4111-8111-111111111111",
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-1",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "gender": "male",
                },
            },
            {
                "fullUrl": "urn:uuid:22222222-2222-4222-8222-222222222222",
                "resource": {
                    "resourceType": "RelatedPerson",
                    "id": "rp-1",
                    "patient": {"reference": "urn:uuid:11111111-1111-4111-8111-111111111111"},
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "text": {
                        "status": "generated",
                        "div": f"<div>Nolan Vermeer, Aadhaar {AAD_A}, Mobile 9811122334</div>",
                    },
                },
            },
        ],
    }
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/child_bundle.json": json.dumps(bundle),
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-930,Nolan Vermeer,{AAD_A}\n",
        },
    )
    assert not _same(recs, "fhir/child_bundle.json#doc", "reg/aurora_hospital.csv#row:0")


@pytest.mark.parametrize(
    "sys_url,val,csv_col",
    [
        ("https://abdm.gov.in/abha", "nolan.vermeer@abdm", "ABHA Address"),
        ("https://incometax.gov.in/pan", PAN_A, "PAN"),
        ("https://example.org/id", AAD_A, "Aadhaar"),
    ],
)
def test_F4_fhir_related_person_identifier_abhaa_pan_and_unsystemed_aadhaar_veto(tmp_path, sys_url, val, csv_col):
    bundle = {
        "resourceType": "Bundle",
        "id": "b-rp-id",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:11111111-1111-4111-8111-111111111112",
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-2",
                    "name": [{"given": ["Nolan"], "family": "Vermeer"}],
                    "birthDate": "1990-04-05",
                },
            },
            {
                "fullUrl": "urn:uuid:22222222-2222-4222-8222-222222222223",
                "resource": {
                    "resourceType": "RelatedPerson",
                    "id": "rp-2",
                    "patient": {"reference": "urn:uuid:11111111-1111-4111-8111-111111111112"},
                    "name": [{"given": ["Gareth"], "family": "Vermeer"}],
                    "identifier": [{"system": sys_url, "value": val}],
                },
            },
        ],
    }
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/rp_id.json": json.dumps(bundle),
            "reg/aurora_hospital.csv": f"UHID,Patient Name,{csv_col},DOB\nAUR-931,Nolan Vermeer,{val},1990-04-05\n",
        },
    )
    assert not _same(recs, "fhir/rp_id.json#doc", "reg/aurora_hospital.csv#row:0")


def test_F4_emergency_contact_csv_and_json_identifiers_are_relative_owned(tmp_path):
    _, recs_csv = _run_link(
        tmp_path / "csv",
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,Emergency Contact Phone,Emergency Contact Aadhaar\n"
                f"AUR-602,Nolan Vermeer,9811122334,{AAD_A}\n"
            ),
            "reg/beacon_hospital.csv": f"MRN,Patient Name,Mobile,Aadhaar\nBCN-602,Nolan Vermeer,9811122334,{AAD_A}\n",
        },
    )
    assert not _same(recs_csv, "reg/aurora_hospital.csv#row:0", "reg/beacon_hospital.csv#row:0")

    _, recs_json = _run_link(
        tmp_path / "json",
        {
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-920,Nolan Vermeer,{AAD_A}\n",
            "opd/beacon_hospital.json": json.dumps(
                {
                    "hospital": "Beacon Hospital",
                    "visits": [
                        {
                            "uhid": "BCN-920",
                            "patient": "Nolan Vermeer",
                            "emergency_contact": {"name": "Nolan Vermeer", "aadhaar": AAD_A, "phone": "9811122334"},
                        }
                    ],
                }
            ),
        },
    )
    assert not _same(recs_json, "reg/aurora_hospital.csv#row:0", "opd/beacon_hospital.json#/visits/0")


@pytest.mark.parametrize(
    "note",
    [
        f"Patient: Nolan Vermeer. Husband: Nolan Vermeer, Aadhaar {AAD_A}. Cough.",
        f"Patient: Nolan Vermeer.\nFather: Nolan Vermeer\nAadhaar: {AAD_A}\nFever.",
        f"Patient: Nolan Vermeer. Attendant: Nolan Vermeer, Aadhaar {AAD_A}. OPD.",
        f"Patient: Nolan Vermeer. NOK Aadhaar: {AAD_A}. Stable.",
        f"Patient: Nolan Vermeer. Next of kin Aadhaar: {AAD_A}. Stable.",
        f"Patient: Nolan Vermeer. Emergency Contact Aadhaar: {AAD_A}. Stable.",
        f"Patient: Nolan Vermeer. Husband Nolan Kumar Vermeer from Sitapur district submitted Aadhaar {AAD_A}.",
        f"मरीज़: नोलन वरमीर, अभिभावक: नोलन वरमीर, आधार {AAD_A}, बुखार",
        f"मरीज़: नोलन वरमीर, बेटा का आधार {AAD_A}, खांसी",
        f"Patient: Nolan Vermeer. Bhai ka Aadhaar {AAD_A}. Fever.",
    ],
)
def test_F4_free_text_relative_cues_across_commas_newlines_and_hindi_hinglish(tmp_path, note):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-910,Nolan Vermeer,{AAD_A}\n",
            "notes/note.txt": note,
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "notes/note.txt#doc")


def test_F4_relative_notes_cannot_merge_wife_and_child_or_hijack_husbands_pseudonym(tmp_path):
    """Two relatives quoting husband/father Aadhaar after comma must NOT merge or steal his pseudonym."""
    _, recs_alone = _run_link(
        tmp_path / "alone",
        {
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-101,Nolan Vermeer,{AAD_A}\n",
        },
    )
    expected_husband_psn = recs_alone["reg/aurora_hospital.csv#row:0"]
    assert expected_husband_psn is not None

    _, recs = _run_link(
        tmp_path / "with_notes",
        {
            "reg/aurora_hospital.csv": f"UHID,Patient Name,Aadhaar\nAUR-101,Nolan Vermeer,{AAD_A}\n",
            "notes/a_wife.txt": f"Patient: Maren Vermeer. Husband: Nolan Vermeer, Aadhaar {AAD_A}. Fever.\n",
            "notes/b_child.txt": f"OPD visit. Father: Nolan Vermeer, Aadhaar {AAD_A}. Cough.\n",
        },
    )
    assert not _same(recs, "notes/a_wife.txt#doc", "notes/b_child.txt#doc")
    assert recs["reg/aurora_hospital.csv#row:0"] == expected_husband_psn


def test_F4_positive_family_name_column_and_explicit_patient_reset_still_link(tmp_path):
    """Guard against false positives: 'Family Name' surname column & 'Patient Aadhaar:' reset stay patient-owned."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": f"UHID,First Name,Family Name,Aadhaar\nAUR-101,Maren,Vermeer,{AAD_A}\n",
            "notes/n.txt": f"Patient: Maren Vermeer. Husband: Nolan Vermeer. Patient Aadhaar: {AAD_A}.",
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "notes/n.txt#doc")


# =========================================================================== F5: Per-record hospital attribution
@pytest.mark.parametrize("col", ["Facility Name", "Clinic", "Institution"])
def test_F5_multi_facility_csv_isolates_mrns_per_row(tmp_path, col):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/combined_export.csv": (
                f"{col},MRN,Patient Name\n"
                "Aurora Clinic,MRN-12345,Nolan Vermeer\n"
                "Beacon Clinic,MRN-12345,Nolan Vermeer\n"
            ),
        },
    )
    assert not _same(recs, "reg/combined_export.csv#row:0", "reg/combined_export.csv#row:1")


def test_F5_sparse_hospital_column_does_not_inherit_row0_hospital(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/combined_empty.csv": (
                "Hospital,MRN,Patient Name,Father Name,Village\n"
                "Aurora Hospital,MRN-12345,Nolan Vermeer,Gareth Vermeer,Keshavpur\n"
                ",MRN-12345,Nolan Vermeer,Dorian Vermeer,Rampur\n"
            ),
        },
    )
    assert not _same(recs, "reg/combined_empty.csv#row:0", "reg/combined_empty.csv#row:1")


def test_F5_positive_same_facility_across_rows_still_links(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/combined_same.csv": (
                "Facility Name,MRN,Patient Name,Complaint\n"
                "Aurora Clinic,MRN-12345,Nolan Vermeer,Fever\n"
                "Aurora Clinic,MRN-12345,Nolan Vermeer,Follow-up\n"
            ),
        },
    )
    assert _same(recs, "reg/combined_same.csv#row:0", "reg/combined_same.csv#row:1")


# =========================================================================== F6: Issue C re-registration independence
def test_F6_reregistration_does_not_double_count_dob_as_village_birth_year(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,DOB,Village\n"
                "AUR-26-000111,Nolan Vermeer,1990-04-05,Keshavpur\n"
                "AUR-26-000999,Nolan Vermeer,1990-04-05,Keshavpur\n"
            ),
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/aurora_hospital.csv#row:1")


def test_F6_reregistration_rejects_swapped_ambiguous_slash_dob(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,DOB,Mobile\n"
                "AUR-26-000111,Nolan Vermeer,03/04/1990,9811122334\n"
                "AUR-26-000999,Nolan Vermeer,04/03/1990,9811122334\n"
            ),
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/aurora_hospital.csv#row:1")


def test_F6_contradictory_abha_address_blocks_reregistration(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,DOB,Mobile,ABHA Address\n"
                "AUR-26-000111,Nolan Vermeer,1990-04-05,9811122334,nolan.one@abdm\n"
                "AUR-26-000999,Nolan Vermeer,1990-04-05,9811122334,nolan.two@abdm\n"
            ),
        },
    )
    assert not _same(recs, "reg/aurora_hospital.csv#row:0", "reg/aurora_hospital.csv#row:1")


def test_F6_distinct_same_prefix_uhids_across_generic_filenames_block_weak_merge(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/export_jan.csv": "UHID,Patient Name,Mobile\nKSR-26-000111,Nolan Vermeer,9811122334\n",
            "reg/export_feb.csv": "UHID,Patient Name,Mobile\nKSR-26-000999,Nolan Vermeer,9811122334\n",
        },
    )
    assert not _same(recs, "reg/export_jan.csv#row:0", "reg/export_feb.csv#row:0")


def test_F6_positive_reregistration_with_unambiguous_dob_and_phone_still_links(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora_hospital.csv": (
                "UHID,Patient Name,DOB,Mobile\n"
                "AUR-26-000111,Nolan Vermeer,1990-04-05,9811122334\n"
                "AUR-26-000999,Nolan Vermeer,05/04/1990,9811122334\n"
            ),
        },
    )
    assert _same(recs, "reg/aurora_hospital.csv#row:0", "reg/aurora_hospital.csv#row:1")


# =========================================================================== F7: Hospital normalisation
def test_F7_hospital_normalisation_distinguishes_branches_and_initials(tmp_path):
    h_dgh, _ = normalize_hospital("District General Hospital")
    h_km, _ = normalize_hospital("K. M. Hospital")
    h_rs, _ = normalize_hospital("R. S. Hospital")
    assert h_dgh is not None
    assert h_km is not None and h_rs is not None and h_km != h_rs

    _, recs = _run_link(
        tmp_path,
        {
            "reg/branch1.csv": (
                "Hospital,MRN,Patient Name,Father Name\n"
                '"City Hospital, Lucknow",MRN-12345,Nolan Vermeer,Gareth Vermeer\n'
            ),
            "reg/branch2.csv": (
                "Hospital,MRN,Patient Name,Father Name\n"
                '"City Hospital, Kanpur",MRN-12345,Nolan Vermeer,Dorian Vermeer\n'
            ),
        },
    )
    assert not _same(recs, "reg/branch1.csv#row:0", "reg/branch2.csv#row:0")


# =========================================================================== F8: Contract validation
def test_F8_contract_handles_nonstandard_json_extension_and_non_issued_psn_literal(tmp_path):
    summary_json, _ = _run_link(
        tmp_path / "dat",
        {
            "reg/aurora_hospital.dat": json.dumps(
                {
                    "hospital": "Aurora Hospital",
                    "patients": [
                        {"uhid": "AUR-101", "name": "Nolan Vermeer", "aadhaar": AAD_A},
                        {"uhid": "AUR-102", "name": "Caleb Mercer", "aadhaar": AAD_B},
                    ],
                }
            ),
        },
    )
    assert summary_json.ok, summary_json.problems

    summary_lit, _ = _run_link(
        tmp_path / "lit",
        {
            "notes/culture.txt": (
                "Clinical note: external sample batch PSN-7Q2K9D received for culture. Normal flora.\n"
            ),
        },
    )
    assert summary_lit.ok, summary_lit.problems


# =========================================================================== F9: Low-severity hardening
def test_F9_date_evidence_refuses_pickling_and_record_evidence_repr_omits_raw_loc():
    with pytest.raises(TypeError):
        pickle.dumps(DateEvidence((1990, 4, 5), None))

    ev = RecordEvidence(record=RecordKey("data.json", "/Nolan Vermeer/0"))
    assert "Nolan" not in repr(ev) and "Vermeer" not in repr(ev)


def test_F9_collision_telemetry_counts_same_canonical_key_rederivation():
    psn = Pseudonymizer(ReleaseSecret(TEST_SECRET.encode()), 180)
    c1 = ClusterProfile.from_record(
        RecordEvidence(RecordKey("a.csv", "row:0"), local_ids=frozenset({("unscoped", "MRN-100")}))
    )
    c2 = ClusterProfile.from_record(
        RecordEvidence(RecordKey("b.csv", "row:0"), local_ids=frozenset({("unscoped", "MRN-100")}))
    )
    stats = LinkingStats(records_total=2)
    mapping, _ = assign_pseudonyms([c1, c2], psn, stats)
    assert len(set(mapping.values())) == 2
    assert stats.pseudonym_collisions_resolved >= 1


# =========================================================================== NEW-1: Structured relative ownership
def test_NEW1_emergency_contact_split_name_and_guardian_demographics_do_not_leak_into_patient(tmp_path):
    """Emergency contact split names and guardian/parent demographics must never become patient evidence."""
    _, recs = _run_link(
        tmp_path,
        {
            "visits/child_visit.json": json.dumps(
                {
                    "hospital": "Aurora Hospital",
                    "visits": [
                        {
                            "uhid": "AUR-801",
                            "patient_name": "Nolan Vermeer",
                            "phone": "9811122334",
                            "emergency_contact": {
                                "first_name": "Dorian",
                                "last_name": "Vermeer",
                                "phone": "9811122334",
                            },
                            "guardian": {
                                "name": "Dorian Vermeer",
                                "dob": "1964-08-19",
                                "age": "61",
                                "gender": "M",
                                "aadhaar": AAD_C,
                            },
                        },
                        {
                            "uhid": "AUR-802",
                            "patient_name": "Dorian Vermeer",
                            "dob": "1964-08-19",
                            "age": "61",
                            "gender": "M",
                            "phone": "9811122334",
                        },
                        {
                            "uhid": "AUR-803",
                            "patient_name": "Nolan Vermeer",
                            "dob": "2018-05-12",
                            "age": "7",
                            "gender": "M",
                            "aadhaar": AAD_A,
                        },
                        {
                            "uhid": "AUR-804",
                            "patient_name": "Nolan Vermeer",
                            "aadhaar": AAD_A,
                            "guardian": {
                                "name": "Elena Vermeer",
                                "dob": "1988-11-03",
                                "age": "37",
                                "gender": "F",
                            },
                        },
                    ],
                }
            ),
        },
    )
    # Child visit (AUR-801) must NOT merge with relative Dorian Vermeer (AUR-802)
    assert not _same(recs, "visits/child_visit.json#/visits/0", "visits/child_visit.json#/visits/1")
    # Two visits of child Nolan Vermeer sharing Aadhaar AAD_A must merge despite guardian female/age-37 fields
    assert _same(recs, "visits/child_visit.json#/visits/2", "visits/child_visit.json#/visits/3")


def test_NEW1_tabular_parent_dob_age_village_pin_stay_off_patient_while_patient_fields_work(tmp_path):
    """Tabular Father DOB / Mother Age / Guardian Village / Guardian PIN must not pollute patient profile."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/pediatric.csv": (
                "UHID,First Name,Family Name,DOB,Age,Sex,Father Name,Father DOB,Mother Age,"
                "Guardian Village,Guardian PIN,Village,PIN,Phone,Emergency Admission No\n"
                "PED-101,Nolan,Vermeer,2016-03-14,9,M,Dorian Vermeer,1982-07-21,39,"
                "Rampur,221001,Keshavpur,110001,9811122334,ADM-9001\n"
                "PED-102,Nolan,Vermeer,2016-03-14,9,M,Dorian Vermeer,1982-07-21,39,"
                "Rampur,221001,Keshavpur,110001,9811122334,ADM-9002\n"
                "PED-103,Dorian,Vermeer,1982-07-21,43,M,Harlan Vermeer,,,"
                ",,Rampur,221001,9811122334,ADM-9003\n"
            ),
        },
    )
    # Same child across two admissions (with patient DOB 2016-03-14 + phone + father name) links
    assert _same(recs, "reg/pediatric.csv#row:0", "reg/pediatric.csv#row:1")
    # Father's own admission (PED-103, DOB 1982-07-21) never merges with child
    assert not _same(recs, "reg/pediatric.csv#row:0", "reg/pediatric.csv#row:2")


# =========================================================================== NEW-2: Free-text & encoded relative cues
@pytest.mark.parametrize(
    ("note_body",),
    [
        ("Father: Mr. Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Mother: Mrs. Elira Thorne, Aadhaar: " + AAD_B,),
        ("Sister: Ms. Clara Thorne, Aadhaar: " + AAD_B,),
        ("Husband: Dr. Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Uncle: Prof. Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Mother: Smt. Elira Thorne, Aadhaar: " + AAD_B,),
        ("Father: Sri. Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Guardian: Sh. G. Thorne, Aadhaar: " + AAD_B,),
        ("Father of patient: Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Husband of the patient: Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Guardian of patient: Dorian Thorne, PAN: " + PAN_B,),
        ("Attendant for pt: Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Patient's husband: Dorian Thorne, Aadhaar: " + AAD_B,),
        ("Patient ke pati: Mr. Dorian Thorne, Aadhaar: " + AAD_B,),
        ("मरीज़ के पति: डोरियन थॉर्न, आधार: " + AAD_B,),
        ("रोगी के पिता श्री. डोरियन थॉर्न का आधार " + AAD_B,),
    ],
)
def test_NEW2_dotted_titles_initials_and_relational_patient_phrases_keep_relative_id_off_patient(tmp_path, note_body):
    _, recs = _run_link(
        tmp_path,
        {
            "notes/patient_a.txt": (f"Aurora Hospital\nPatient: Clara Thorne\nDOB: 1993-04-15\n{note_body}\n"),
            "notes/relative_record.txt": (
                f"Meridian Hospital\nAadhaar: {AAD_B}\nPAN: {PAN_B}\nDiagnosis: Essential hypertension\n"
            ),
        },
    )
    assert not _same(recs, "notes/patient_a.txt#doc", "notes/relative_record.txt#doc")


def test_NEW2_xhtml_and_html_entity_encoded_relative_cues_do_not_falsely_merge_patients(tmp_path):
    """Tag-heavy XHTML (>120 raw chars) and HTML-entity Devanagari kinship cues must attribute to relative."""
    xhtml_div = (
        "<div xmlns='http://www.w3.org/1999/xhtml'>"
        "<p><span class='clinical-label' data-field='rel'>Father:</span> "
        "<span class='person-title' data-honorific='mr'>Mr. Dorian Thorne</span>, "
        "<span class='id-type' data-system='uidai-aadhaar'>Aadhaar:</span> "
        f"<span class='id-val'>{AAD_B}</span></p></div>"
    )
    # "पति का आधार " in numeric HTML entities
    entity_hindi = "&#x092A;&#x0924;&#x093F; &#x0915;&#x093E; &#x0906;&#x0927;&#x093E;&#x0930;: " + AAD_C
    _, recs = _run_link(
        tmp_path,
        {
            "fhir/enc_a.json": json.dumps(
                {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "Patient",
                                "id": "p1",
                                "name": [{"text": "Clara Thorne"}],
                                "birthDate": "1993-04-15",
                            }
                        },
                        {
                            "resource": {
                                "resourceType": "Encounter",
                                "id": "e1",
                                "text": {"status": "generated", "div": xhtml_div},
                            }
                        },
                    ],
                }
            ),
            "notes/father_claim.txt": f"Meridian Hospital\nAadhaar: {AAD_B}\nDiagnosis: Cataract\n",
            "notes/ent_a.txt": f"Aurora Hospital\nPatient: Clara Mercer\n{entity_hindi}\n",
            "notes/husband_claim.txt": f"Meridian Hospital\nAadhaar: {AAD_C}\nDiagnosis: Asthma\n",
        },
    )
    assert not _same(recs, "fhir/enc_a.json#doc", "notes/father_claim.txt#doc")
    assert not _same(recs, "notes/ent_a.txt#doc", "notes/husband_claim.txt#doc")


def test_NEW2_positive_patient_reset_after_relative_with_title_still_links_patient(tmp_path):
    """Explicit 'Patient Aadhaar:' after a titled relative mention must still link the patient."""
    _, recs = _run_link(
        tmp_path,
        {
            "notes/p1.txt": (
                "Aurora Hospital\nPatient: Clara Mercer\nFather: Mr. Dorian Thorne. Patient Aadhaar: " + AAD_A + "\n"
            ),
            "notes/p2.txt": ("Meridian Hospital\nPatient: Clara Mercer\nAadhaar: " + AAD_A + "\n"),
        },
    )
    assert _same(recs, "notes/p1.txt#doc", "notes/p2.txt#doc")


# =========================================================================== NEW-3: External-lab & generic MRN
def test_NEW3_two_different_external_labs_with_same_generic_mrn_do_not_merge(tmp_path):
    """Two distinct external pathology labs sharing a generic MRN must not merge without a shared hospital."""
    _, recs = _run_link(
        tmp_path,
        {
            "lab/city_lab.txt": ("City Pathology Lab\nPatient: Nolan Vermeer\nMRN: MRN-12345\nHbA1c: 5.7%\n"),
            "lab/horizon_lab.txt": (
                "Horizon Diagnostics Lab\nPatient: Nolan Vermeer\nMRN: MRN-12345\nTSH: 2.4 mIU/L\n"
            ),
        },
    )
    assert not _same(recs, "lab/city_lab.txt#doc", "lab/horizon_lab.txt#doc")


def test_NEW3_nameless_external_lab_abstains_when_multiple_conflicting_hospitals_share_mrn(tmp_path):
    """Nameless external lab with generic MRN-12345 must abstain when two conflicting hospitals have MRN-12345."""
    _, recs = _run_link(
        tmp_path,
        {
            "hospitals/halcyon.csv": (
                "Facility,MRN,Patient Name,DOB\nHalcyon Hospital,MRN-12345,Dorian Thorne,1980-02-14\n"
            ),
            "hospitals/meridian.csv": (
                "Facility,MRN,Patient Name,DOB\nMeridian Hospital,MRN-12345,Caleb Mercer,1992-11-08\n"
            ),
            "lab/specimen.txt": ("Central Pathology Lab\nMRN: MRN-12345\nSerum Creatinine: 0.9 mg/dL\n"),
        },
    )
    assert not _same(recs, "hospitals/halcyon.csv#row:0", "hospitals/meridian.csv#row:0")
    assert not _same(recs, "lab/specimen.txt#doc", "hospitals/halcyon.csv#row:0")
    assert not _same(recs, "lab/specimen.txt#doc", "hospitals/meridian.csv#row:0")


def test_NEW3_nameless_external_lab_links_when_single_unambiguous_hospital_matches_mrn(tmp_path):
    """Positive control: nameless external lab links to the sole hospital record carrying that MRN."""
    _, recs = _run_link(
        tmp_path,
        {
            "hospitals/halcyon.csv": (
                "Facility,MRN,Patient Name,DOB\nHalcyon Hospital,MRN-54321,Dorian Thorne,1980-02-14\n"
            ),
            "lab/specimen.txt": ("Central Pathology Lab\nMRN: MRN-54321\nSerum Creatinine: 0.9 mg/dL\n"),
        },
    )
    assert _same(recs, "hospitals/halcyon.csv#row:0", "lab/specimen.txt#doc")


def test_NEW3_different_hospital_subdirectories_with_same_filename_do_not_merge_on_generic_mrn(tmp_path):
    """Two different hospital directories with identical generic filenames must not share MRN scope."""
    _, recs = _run_link(
        tmp_path,
        {
            "halcyon_hospital/ward_register.csv": ("MRN,Patient Name\nMRN-12345,Nolan Vermeer\n"),
            "meridian_hospital/ward_register.csv": ("MRN,Patient Name\nMRN-12345,Nolan Vermeer\n"),
            "halcyon_hospital/discharge_register.csv": ("MRN,Patient Name\nMRN-12345,Nolan Vermeer\n"),
            "dir_alpha/ward_register.csv": ("MRN,Patient Name\nMRN-77777,Caleb Mercer\n"),
            "dir_beta/ward_register.csv": ("MRN,Patient Name\nMRN-77777,Caleb Mercer\n"),
        },
    )
    assert not _same(recs, "halcyon_hospital/ward_register.csv#row:0", "meridian_hospital/ward_register.csv#row:0")
    assert _same(recs, "halcyon_hospital/ward_register.csv#row:0", "halcyon_hospital/discharge_register.csv#row:0")
    assert not _same(recs, "dir_alpha/ward_register.csv#row:0", "dir_beta/ward_register.csv#row:0")


def test_NEW3_same_lab_with_reliable_hospital_anchor_and_prefixed_uhids_still_link(tmp_path):
    """Positive controls: external lab records link when anchored to a reliable hospital or prefixed UHID."""
    _, recs = _run_link(
        tmp_path,
        {
            "hospitals/halcyon.csv": ("Facility,MRN,Patient Name\nHalcyon Hospital,MRN-65432,Nolan Vermeer\n"),
            "lab/city_lab_1.txt": ("City Pathology Lab\nPatient: Nolan Vermeer\nMRN: MRN-65432\nHbA1c: 5.8%\n"),
            "lab/city_lab_2.txt": (
                "City Pathology Lab\nPatient: Nolan Vermeer\nMRN: MRN-65432\nFasting Glucose: 102 mg/dL\n"
            ),
            "exports/jan_batch.csv": ("UHID,Patient Name\nHLC-2026-00987,Caleb Mercer\n"),
            "exports/feb_batch.csv": ("UHID,Patient Name\nHLC-2026-00987,Caleb Mercer\n"),
        },
    )
    assert _same(recs, "hospitals/halcyon.csv#row:0", "lab/city_lab_1.txt#doc")
    assert _same(recs, "hospitals/halcyon.csv#row:0", "lab/city_lab_2.txt#doc")
    assert _same(recs, "exports/jan_batch.csv#row:0", "exports/feb_batch.csv#row:0")


# =========================================================================== NEW-4: Phonetic matching hardening
@pytest.mark.parametrize(
    ("name_a", "name_b"),
    [
        ("Kiran Solanki", "Karan Solanki"),
        ("Alok Solanki", "Alka Solanki"),
        ("Sunil Solanki", "Sonal Solanki"),
        ("Anil Kumar Solanki", "Anil Prakash Solanki"),
    ],
)
def test_NEW4_distinct_indian_given_or_middle_names_veto_shared_aadhaar_and_mrn(tmp_path, name_a, name_b):
    """Distinct given names (Kiran/Karan, Alok/Alka, Sunil/Sonal) and conflicting middle names must veto merges."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/patients.csv": (
                "Facility,MRN,Patient Name,Aadhaar\n"
                f"Aurora Hospital,MRN-90100,{name_a},{AAD_A}\n"
                f"Aurora Hospital,MRN-90100,{name_b},{AAD_A}\n"
            ),
        },
    )
    assert not _same(recs, "reg/patients.csv#row:0", "reg/patients.csv#row:1")


def test_NEW4_positive_controls_transliteration_schwa_omission_and_middle_name_omission_still_link(tmp_path):
    """Legitimate transliteration, schwa, 1-char vowel omission under strong ID, and middle-name omission link."""
    _, recs = _run_link(
        tmp_path,
        {
            "reg/aurora.csv": (
                "Facility,MRN,Patient Name,Aadhaar,Phone\n"
                f"Aurora Hospital,AUR-501,Zarina Qureshi,{AAD_A},9811122334\n"
                f"Aurora Hospital,AUR-501,Zarna Qureshi,{AAD_A},9811122334\n"
                f"Aurora Hospital,AUR-502,Kamlesh Pande,{AAD_B},9822233445\n"
                f"Aurora Hospital,AUR-502,Kamalesh Pandeya,{AAD_B},9822233445\n"
                f"Aurora Hospital,AUR-503,Anil Solanki,{AAD_C},9833344556\n"
                f"Aurora Hospital,AUR-503,Anil Kumar Solanki,{AAD_C},9833344556\n"
                f"Aurora Hospital,AUR-504,प्रणव कुलकर्णी,{AAD_D},9844455667\n"
                f"Aurora Hospital,AUR-504,Pranav Kulkarni,{AAD_D},9844455667\n"
                "Aurora Hospital,AUR-505,N. Vermeer,,9855566778\n"
                "Aurora Hospital,AUR-505,Nolan Vermeer,,9855566778\n"
            ),
        },
    )
    assert _same(recs, "reg/aurora.csv#row:0", "reg/aurora.csv#row:1")
    assert _same(recs, "reg/aurora.csv#row:2", "reg/aurora.csv#row:3")
    assert _same(recs, "reg/aurora.csv#row:4", "reg/aurora.csv#row:5")
    assert _same(recs, "reg/aurora.csv#row:6", "reg/aurora.csv#row:7")
    assert _same(recs, "reg/aurora.csv#row:8", "reg/aurora.csv#row:9")
