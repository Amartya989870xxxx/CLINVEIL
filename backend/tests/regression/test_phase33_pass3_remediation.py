"""Phase 3.3 Pass 3: regression tests for the Carbon Phase 3.3 audit findings P33-F1 .. P33-F5.

Every name, identifier, phone number, date and facility below is newly invented for these tests
(no organiser practice identity, canary or hidden-evaluation value).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from clinveil.config.policy import Policy
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.ingestion.limits import IngestLimits
from clinveil.linking.cluster import MAX_COMPONENT, cluster_records
from clinveil.linking.matcher import _names_phonetically_compatible
from clinveil.linking.models import NameGrade, RecordEvidence, RecordKey
from clinveil.linking.normalize import build_name_evidence, compare_names, strict_name_token
from clinveil.pipeline import _pass1_collect, run
from clinveil.security.secrets import ReleaseSecret
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_1 = _aadhaar("51738264093")
AAD_2 = _aadhaar("62849375104")


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _run_link(tmp_path: Path, files: dict[str, str]) -> dict[str, str | None]:
    """Run the full pipeline; map ``<input rel>#<loc>`` -> pseudonym."""
    inp, out = _write(tmp_path / "in", files), tmp_path / "out"
    summary = run(inp, out, ReleaseSecret(TEST_SECRET.encode()), Policy())
    assert summary.ok, summary.problems
    recs: dict[str, str | None] = {}
    for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[f"{r['file'].removeprefix('sanitized/')}#{r['loc']}"] = r["patient"]
    return recs


def _same(recs: dict[str, str | None], a: str, b: str) -> bool:
    return recs[a] is not None and recs[a] == recs[b]


def _evidence(tmp_path: Path, files: dict[str, str]) -> dict[str, RecordEvidence]:
    root = _write(tmp_path / "ev", files)
    pol = Policy()
    _, evs = _pass1_collect(root, pol, IngestLimits.from_policy(pol))
    return {f"{e.record.file_rel}#{e.record.loc}": e for e in evs}


def _name(raw: str):
    return build_name_evidence(raw, confidence=0.9, source="test")


def _rec(key: str, *, name: str | None = None, **kw) -> RecordEvidence:
    if name is not None:
        kw["patient_names"] = (_name(name),)
    return RecordEvidence(record=RecordKey(key, "doc"), **kw)


def _partition(evs: list[RecordEvidence]) -> list[list[str]]:
    clusters, _ = cluster_records(evs)
    return sorted(sorted(m.file_rel for m in c.members) for c in clusters)


def _together(part: list[list[str]], a: str, b: str) -> bool:
    return any(a in grp and b in grp for grp in part)


# =========================================================================== P33-F1: weak-MRN group homonym vetoes
_OPD_HEADER = "UHID,Patient Name,Father Name,Village\n"


def _f1_cross_file_files(second_father: str, second_village: str) -> dict[str, str]:
    return {
        "opd/opd_march.csv": _OPD_HEADER + "KSR-26-005522,Rhea Castellan,Joaquin Castellan,Brantmoor\n",
        "opd/opd_april.csv": _OPD_HEADER + f"KSR-26-005522,Rhea Castellan,{second_father},{second_village}\n",
        "lab/pathology_slip.txt": (
            "PATHOLOGY REPORT\nPatient: Rhea Castellan\nUHID: KSR-26-005522\nHaemoglobin 11.2 g/dL\n"
        ),
    }


def test_p33_f1_cross_file_prefixed_mrn_lab_slip_cannot_bridge_two_homonyms(tmp_path):
    recs = _run_link(tmp_path, _f1_cross_file_files("Idris Halloran", "Holloway Cross"))
    a, b, lab = "opd/opd_march.csv#row:0", "opd/opd_april.csv#row:0", "lab/pathology_slip.txt#doc"
    assert not _same(recs, a, b)
    # The partial lab slip matches both homonyms: it is an ambiguous bridge and joins neither.
    assert not _same(recs, lab, a) and not _same(recs, lab, b)


def test_p33_f1_positive_cross_file_prefixed_mrn_compatible_records_still_link(tmp_path):
    recs = _run_link(tmp_path, _f1_cross_file_files("Joaquin Castellan", "Brantmoor"))
    a, b, lab = "opd/opd_march.csv#row:0", "opd/opd_april.csv#row:0", "lab/pathology_slip.txt#doc"
    assert _same(recs, a, b) and _same(recs, a, lab)


