"""Phase 3.1: false-merge regressions from the independent Phase 3 audit (R1-R7), plus positives.

Every negative case below merged two different people at ``32fe8fc``. Each one is paired with
a positive counterpart, so precision is not bought by refusing all linking. All names, IDs,
hospitals and phone numbers are invented.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from clinveil.config.policy import Policy
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.pipeline import run
from clinveil.security.secrets import ReleaseSecret
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_FATHER = _aadhaar("27364519082")
AAD_HUSBAND = _aadhaar("38475620193")
AAD_ARVEL = _aadhaar("49586731204")
AAD_OTHER = _aadhaar("51697842315")


def _link(tmp_path: Path, files: dict[str, str]) -> dict[str, str | None]:
    """Run the real pipeline; return ``"<input rel>#<loc>" -> pseudonym | None``."""
    inp = tmp_path / "in"
    for rel, content in files.items():
        p = inp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    out = tmp_path / "out"
    summary = run(inp, out, ReleaseSecret(TEST_SECRET.encode()), Policy())
    assert summary.ok, summary.problems
    rep = json.loads((out / "report.json").read_text())
    sha_to_in = {hashlib.sha256(c.encode("utf-8")).hexdigest(): rel for rel, c in files.items()}
    out_to_in = {e["output"]: sha_to_in[e["input_sha256"]] for e in rep["files"] if e.get("output")}
    recs = {}
    for line in (out / "records.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[f"{out_to_in.get(r['file'], r['file'])}#{r['loc']}"] = r["patient"]
    return recs


def _same(recs: dict[str, str | None], a: str, b: str) -> bool:
    return recs[a] is not None and recs[a] == recs[b]


# =========================================================================== R1: relative-owned identifiers
@pytest.mark.parametrize(
    "header",
    ["Father Aadhaar", "Father's Aadhaar No", "Mother Aadhaar", "Guardian Aadhaar", "पिता आधार", "Parent UID"],
)
def test_R1_siblings_sharing_a_parent_identifier_column_are_not_merged(tmp_path, header):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,{header}\n"
            f"KSR-26-000111,Arvel Dunmore,{AAD_FATHER}\nKSR-26-000222,Tavin Dunmore,{AAD_FATHER}\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/kesari_hospital.csv#row:1")


def test_R1_siblings_across_two_hospitals_sharing_a_parent_identifier(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Father Aadhaar\nKSR-26-000111,Arvel Dunmore,{AAD_FATHER}\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Father Aadhaar\nBHR-700, Tavin Dunmore,{AAD_FATHER}\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


@pytest.mark.parametrize(
    "note",
    [
        f"Patient: Sunila Dunmore W/o Arvel Dunmore. Husband's Aadhaar {AAD_HUSBAND}. C/O fever x 3 days.",
        f"Patient: Sunila Dunmore. Aadhaar of husband: {AAD_HUSBAND}. Seen in OPD.",
        f"मरीज़: सुनीला डनमोर, पति का आधार {AAD_HUSBAND}, बुखार",
        f"Name: Sunila Dunmore W/o Arvel Dunmore Aadhaar {AAD_HUSBAND} OPD visit",  # ambiguous owner: never patient's
    ],
)
def test_R2_spouse_note_citing_the_other_spouses_identifier_is_not_merged(tmp_path, note):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Aadhaar\nKSR-26-000333,Arvel Dunmore,{AAD_HUSBAND}\n",
            "notes/opd_note.txt": note,
        },
    )
    assert not _same(recs, "notes/opd_note.txt#doc", "reg/kesari_hospital.csv#row:0")


def test_R2_json_relationship_key_identifier_is_relative_owned(tmp_path):
    visits = {
        "hospital": "Kesari Hospital",
        "visits": [
            {
                "uhid": "KSR-26-000501",
                "patient": "Arvel Dunmore",
                "guardian": {"name": "Kelvar Dunmore", "aadhaar": AAD_FATHER},
            },
            {
                "uhid": "KSR-26-000502",
                "patient": "Tavin Dunmore",
                "guardian": {"name": "Kelvar Dunmore", "aadhaar": AAD_FATHER},
            },
        ],
    }
    recs = _link(tmp_path, {"opd/kesari_opd.json": json.dumps(visits)})
    assert not _same(recs, "opd/kesari_opd.json#/visits/0", "opd/kesari_opd.json#/visits/1")


def test_R2_fhir_related_person_identifier_never_becomes_the_patients(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "id": "b",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:p",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p",
                    "name": [{"text": "Sunila Dunmore"}],
                    "gender": "female",
                },
            },
            {
                "fullUrl": "urn:uuid:rp",
                "resource": {
                    "resourceType": "RelatedPerson",
                    "id": "rp",
                    "patient": {"reference": "urn:uuid:p"},
                    "name": [{"text": "Arvel Dunmore"}],
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_HUSBAND}],
                },
            },
        ],
    }
    recs = _link(
        tmp_path,
        {
            "fhir/sunila.json": json.dumps(bundle),
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Aadhaar\nKSR-26-000333,Arvel Dunmore,{AAD_HUSBAND}\n",
        },
    )
    assert not _same(recs, "fhir/sunila.json#doc", "reg/kesari_hospital.csv#row:0")


def test_R1_R2_positive_patient_owned_identifiers_still_link(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,Aadhaar,Father Name\n"
            f"KSR-26-000601,Arvel Dunmore,{AAD_ARVEL},Kelvar Dunmore\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Aadhaar No\nBHR-26-900,Arvel Dunmore,{AAD_ARVEL}\n",
            "notes/c.txt": f"Name: Arvel Dunmore S/o Kelvar Dunmore, Aadhaar {AAD_ARVEL}. C/O fever x 2 days.",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "notes/c.txt#doc")


# =========================================================================== R3: household / family-level identifiers
@pytest.mark.parametrize(
    "col, value",
    [("ESIC No", "ESIC 1234567890"), ("Email", "dunmore.family@example.com"), ("PMJAY ID", "PMJAY-UP-123456789")],
)
def test_R3_family_members_sharing_a_household_identifier_are_not_merged(tmp_path, col, value):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,{col}\nKSR-002,Arvel Dunmore,{value}\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,{col}\nBHR-002,Tavin Dunmore,{value}\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


def test_R3_different_patients_sharing_email_and_address_are_not_merged(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,Email,Village\n"
            "KSR-003,Arvel Dunmore,home@example.com,Bhatpurwa\n",
            "reg/bharat_hospital.csv": "MRN,Patient Name,Email,Village\n"
            "BHR-003,Sunila Kelkar,home@example.com,Bhatpurwa\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


def test_R3_positive_shared_policy_plus_same_full_name_still_links(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,ESIC No\nKSR-004,Arvel Dunmore,ESIC 1234567890\n",
            "reg/bharat_hospital.csv": "MRN,Patient Name,ESIC No\nBHR-004,Arvel Dunmore,ESIC 1234567890\n",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


# =========================================================================== R4: given-name conflicts under a strong ID
def test_R4_same_surname_different_given_names_with_one_shared_aadhaar_do_not_merge(tmp_path):
    # Controlled conflict: both rows claim the same patient-owned Aadhaar (a data-entry error).
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Aadhaar\nKSR-005,Arvel Dunmore,{AAD_ARVEL}\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Aadhaar\nBHR-005,Tavin Dunmore,{AAD_ARVEL}\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


def test_R4_identical_full_names_with_conflicting_aadhaar_do_not_merge(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,Aadhaar,Mobile\n"
            f"KSR-006,Arvel Dunmore,{AAD_ARVEL},9876500111\n",
            "reg/bharat_hospital.csv": "MRN,Patient Name,Aadhaar,Mobile\n"
            f"BHR-006,Arvel Dunmore,{AAD_OTHER},9876500111\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


@pytest.mark.parametrize(
    "other_name",
    [
        "Arvell Dunmore",
        "Dunmore Arvel",
        "A. Dunmore",
        "आरवेल डनमोर",
        "Dunmore",
    ],  # variant, order, initial, script, missing given
)
def test_R4_positive_name_variants_with_the_same_aadhaar_still_link(tmp_path, other_name):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Aadhaar\nKSR-007,Arvel Dunmore,{AAD_ARVEL}\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Aadhaar\nBHR-007,{other_name},{AAD_ARVEL}\n",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


# =========================================================================== R5: prefixed MRNs across hospitals
@pytest.mark.parametrize("mrn", ["UH-2026-00451", "GH/26/00451", "DH-00451", "SVH-2026-00451"])
def test_R5_same_prefixed_mrn_at_two_known_hospitals_is_not_evidence(tmp_path, mrn):
    recs = _link(
        tmp_path,
        {
            "reg/apex_hospital.csv": f"MRN,Patient Name,Age\n{mrn},Arvel Dunmore,30\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Age\n{mrn},Arvel Dunmore,31\n",
        },
    )
    assert not _same(recs, "reg/apex_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


def test_R5_positive_external_lab_citing_a_hospital_prefixed_mrn_still_links(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/apex_hospital.csv": "MRN,Patient Name\nAPX-2026-00451,Arvel Dunmore\n",
            "lab/city_pathology_lab.json": json.dumps(
                {
                    "lab": "City Pathology Lab",
                    "patient": {"name": "Arvel Dunmore", "ref_mrn": "APX-2026-00451"},
                    "panels": [{"test": "Hb", "value": "11.2"}],
                }
            ),
        },
    )
    assert _same(recs, "reg/apex_hospital.csv#row:0", "lab/city_pathology_lab.json#doc")


# =========================================================================== R6: identifier types and digit cores
@pytest.mark.parametrize("other", ["IPD/26/0045123", "OPD-0045123", "ADM 2026 0045123", "VISIT-0045123"])
def test_R6_admission_or_visit_number_never_matches_a_uhid_by_digit_core(tmp_path, other):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name\nUHID-0045123,Arvel Dunmore\nUHID-0099999,Tavin Kelkar\n",
            "lab/kesari_hospital_lab.json": json.dumps(
                {"facility": "Kesari Hospital", "ref_no": other, "test": "Hb", "result": "11.2"}
            ),
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "lab/kesari_hospital_lab.json#doc")


def test_R6_positive_same_uhid_with_different_separators_still_links(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name\nUHID-0045123,Arvel Dunmore\n",
            "opd/kesari_hospital_opd.csv": "UHID,Patient Name,Complaint\nUHID/0045123,Arvel Dunmore,fever\n",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "opd/kesari_hospital_opd.csv#row:0")


# ===================================================== R7: distinct authoritative MRNs, same hospital
def test_R7_two_distinct_uhids_from_one_hospital_block_a_weak_name_merge(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,Mobile\nKSR-26-000111,Arvel Dunmore,9876500222\n"
            "KSR-26-000999,Arvel Dunmore,9876500222\n",
        },
    )
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "reg/kesari_hospital.csv#row:1")


def test_R7_positive_one_mrn_with_several_admission_numbers_still_links(tmp_path):
    recs = _link(
        tmp_path,
        {
            "ipd/kesari_hospital_ipd.csv": "UHID,IPD No,Patient Name,Diagnosis\n"
            "KSR-26-000777,IPD/26/0101,Arvel Dunmore,Typhoid\nKSR-26-000777,IPD/26/0388,Arvel Dunmore,Malaria\n",
        },
    )
    assert _same(recs, "ipd/kesari_hospital_ipd.csv#row:0", "ipd/kesari_hospital_ipd.csv#row:1")


def test_R7_positive_different_hospital_mrns_linked_by_patient_aadhaar(tmp_path):
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": f"UHID,Patient Name,Aadhaar\nKSR-26-000888,Arvel Dunmore,{AAD_ARVEL}\n",
            "reg/bharat_hospital.csv": f"MRN,Patient Name,Aadhaar\nBHR-26-123456,Arvel Dunmore,{AAD_ARVEL}\n",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")


# =========================================================================== cluster-level consistency
def test_weak_bridge_cannot_join_a_conflicting_record_through_a_strong_cluster(tmp_path):
    """A~B strongly (shared Aadhaar), B~C weakly (name + phone), A and C conflict (age 30 vs 36)."""
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,Aadhaar,Age,Mobile\n"
            f"KSR-1,Arvel Dunmore,{AAD_ARVEL},30,9876500333\n",
            "reg/bharat_hospital.csv": "MRN,Patient Name,Aadhaar,Age,Mobile\n"
            f"BHR-1,Arvel Dunmore,{AAD_ARVEL},33,9876500333\n",
            "notes/c.txt": "Patient: Arvel Dunmore, Age 36 yrs, Mob 9876500333. Review.",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/bharat_hospital.csv#row:0")
    assert not _same(recs, "reg/kesari_hospital.csv#row:0", "notes/c.txt#doc")


def test_capped_homonym_name_block_abstains_instead_of_linking_through_phone_blocks(tmp_path):
    # 70 different people share one full name (> the 64 name-block cap); pairs also share a phone.
    rows = "".join(f"Arvel Dunmore,{9876510000 + i // 2}\n" for i in range(70))
    recs = _link(tmp_path, {"reg/camp.csv": "Patient Name,Mobile\n" + rows})
    assert not any(recs[f"reg/camp.csv#row:{i}"] for i in range(70))


def test_R7_positive_documented_reregistration_with_dob_and_phone_still_links(tmp_path):
    """DATASET.md: "some re-register at the same hospital with a new ID: the same person"."""
    recs = _link(
        tmp_path,
        {
            "reg/kesari_hospital.csv": "UHID,Patient Name,DOB,Mobile\n"
            "KSR-26-000111,Arvel Dunmore,1990-02-03,9876500222\n"
            "KSR-26-000999,Arvel Dunmore,1990-02-03,9876500222\n",
        },
    )
    assert _same(recs, "reg/kesari_hospital.csv#row:0", "reg/kesari_hospital.csv#row:1")


def test_R5_positive_third_party_record_quoting_an_issuer_prefixed_uhid_still_links(tmp_path):
    """File names without a hospital word are not proof of two different issuers."""
    recs = _link(
        tmp_path,
        {
            "reg/master.csv": "UHID,Patient Name\nKSR-26-004417,Arvel Dunmore\n",
            "notes/discharge_summary.txt": "Discharge summary. UHID KSR-26-004417. Stable, discharged.",
        },
    )
    assert _same(recs, "reg/master.csv#row:0", "notes/discharge_summary.txt#doc")


# =========================================================================== per-record output validation
def _release(tmp_path: Path, csv_text: str, records: list[dict]) -> Path:
    out = tmp_path / "rel"
    (out / "sanitized" / "reg").mkdir(parents=True)
    (out / "sanitized/reg/a.csv").write_text(csv_text)
    (out / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    linked = sum(1 for r in records if r["patient"])
    (out / "report.json").write_text(
        json.dumps(
            {
                "files": [{"input_sha256": "x" * 64, "output": "sanitized/reg/a.csv", "status": "sanitized"}],
                "counts": {"records_linked": linked},
            }
        )
    )
    return out


def test_contract_rejects_a_pseudonym_that_is_only_elsewhere_in_the_file(tmp_path):
    from clinveil.validation.contract import check_release

    csv_text = "UHID,Patient Name\nPSN-AAAAAA,[NAME]\n[MRN],[NAME]\n"
    out = _release(
        tmp_path,
        csv_text,
        [
            {"file": "sanitized/reg/a.csv", "loc": "row:0", "patient": "PSN-AAAAAA"},
            {"file": "sanitized/reg/a.csv", "loc": "row:1", "patient": "PSN-AAAAAA"},  # claimed, but not in row 1
        ],
    )
    problems = check_release(out, ["x" * 64])
    assert "1 linked records do not contain their own pseudonym" in problems


def test_contract_rejects_an_inherited_or_foreign_pseudonym(tmp_path):
    from clinveil.validation.contract import check_release

    csv_text = "UHID,Patient Name\nPSN-AAAAAA,[NAME]\nPSN-BBBBBB,[NAME]\n"
    out = _release(
        tmp_path,
        csv_text,
        [
            {"file": "sanitized/reg/a.csv", "loc": "row:0", "patient": "PSN-AAAAAA"},
            {"file": "sanitized/reg/a.csv", "loc": "row:1", "patient": None},  # unlinked, yet carries a pseudonym
        ],
    )
    assert "1 records contain another patient's pseudonym" in check_release(out, ["x" * 64])


def test_contract_accepts_correct_per_record_placement(tmp_path):
    from clinveil.validation.contract import check_release

    csv_text = "UHID,Patient Name\nPSN-AAAAAA,[NAME]\nPSN-AAAAAA,[NAME]\n[MRN],[NAME]\n"
    out = _release(
        tmp_path,
        csv_text,
        [
            {"file": "sanitized/reg/a.csv", "loc": "row:0", "patient": "PSN-AAAAAA"},
            {"file": "sanitized/reg/a.csv", "loc": "row:1", "patient": "PSN-AAAAAA"},
            {"file": "sanitized/reg/a.csv", "loc": "row:2", "patient": None},
        ],
    )
    assert not [p for p in check_release(out, ["x" * 64]) if "pseudonym" in p or "locat" in p]