_WARD_HEADER = "MRN,Patient Name,Father Name,Village,Age\n"


def test_p33_f1_unverified_stem_csv_partial_row_cannot_bridge_conflicting_homonyms(tmp_path):
    recs = _run_link(
        tmp_path,
        {
            "harlowcare_ward.csv": _WARD_HEADER
            + "OP-778812,Rhea Castellan,Joaquin Castellan,Brantmoor,34\n"
            + "OP-778812,Rhea Castellan,Idris Halloran,Holloway Cross,35\n"
            + "OP-778812,Rhea Castellan,,,\n"
        },
    )
    r0, r1, r2 = (f"harlowcare_ward.csv#row:{i}" for i in range(3))
    assert not _same(recs, r0, r1)
    assert not _same(recs, r2, r0) and not _same(recs, r2, r1)


def test_p33_f1_positive_unverified_stem_csv_compatible_rows_and_partial_row_link(tmp_path):
    recs = _run_link(
        tmp_path,
        {
            "harlowcare_ward.csv": _WARD_HEADER
            + "OP-778812,Rhea Castellan,Joaquin Castellan,Brantmoor,34\n"
            + "OP-778812,Rhea Castellan,Joaquin Castellan,Brantmoor,35\n"
            + "OP-778812,Rhea Castellan,,,\n"
        },
    )
    r0, r1, r2 = (f"harlowcare_ward.csv#row:{i}" for i in range(3))
    assert _same(recs, r0, r1) and _same(recs, r0, r2)


def test_p33_f1_positive_verified_same_hospital_mrn_keeps_relaxed_homonym_vetoes(tmp_path):
    # A verified same-hospital UHID proves identity: one patient's records may name different relatives
    # (father in one, spouse in another) and that must not split them (recall protection).
    recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": "UHID,Patient Name,Father Name\nKSR-26-006630,Rhea Castellan,"
            "Joaquin Castellan\n",
            "kestrel_hospital/admissions.csv": "UHID,Patient Name,Husband Name\nKSR-26-006630,Rhea Castellan,"
            "Idris Halloran\n",
            "kestrel_hospital/billing.csv": "UHID,Amount\nKSR-26-006630,1200\n",
        },
    )
    a, b, c = (
        "kestrel_hospital/registration.csv#row:0",
        "kestrel_hospital/admissions.csv#row:0",
        "kestrel_hospital/billing.csv#row:0",
    )
    assert _same(recs, a, b) and _same(recs, a, c)


def _weak_ev(key: str, *, name: str | None, relatives: tuple[str, ...] = (), village: str | None = None):
    kw: dict = {
        "hospital": "ward_register",
        "local_ids": frozenset({("hosp:ward_register", "OP778812")}),
        "raw_mrns": frozenset({("OP778812", False)}),
    }
    if relatives:
        kw["relative_names"] = tuple(_name(r) for r in relatives)
    if village:
        kw["villages"] = frozenset({village})
    return _rec(key, name=name, **kw)


def test_p33_f1_unit_weak_group_applies_full_profile_conflict_between_non_adjacent_members():
    evs = [
        _weak_ev("a", name="Rhea Castellan", relatives=("Joaquin Castellan",), village="brntmr"),
        _weak_ev("b", name="Rhea Castellan", relatives=("Idris Halloran",), village="hlwykrs"),
        _weak_ev("c", name=None),
    ]
    part = _partition(evs)
    assert not _together(part, "a", "b")
    assert not _together(part, "c", "a") and not _together(part, "c", "b")


@pytest.mark.parametrize("seed", range(12))
def test_p33_f1_metamorphic_bridge_result_independent_of_input_order(seed):
    evs = [
        _weak_ev("a", name="Rhea Castellan", relatives=("Joaquin Castellan",)),
        _weak_ev("b", name="Rhea Castellan", relatives=("Idris Halloran",)),
        _weak_ev("c", name=None),
        _weak_ev("d", name="Rhea Castellan"),
    ]
    rng = random.Random(seed)
    shuffled = evs[:]
    rng.shuffle(shuffled)
    assert _partition(shuffled) == _partition(evs)
    assert not _together(_partition(shuffled), "a", "b")


# =========================================================================== P33-F2: relative age / gender ownership
def test_p33_f2_child_age_ignores_grandfather_age_in_free_text(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "notes/opd_note.txt": (
                "OPD NOTE\nPatient: Arlo Venn, 7 yrs, M\nBrought by grandfather Bram Venn (72 yrs).\n"
                "Mobile: 9812047736\nComplaint: fever for 3 days.\n"
            )
        },
    )["notes/opd_note.txt#doc"]
    assert ev.ages == frozenset({7})


def test_p33_f2_child_with_grandfather_mentioned_still_links_to_own_record(tmp_path):
    # False-split case: the leaked grandfather age (72) would contradict the child's own age (7).
    recs = _run_link(
        tmp_path,
        {
            "notes/opd_note.txt": (
                "OPD NOTE\nPatient: Arlo Venn, 7 yrs\nBrought by grandfather Bram Venn (72 yrs).\n"
                "Mobile: 9812047736\nComplaint: fever for 3 days.\n"
            ),
            "notes/followup.txt": "FOLLOW UP\nPatient: Arlo Venn, Age: 7\nMobile: 9812047736\nAfebrile.\n",
        },
    )
    assert _same(recs, "notes/opd_note.txt#doc", "notes/followup.txt#doc")


def test_p33_f2_female_patient_gender_ignores_male_father_in_same_note(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "notes/ward_note.txt": (
                "WARD NOTE\nPatient: Tamsin Okafor, 34 yrs/F\nAccompanied by father Idris Okafor, 61 yrs/M.\n"
                "Vitals stable.\n"
            )
        },
    )["notes/ward_note.txt#doc"]
    assert ev.genders == frozenset({"F"})
    assert ev.ages == frozenset({34})


def test_p33_f2_leaked_relative_gender_cannot_hide_gender_conflict_under_same_hospital_uhid(tmp_path):
    # False-merge case: with the father's "M" leaked into the female record, the gender veto would not fire.
    recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/ward_note.txt": (
                "KESTREL HOSPITAL\nWARD NOTE\nPatient: Tamsin Okafor, 34 yrs/F\nUHID: KSR-26-007714\n"
                "Accompanied by father Idris Okafor, 61 yrs/M.\n"
            ),
            "kestrel_hospital/opd_slip.txt": (
                "KESTREL HOSPITAL\nOPD SLIP\nPatient: Tamsin Okafor\nUHID: KSR-26-007714\nSex: M\n"
            ),
        },
    )
    assert not _same(recs, "kestrel_hospital/ward_note.txt#doc", "kestrel_hospital/opd_slip.txt#doc")


def test_p33_f2_explicit_patient_labels_keep_patient_owned_age_and_gender(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "notes/intake.txt": (
                "INTAKE\nPatient: Joaquin Ferro, Age: 46, Sex: M.\nMother: Lucia Ferro, Age: 71, Sex: F.\n"
            )
        },
    )["notes/intake.txt#doc"]
    assert ev.ages == frozenset({46})
    assert ev.genders == frozenset({"M"})


def test_p33_f2_relative_demographics_before_and_after_patient_demographics(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "notes/family_visit.txt": (
                "FAMILY VISIT\nMother: Lucia Ferro, 58 yrs/F.\nPatient: Joaquin Ferro, 31 yrs/M.\n"
                "Sister: Nadia Ferro, 27 yrs/F.\nGrandmother: Ines Ferro, aged 83.\n"
            )
        },
    )["notes/family_visit.txt#doc"]
    assert ev.ages == frozenset({31})
    assert ev.genders == frozenset({"M"})


def test_p33_f2_multiple_relatives_html_entities_and_hindi_kinship(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "notes/referral_note.txt": (
                "REFERRAL NOTE\nPatient: Idris Halloran, 52 yrs/M\n"
                "Wife&nbsp;Rhea Halloran&nbsp;(49&nbsp;yrs/F) and son Bram Halloran (24 yrs/M) present.\n"
                "पिता: Oswin Halloran, आयु 80\n"
            )
        },
    )["notes/referral_note.txt#doc"]
    assert ev.ages == frozenset({52})
    assert ev.genders == frozenset({"M"})


def test_p33_f2_hindi_patient_owned_demographics_kept(tmp_path):
    ev = _evidence(
        tmp_path,
        {"notes/hindi_note.txt": "OPD पर्ची\nमरीज़: Joaquin Ferro\nआयु: 46\nलिंग: पुरुष\nपत्नी: Lucia Ferro, आयु 44\n"},
    )["notes/hindi_note.txt#doc"]
    assert ev.ages == frozenset({46})
    assert ev.genders == frozenset({"M"})


def _fhir_bundle(narrative: str, *, gender: str = "female", aadhaar: str = AAD_1) -> str:
    return json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "p1",
                        "name": [{"given": ["Tamsin"], "family": "Okafor"}],
                        "gender": gender,
                        "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": aadhaar}],
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "e1",
                        "status": "finished",
                        "subject": {"reference": "Patient/p1"},
                        "text": {"status": "generated", "div": narrative},
                    }
                },
            ],
        }
    )


def test_p33_f2_fhir_encounter_narrative_relative_age_not_patient_age(tmp_path):
    div = (
        '<div xmlns="http://www.w3.org/1999/xhtml"><p>Patient Tamsin Okafor, 34 yrs.</p>'
        "<p>Accompanied by her <b>father</b>&nbsp;Idris Okafor, 61&nbsp;yrs/M.</p></div>"
    )
    ev = _evidence(tmp_path, {"fhir/encounter_bundle.json": _fhir_bundle(div)})["fhir/encounter_bundle.json#doc"]
    assert 61 not in ev.ages
    assert 34 in ev.ages
    assert ev.genders == frozenset({"F"})


def test_p33_f2_fhir_relative_demographics_keep_verified_aadhaar_continuity(tmp_path):
    div = (
        '<div xmlns="http://www.w3.org/1999/xhtml"><p>Patient Tamsin Okafor, 34 yrs.</p>'
        "<p>Accompanied by her father Idris Okafor, 61 yrs/M.</p></div>"
    )
    recs = _run_link(
        tmp_path,
        {
            "fhir/encounter_bundle.json": _fhir_bundle(div),
            "kestrel_hospital/registration.csv": f"Aadhaar,Patient Name,Age,Gender\n{AAD_1},Tamsin Okafor,34,F\n",
        },
    )
    assert _same(recs, "fhir/encounter_bundle.json#doc", "kestrel_hospital/registration.csv#row:0")


# =========================================================================== P33-F3: relative-owned facility
def _json_record(extra: dict) -> str:
    rec = {"patient_name": "Joaquin Ferro", "mrn": "OP-552190", **extra}
    return json.dumps({"records": [rec]})


@pytest.mark.parametrize(
    "container",
    [
        {"guardian": {"name": "Lucia Ferro", "facility": "Wrenfield Hospital"}},
        {"emergency_contact": {"name": "Lucia Ferro", "hospital": "Wrenfield Hospital"}},
        {"father": {"name": "Oswin Ferro", "facility": {"name": "Wrenfield Hospital"}}},
        {"spouse": {"name": "Lucia Ferro", "hospital_name": "Wrenfield Hospital"}},
        {"contact_person": {"name": "Lucia Ferro", "institution": "Wrenfield Hospital"}},
    ],
    ids=["guardian", "emergency_contact", "father_nested", "spouse", "contact_person"],
)
def test_p33_f3_relative_owned_facility_never_sets_patient_hospital(tmp_path, container):
    evs = _evidence(tmp_path, {"exports/batch_export.json": _json_record(container)})
    (ev,) = evs.values()
    assert ev.hospital is None or "wrenfield" not in ev.hospital
    assert not ev.hospital_reliable


def test_p33_f3_relative_owned_facility_never_sets_document_hospital(tmp_path):
    doc = json.dumps(
        {"patient_name": "Joaquin Ferro", "mrn": "OP-552190", "guardian": {"facility": "Wrenfield Hospital"}}
    )
    (ev,) = _evidence(tmp_path, {"exports/single_case.json": doc}).values()
    assert ev.hospital is None or "wrenfield" not in ev.hospital
    assert not ev.hospital_reliable


def test_p33_f3_positive_patient_owned_facility_metadata_is_kept(tmp_path):
    evs = _evidence(
        tmp_path,
        {
            "exports/batch_export.json": _json_record(
                {"facility": {"name": "Kestrel Hospital"}, "guardian": {"facility": "Wrenfield Hospital"}}
            )
        },
    )
    (ev,) = evs.values()
    assert ev.hospital is not None and "kestrel" in ev.hospital
    assert ev.hospital_reliable


def test_p33_f3_positive_referral_exclusion_still_applies(tmp_path):
    evs = _evidence(
        tmp_path, {"exports/batch_export.json": _json_record({"referral": {"hospital": "Wrenfield Hospital"}})}
    )
    (ev,) = evs.values()
    assert ev.hospital is None or "wrenfield" not in ev.hospital


def test_p33_f3_guardian_facility_cannot_split_one_patient_across_hospitals(tmp_path):
    # Two records of one patient under one reliable hospital: a guardian's workplace hospital must not
    # turn one of them into a "different reliable hospital" (false split through the R5 guard).
    recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": "UHID,Patient Name,Mobile\nKSR-26-008841,Joaquin Ferro,9934102265\n",
            "kestrel_hospital/admissions.json": json.dumps(
                {
                    "records": [
                        {
                            "uhid": "KSR-26-008841",
                            "patient_name": "Joaquin Ferro",
                            "guardian": {"name": "Lucia Ferro", "facility": "Wrenfield Hospital"},
                        }
                    ]
                }
            ),
        },
    )
    keys = [k for k in recs if k.startswith("kestrel_hospital/admissions.json")]
    assert len(keys) == 1
    assert _same(recs, "kestrel_hospital/registration.csv#row:0", keys[0])


# =========================================================================== P33-F4: Latin initial vowel folding
@pytest.mark.parametrize(
    ("initial", "full", "compatible"),
    [
        ("E. Vance", "Evander Vance", True),
        ("E. Rao", "Eshaan Rao", True),
        ("O. Kadri", "Omar Kadri", True),
        ("I. Rao", "Ishaan Rao", True),
        ("U. Kadri", "Umesh Kadri", True),
        ("E. Vance", "Imran Vance", False),
        ("E. Vance", "Indira Vance", False),
        ("O. Kadri", "Umesh Kadri", False),
        ("O. Kadri", "Ulmara Kadri", False),
        ("I. Vance", "Evander Vance", False),
        ("U. Kadri", "Omar Kadri", False),
    ],
)
def test_p33_f4_initial_compatibility_uses_raw_latin_initial(initial, full, compatible):
    a, b = _name(initial), _name(full)
    ok_grades = {NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL, NameGrade.ABBREVIATED_FULL}
    assert (compare_names(a, b) in ok_grades) is compatible
    assert (compare_names(b, a) in ok_grades) is compatible
    assert _names_phonetically_compatible([a], [b]) is compatible


def test_p33_f4_two_different_vowel_initials_are_not_equal():
    assert compare_names(_name("E. Vance"), _name("I. Vance")) is NameGrade.CONFLICT
    assert compare_names(_name("O. Kadri"), _name("U. Kadri")) is NameGrade.CONFLICT
    assert strict_name_token("E") != strict_name_token("I")


def test_p33_f4_full_name_vowel_folds_unchanged():
    # Full-name transliteration folds stay as before (Eshaan ~ Ishaan, Omar ~ Umar); only bare initials changed.
    assert compare_names(_name("Eshaan Rao"), _name("Ishaan Rao")) in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
    assert compare_names(_name("Omar Kadri"), _name("Umar Kadri")) in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
    assert compare_names(_name("Kiran Rao"), _name("Karan Rao")) is NameGrade.CONFLICT


@pytest.mark.parametrize(
    ("initial", "devanagari", "compatible"),
    [
        ("I. Kapoor", "ईशान कपूर", True),
        ("U. Kadri", "उमेश कादरी", True),
        ("O. Kadri", "ओमर कादरी", True),
        ("E. Kapoor", "इमरान कपूर", False),
        ("O. Kadri", "उमेश कादरी", False),
    ],
)
def test_p33_f4_devanagari_full_names_keep_transliteration_initials(initial, devanagari, compatible):
    ok_grades = {NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL, NameGrade.ABBREVIATED_FULL}
    assert (compare_names(_name(initial), _name(devanagari)) in ok_grades) is compatible


def test_p33_f4_shared_household_phone_initial_does_not_merge_different_vowel_given_name(tmp_path):
    recs = _run_link(
        tmp_path,
        {
            "clinic_a/visits.csv": "Patient Name,Mobile,Age\nE. Vance,9845067712,40\n",
            "clinic_b/visits.csv": "Patient Name,Mobile,Age\nImran Vance,9845067712,40\n",
        },
    )
    assert not _same(recs, "clinic_a/visits.csv#row:0", "clinic_b/visits.csv#row:0")


def test_p33_f4_positive_shared_phone_initial_links_matching_given_name(tmp_path):
    recs = _run_link(
        tmp_path,
        {
            "clinic_a/visits.csv": "Patient Name,Mobile,Age\nE. Vance,9845067712,40\n",
            "clinic_b/visits.csv": "Patient Name,Mobile,Age\nEvander Vance,9845067712,40\n",
        },
    )
    assert _same(recs, "clinic_a/visits.csv#row:0", "clinic_b/visits.csv#row:0")


def test_p33_f4_weak_shared_mrn_initial_does_not_merge_different_vowel_given_name():
    evs = [
        _weak_ev("init", name="O. Kadri"),
        _weak_ev("full", name="Ulmara Kadri"),
    ]
    assert not _together(_partition(evs), "init", "full")


def test_p33_f4_positive_weak_shared_mrn_initial_links_matching_given_name():
    evs = [_weak_ev("init", name="O. Kadri"), _weak_ev("full", name="Omar Kadri")]
    assert _together(_partition(evs), "init", "full")


# =========================================================================== P33-F5: oversized component re-entry
_SEG = 128  # = MAX_ID_BLOCK: no single identifier block is capped, only the connected component is too large


def _id_segment_group(n: int) -> list[RecordEvidence]:
    """``n`` mutually compatible records forming ONE connected identifier component: consecutive
    segments of up to 128 records share one validated ID (Aadhaar, then PAN, then ABHA number), and
    neighbouring segments overlap in one record. Pairs (2k, 2k+1) also share a verified UHID, and
    every record carries a fragment name and a household phone (Stage B / C2 re-entry routes)."""
    kinds = ["aadhaar", "pan", "abha_number"]
    values = [_aadhaar("73015529846"), "BQXPT5823K", "91-4471-2290-6635"]
    out = []
    for i in range(n):
        ids: dict[str, set[str]] = {k: set() for k in kinds}
        for seg in range(len(kinds)):
            lo, hi = seg * (_SEG - 1), seg * (_SEG - 1) + _SEG - 1
            if lo <= i <= hi:
                ids[kinds[seg]].add(values[seg])
        out.append(
            _rec(
                f"grp/{i:04d}",
                name="Joaquin",
                aadhaar=frozenset(ids["aadhaar"]),
                pan=frozenset(ids["pan"]),
                abha_number=frozenset(ids["abha_number"]),
                hospital="kestrel",
                hospital_reliable=True,
                local_ids=frozenset({("hosp:kestrel", f"KSR-26-{9000 + i // 2:06d}")}),
                phones=frozenset({"9900112233"}),
            )
        )
    return out


def _anchor() -> list[RecordEvidence]:
    # A separate, legitimate anchor cluster that the fragments could otherwise attach to in Stage C2.
    return [
        _rec("anchor/a", name="Joaquin Ferro", aadhaar=frozenset({AAD_2}), phones=frozenset({"9900112233"})),
        _rec("anchor/b", name="Joaquin Ferro", aadhaar=frozenset({AAD_2}), phones=frozenset({"9900112233"})),
    ]


def test_p33_f5_oversized_component_members_never_reenter_later_stages():
    n = MAX_COMPONENT + 4
    assert n <= 3 * (_SEG - 1)
    evs = _id_segment_group(n) + _anchor()
    clusters, stats = cluster_records(evs)
    for c in clusters:
        if any(m.file_rel.startswith("grp/") for m in c.members):
            assert len(c.members) == 1, "a record of the abstained oversized component was merged by a later stage"
    assert stats.blocks_capped_ambiguous >= 1
    assert _together(_partition(evs), "anchor/a", "anchor/b")


@pytest.mark.parametrize("n", [8, MAX_COMPONENT])
def test_p33_f5_positive_component_within_cap_is_processed_normally(n):
    part = _partition(_id_segment_group(n))
    assert len(part) == 1 and len(part[0]) == n


def test_p33_f5_whole_group_abstention_freezes_every_member():
    """Path a-b-c-d-e-f of weak MRN edges whose only contradictions are a/d (gender), b/e (age) and
    c/f (Aadhaar): no member bridges two conflicting neighbours, so the whole group abstains and every
    member must be frozen (never re-reached by Stage C1 / C2)."""
    from clinveil.linking.cluster import _resolve_edge_groups
    from clinveil.linking.matcher import ClusterProfile
    from clinveil.linking.models import LinkingStats, MatchOutcome, MatchStrength, PairDecision

    extra = {
        "a": {"genders": frozenset({"F"})},
        "b": {"ages": frozenset({20})},
        "c": {"aadhaar": frozenset({AAD_1})},
        "d": {"genders": frozenset({"M"})},
        "e": {"ages": frozenset({60})},
        "f": {"aadhaar": frozenset({AAD_2})},
    }
    names = list(extra)
    clusters = {i: ClusterProfile.from_record(_rec(k, **extra[k])) for i, k in enumerate(names)}
    sigs = {i: (k,) for i, k in enumerate(names)}
    dec = PairDecision(MatchOutcome.CONFIDENT_MATCH, MatchStrength.STRONG_SCOPED_ID, ("shared_scoped_mrn",), ())
    edges = {(i, i + 1): dec for i in range(len(names) - 1)}
    parent = {i: i for i in clusters}
    frozen: set[int] = set()
    _resolve_edge_groups(
        edges,
        clusters=clusters,
        sigs=sigs,
        find=lambda x: parent[x],
        merge_roots=lambda *a: pytest.fail("an inconsistent group must not merge"),
        stats=LinkingStats(records_total=len(names)),
        frozen=frozen,
    )
    assert frozen == set(range(len(names)))


# =========================================================================== cross-finding interactions
def test_p33_f3_x_f1_guardian_facility_cannot_turn_weak_mrn_into_verified_and_relax_vetoes(tmp_path):
    # If a guardian's hospital became the records' reliable scope, the shared MRN would count as a
    # VERIFIED same-hospital match and relax the father-name veto between two homonyms.
    def rec(father: str) -> str:
        return json.dumps(
            {
                "records": [
                    {
                        "mrn": "OP-664120",
                        "patient_name": "Rhea Castellan",
                        "father_name": father,
                        "guardian": {"name": father, "facility": "Kestrel Hospital"},
                    }
                ]
            }
        )

    recs = _run_link(
        tmp_path, {"exports/batch_a.json": rec("Joaquin Castellan"), "exports/batch_b.json": rec("Idris Halloran")}
    )
    (a,) = [k for k in recs if k.startswith("exports/batch_a.json")]
    (b,) = [k for k in recs if k.startswith("exports/batch_b.json")]
    assert not _same(recs, a, b)


def test_p33_f4_x_f1_initial_partial_record_links_only_to_matching_given_name():
    evs = [
        _weak_ev("full_e", name="Evander Castellan"),
        _weak_ev("init", name="E. Castellan"),
        _weak_ev("full_i", name="Imran Castellan"),
    ]
    part = _partition(evs)
    assert _together(part, "init", "full_e")
    assert not _together(part, "init", "full_i") and not _together(part, "full_e", "full_i")


def test_p33_f2_x_f1_relative_ages_do_not_create_or_hide_weak_group_conflicts(tmp_path):
    # Both notes mention the same grandmother's age; the patients' own ages agree: still one patient.
    note = "Patient: Arlo Venn, {age} yrs\nUHID: KSR-26-003318\nGrandmother: Ines Venn, aged 79.\n"
    recs = _run_link(
        tmp_path,
        {
            "opd/visit_one.txt": "OPD NOTE\n" + note.format(age=7),
            "opd/visit_two.txt": "OPD NOTE\n" + note.format(age=8),
            "lab/slip.txt": "PATHOLOGY REPORT\nPatient: Arlo Venn\nUHID: KSR-26-003318\nHb 12.1 g/dL\n",
        },
    )
    assert _same(recs, "opd/visit_one.txt#doc", "opd/visit_two.txt#doc")
    assert _same(recs, "opd/visit_one.txt#doc", "lab/slip.txt#doc")
