"""Phase 3.3 Pass 4: regression tests for the two independently reproduced HIGH false-merge findings.

* P33-PASS3-F1: XHTML structure (``</td><td>``, ``</dt><dd>``, ``</p><p>``) cut a relative label off
  from the relative's age / gender / Aadhaar in a FHIR narrative, making them patient-owned. Also
  the Devanagari word-boundary defect in the free-text gender patterns (``महिला`` / ``स्त्री`` never
  matched; ``पुत्री`` "daughter" was read as ``पुत्र`` "son").
* P33-PASS3-F2: a shared non-authoritative OPD / IPD number at a verified hospital (Tier 2a) returned
  a match before R7 (two different authoritative UHIDs from one issuer) was checked.

Every name, identifier, phone number, date and facility below is newly invented for these tests
(no organiser practice identity, canary or hidden-evaluation value).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from clinveil.config.policy import Policy
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.ingestion.limits import IngestLimits
from clinveil.linking.extract import _build_owner_view, context_owner
from clinveil.linking.matcher import ClusterProfile, compare_profiles, weak_path_conflicts
from clinveil.linking.models import MatchOutcome, MatchStrength, RecordEvidence
from clinveil.linking.normalize import iter_free_genders
from clinveil.pipeline import _pass1_collect, run
from clinveil.security.secrets import ReleaseSecret
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_FATHER = _aadhaar("83920475162")
AAD_CHILD = _aadhaar("94031586273")


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


def _profiles(evs: dict[str, RecordEvidence], a: str, b: str) -> tuple[ClusterProfile, ClusterProfile]:
    reliable = frozenset(
        e.hospital for e in evs.values() if e.hospital and e.hospital_reliable and not e.is_external_lab
    )
    return ClusterProfile.from_record(evs[a], reliable), ClusterProfile.from_record(evs[b], reliable)


def _owner_at(text: str, needle: str) -> str:
    view, starts = _build_owner_view(text)
    raw = text.index(needle)
    pos = raw if starts is None else next(i for i, s in enumerate(starts) if s >= raw)
    return context_owner(view, pos)


# =========================================================================== P33-PASS3-F1: XHTML ownership
_XHTML = '<div xmlns="http://www.w3.org/1999/xhtml">{}</div>'
_FATHER_DETAILS = f"Thaddeus Ravensworth, 42 yrs, Aadhaar: {AAD_FATHER}"

F1_VARIANTS = {
    "table": _XHTML.format(
        "<table><tr><td>Patient</td><td>T. Ravensworth, 8 yrs</td></tr>"
        f"<tr><td>Father</td><td>{_FATHER_DETAILS}</td></tr></table>"
    ),
    "table_th_pretty_printed": _XHTML.format(
        "\n  <table>\n    <tr>\n      <th>Patient</th>\n      <td>T. Ravensworth, 8 yrs</td>\n    </tr>\n"
        f"    <tr>\n      <th>Father</th>\n      <td>{_FATHER_DETAILS}</td>\n    </tr>\n  </table>\n"
    ),
    "definition_list": _XHTML.format(
        f"<dl><dt>Patient</dt><dd>T. Ravensworth, 8 yrs</dd><dt>Father</dt><dd>{_FATHER_DETAILS}</dd></dl>"
    ),
    "consecutive_paragraphs": _XHTML.format(
        f"<p>Patient: T. Ravensworth, 8 yrs</p><p>Father: Thaddeus Ravensworth</p><p>42 yrs, Aadhaar: {AAD_FATHER}</p>"
    ),
    "inline_control": _XHTML.format(f"<p>Patient: T. Ravensworth, 8 yrs</p><p><b>Father</b>: {_FATHER_DETAILS}</p>"),
}


def _child_bundle(div: str, *, gender: str = "male", identifiers: list[dict] | None = None) -> str:
    patient: dict = {
        "resourceType": "Patient",
        "id": "child-1",
        "name": [{"given": ["T."], "family": "Ravensworth"}],
        "gender": gender,
    }
    if identifiers:
        patient["identifier"] = identifiers
    return json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": patient},
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "enc-1",
                        "status": "finished",
                        "subject": {"reference": "Patient/child-1"},
                        "text": {"status": "generated", "div": div},
                    }
                },
            ],
        }
    )


_FATHER_CSV = f"Aadhaar,Patient Name,Age,Gender\n{AAD_FATHER},Thaddeus Ravensworth,42,M\n"
_CHILD_KEY = "fhir/child_bundle.json#doc"
_FATHER_KEY = "registry/adult_register.csv#row:0"


@pytest.mark.parametrize("variant", sorted(F1_VARIANTS))
def test_pass4_f1_relative_age_and_aadhaar_never_patient_owned_in_xhtml(variant):
    div = F1_VARIANTS[variant]
    assert _owner_at(div, "42 yrs") != "patient"
    assert _owner_at(div, AAD_FATHER) != "patient"
    assert _owner_at(div, "8 yrs") == "patient"


@pytest.mark.parametrize("variant", ["table", "table_th_pretty_printed", "definition_list", "inline_control"])
def test_pass4_f1_label_in_same_row_or_entry_is_relative_owned(variant):
    div = F1_VARIANTS[variant]
    assert _owner_at(div, "42 yrs") == "relative"
    assert _owner_at(div, AAD_FATHER) == "relative"


@pytest.mark.parametrize("variant", sorted(F1_VARIANTS))
def test_pass4_f1_child_evidence_excludes_father_age_and_aadhaar(tmp_path, variant):
    ev = _evidence(tmp_path, {"fhir/child_bundle.json": _child_bundle(F1_VARIANTS[variant])})[_CHILD_KEY]
    assert ev.ages == frozenset({8})
    assert AAD_FATHER not in ev.aadhaar


@pytest.mark.parametrize("variant", ["table", "definition_list", "inline_control"])
def test_pass4_f1_father_aadhaar_recorded_as_relative_owned(tmp_path, variant):
    ev = _evidence(tmp_path, {"fhir/child_bundle.json": _child_bundle(F1_VARIANTS[variant])})[_CHILD_KEY]
    assert any(AAD_FATHER in rid for rid in ev.relative_global_ids)


@pytest.mark.parametrize("variant", sorted(F1_VARIANTS))
def test_pass4_f1_full_pipeline_child_and_father_get_different_pseudonyms(tmp_path, variant):
    recs = _run_link(
        tmp_path,
        {"fhir/child_bundle.json": _child_bundle(F1_VARIANTS[variant]), "registry/adult_register.csv": _FATHER_CSV},
    )
    assert recs[_FATHER_KEY] is not None
    assert recs[_CHILD_KEY] != recs[_FATHER_KEY]


@pytest.mark.parametrize("structure", ["table", "definition_list"])
def test_pass4_f1_relative_gender_in_xhtml_not_patient_gender(tmp_path, structure):
    father = "Thaddeus Ravensworth, 42 yrs/M"
    if structure == "table":
        body = (
            "<table><tr><td>Patient</td><td>T. Ravensworth, 8 yrs/F</td></tr>"
            f"<tr><td>Father</td><td>{father}</td></tr></table>"
        )
    else:
        body = f"<dl><dt>Patient</dt><dd>T. Ravensworth, 8 yrs/F</dd><dt>Father</dt><dd>{father}</dd></dl>"
    ev = _evidence(tmp_path, {"fhir/child_bundle.json": _child_bundle(_XHTML.format(body), gender="female")})[
        _CHILD_KEY
    ]
    assert ev.genders == frozenset({"F"})
    assert ev.ages == frozenset({8})


def test_pass4_f1_patient_owned_identifiers_and_demographics_still_extracted(tmp_path):
    div = _XHTML.format(
        f"<table><tr><td>Patient</td><td>T. Ravensworth, 8 yrs/M, Aadhaar: {AAD_CHILD}</td></tr>"
        f"<tr><td>Father</td><td>{_FATHER_DETAILS}</td></tr></table>"
    )
    ev = _evidence(tmp_path, {"fhir/child_bundle.json": _child_bundle(div)})[_CHILD_KEY]
    assert AAD_CHILD in ev.aadhaar
    assert AAD_FATHER not in ev.aadhaar
    assert ev.ages == frozenset({8})
    assert ev.genders == frozenset({"M"})


def test_pass4_f1_separate_sections_keep_their_own_owners(tmp_path):
    div = _XHTML.format(
        "<h3>Father</h3><p>Thaddeus Ravensworth, 42 yrs</p>"
        f"<h3>Patient</h3><p>T. Ravensworth, 8 yrs, Aadhaar: {AAD_CHILD}</p>"
    )
    assert _owner_at(div, "42 yrs") != "patient"
    assert _owner_at(div, AAD_CHILD) == "patient"
    ev = _evidence(tmp_path, {"fhir/child_bundle.json": _child_bundle(div)})[_CHILD_KEY]
    assert AAD_CHILD in ev.aadhaar and ev.ages == frozenset({8})


def test_pass4_f1_new_section_is_still_a_hard_boundary():
    # A heading opens an unrelated section: the identifier after it is not the mother's.
    div = _XHTML.format(f"<p>Mother: Ysolde Ravensworth</p><h2>Investigations</h2><p>Aadhaar: {AAD_CHILD}</p>")
    assert _owner_at(div, AAD_CHILD) == "patient"


def test_pass4_f1_separate_rows_do_not_inherit_patient_owner_from_previous_row():
    div = F1_VARIANTS["table"]
    view, _ = _build_owner_view(div)
    # Rows stay separate lines; a cell join inside a row is one space (like "Father: <name>").
    assert re.search(r"\n[ ]*Father[ ]+Thaddeus", view)
    assert re.search(r"\n[ \t]*\n", view) is None


def test_pass4_f1_positive_child_links_to_own_record_by_own_aadhaar(tmp_path):
    div = F1_VARIANTS["table"]
    recs = _run_link(
        tmp_path,
        {
            "fhir/child_bundle.json": _child_bundle(
                div, identifiers=[{"system": "https://uidai.gov.in/aadhaar", "value": AAD_CHILD}]
            ),
            "registry/adult_register.csv": _FATHER_CSV,
            "registry/child_register.csv": f"Aadhaar,Patient Name,Age,Gender\n{AAD_CHILD},Tobin Ravensworth,8,M\n",
        },
    )
    child_csv = "registry/child_register.csv#row:0"
    assert _same(recs, _CHILD_KEY, child_csv)
    assert recs[_CHILD_KEY] != recs[_FATHER_KEY]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("लिंग: महिला", "F"),
        ("लिंग: महिला\nआयु 30", "F"),
        ("लिंग: स्त्री, आयु 30", "F"),
        ("लिंग: पुरुष", "M"),
        ("Zerina पुत्री Ilyas", "F"),
        ("Corwin पुत्र Ilyas", "M"),
        ("Zerina पत्नी Ilyas", "F"),
    ],
)
def test_pass4_f1_devanagari_gender_word_boundaries(text, expected):
    assert [g for _, g in iter_free_genders(text)] == [expected]


def test_pass4_f1_devanagari_kin_label_and_longer_words_not_gender():
    assert iter_free_genders("पत्नी: Zerina") == []
    assert iter_free_genders("लिंग: महिलाएं") == []


def test_pass4_f1_devanagari_female_free_text_patient_gender(tmp_path):
    note = "रोगी: Zerina Talwar\nआयु 29 वर्ष\nलिंग: महिला\nपिता: Ilyas Talwar, आयु 61\n"
    ev = _evidence(tmp_path, {"notes/opd_note.txt": note})["notes/opd_note.txt#doc"]
    assert ev.genders == frozenset({"F"})
    assert 61 not in ev.ages


# =========================================================================== P33-PASS3-F2: R7 before Tier 2a
_OPD_HEADER = "UHID,OPD No,Patient Name,DOB\n"
_IPD_HEADER = "UHID,IPD No,Patient Name,DOB\n"
_LINK_HEADER = "OPD No,IPD No,Patient Name,DOB\n"
_A = "harlowcare_hospital/opd_jan.csv#row:0"
_B = "harlowcare_hospital/opd_feb.csv#row:0"


def _f2_files(uhid_b: str, local_b: str, *, header: str = _OPD_HEADER, local_a: str = "OP-512907") -> dict[str, str]:
    return {
        "harlowcare_hospital/opd_jan.csv": header + f"HCW-31-004417,{local_a},Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/opd_feb.csv": header + f"{uhid_b},{local_b},Odalys Treverro,1987-06-14\n",
    }


def test_pass4_f2_compare_profiles_distinct_uhids_shared_opd_is_conflict(tmp_path):
    evs = _evidence(tmp_path, _f2_files("HCW-31-006023", "OP-512907"))
    pa, pb = _profiles(evs, _A, _B)
    dec = compare_profiles(pa, pb)
    assert dec.outcome is MatchOutcome.CONFLICT
    assert "conflict_scoped_mrn" in dec.conflicts


def test_pass4_f2_weak_path_conflicts_enforces_r7_with_shared_verified_local_id(tmp_path):
    evs = _evidence(tmp_path, _f2_files("HCW-31-006023", "OP-512907"))
    pa, pb = _profiles(evs, _A, _B)
    assert "conflict_scoped_mrn" in weak_path_conflicts(pa, pb)


@pytest.mark.parametrize(
    ("header", "local"),
    [(_OPD_HEADER, "OP-512907"), (_IPD_HEADER, "IPD-770318"), (_IPD_HEADER, "ADM-2026-04418")],
)
def test_pass4_f2_full_pipeline_distinct_uhids_shared_visit_or_admission_id_not_merged(tmp_path, header, local):
    recs = _run_link(tmp_path, _f2_files("HCW-31-006023", local, header=header, local_a=local))
    assert recs[_A] is not None and recs[_B] is not None
    assert recs[_A] != recs[_B]


def test_pass4_f2_positive_same_uhid_still_tier2a_match(tmp_path):
    evs = _evidence(tmp_path, _f2_files("HCW-31-004417", "OP-640021"))
    pa, pb = _profiles(evs, _A, _B)
    dec = compare_profiles(pa, pb)
    assert dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength is MatchStrength.STRONG_SCOPED_ID
    assert weak_path_conflicts(pa, pb) == ()
    recs = _run_link(tmp_path, _f2_files("HCW-31-004417", "OP-640021"))
    assert _same(recs, _A, _B)


def test_pass4_f2_positive_shared_opd_without_conflicting_uhid_still_links(tmp_path):
    files = {
        "harlowcare_hospital/opd_jan.csv": _OPD_HEADER + "HCW-31-004417,OP-512907,Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/opd_visit.csv": "OPD No,Patient Name,DOB\nOP-512907,Odalys Treverro,1987-06-14\n",
    }
    evs = _evidence(tmp_path, files)
    b = "harlowcare_hospital/opd_visit.csv#row:0"
    pa, pb = _profiles(evs, _A, b)
    dec = compare_profiles(pa, pb)
    assert dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength is MatchStrength.STRONG_SCOPED_ID
    recs = _run_link(tmp_path, files)
    assert _same(recs, _A, b)


def _rereg_files(shared_opd: bool) -> dict[str, str]:
    hdr = "UHID,OPD No,Patient Name,DOB,Phone\n"
    opd_b = "OP-512907" if shared_opd else "OP-640021"
    return {
        "harlowcare_hospital/opd_jan.csv": hdr + "HCW-31-004417,OP-512907,Odalys Treverro,1987-06-14,9301746628\n",
        "harlowcare_hospital/opd_feb.csv": hdr + f"HCW-31-006023,{opd_b},Odalys Treverro,1987-06-14,9301746628\n",
    }


@pytest.mark.parametrize("shared_opd", [False, True])
def test_pass4_f2_positive_reregistration_exact_dob_and_phone_still_links(tmp_path, shared_opd):
    files = _rereg_files(shared_opd)
    evs = _evidence(tmp_path, files)
    pa, pb = _profiles(evs, _A, _B)
    dec = compare_profiles(pa, pb)
    assert dec.outcome is MatchOutcome.CONFIDENT_MATCH
    assert "conflict_scoped_mrn" not in weak_path_conflicts(pa, pb)
    recs = _run_link(tmp_path, files)
    assert _same(recs, _A, _B)


def test_pass4_f2_global_id_precedence_preserved(tmp_path):
    hdr = "UHID,OPD No,Aadhaar,Patient Name,DOB\n"
    files = {
        "harlowcare_hospital/opd_jan.csv": hdr + f"HCW-31-004417,OP-512907,{AAD_CHILD},Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/opd_feb.csv": hdr + f"HCW-31-006023,OP-512907,{AAD_CHILD},Odalys Treverro,1987-06-14\n",
    }
    evs = _evidence(tmp_path, files)
    pa, pb = _profiles(evs, _A, _B)
    dec = compare_profiles(pa, pb)
    assert dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength is MatchStrength.STRONG_GLOBAL
    recs = _run_link(tmp_path, files)
    assert _same(recs, _A, _B)


def test_pass4_f2_chain_of_verified_local_ids_cannot_join_distinct_uhids(tmp_path):
    # A and B never share a local ID directly: A -OPD- C -IPD- B. C is an ambiguous bridge.
    files = {
        "harlowcare_hospital/opd_jan.csv": _OPD_HEADER + "HCW-31-004417,OP-512907,Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/ward_link.csv": _LINK_HEADER + "OP-512907,IPD-770318,Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/ipd_feb.csv": _IPD_HEADER + "HCW-31-006023,IPD-770318,Odalys Treverro,1987-06-14\n",
    }
    recs = _run_link(tmp_path, files)
    a, c, b = _A, "harlowcare_hospital/ward_link.csv#row:0", "harlowcare_hospital/ipd_feb.csv#row:0"
    assert not _same(recs, a, b)
    assert not (_same(recs, c, a) and _same(recs, c, b))


def test_pass4_f2_positive_chain_of_verified_local_ids_without_conflict_still_links(tmp_path):
    files = {
        "harlowcare_hospital/opd_jan.csv": _OPD_HEADER + "HCW-31-004417,OP-512907,Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/ward_link.csv": _LINK_HEADER + "OP-512907,IPD-770318,Odalys Treverro,1987-06-14\n",
        "harlowcare_hospital/ipd_feb.csv": _IPD_HEADER + "HCW-31-004417,IPD-770318,Odalys Treverro,1987-06-14\n",
    }
    recs = _run_link(tmp_path, files)
    a, c, b = _A, "harlowcare_hospital/ward_link.csv#row:0", "harlowcare_hospital/ipd_feb.csv#row:0"
    assert _same(recs, a, c) and _same(recs, c, b)


def test_pass4_f2_x_f1_xhtml_relative_aadhaar_cannot_override_distinct_uhids(tmp_path):
    # Two different patients at one hospital: the shared Aadhaar is the FATHER's (table cell), so it
    # must not become a global ID that outranks R7.
    div = _XHTML.format(
        "<table><tr><td>Patient</td><td>Odalys Treverro</td></tr>"
        f"<tr><td>Father</td><td>Bastien Treverro, Aadhaar: {AAD_FATHER}</td></tr></table>"
    )
    bundle = json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "p1",
                        "name": [{"given": ["Odalys"], "family": "Treverro"}],
                        "birthDate": "1987-06-14",
                        "identifier": [{"system": "https://harlowcare.example/uhid", "value": "HCW-31-004417"}],
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "e1",
                        "status": "finished",
                        "subject": {"reference": "Patient/p1"},
                        "text": {"status": "generated", "div": div},
                    }
                },
            ],
        }
    )
    files = {
        "harlowcare_hospital/bundle.json": bundle,
        "harlowcare_hospital/opd_feb.csv": "UHID,Aadhaar,Patient Name,DOB\n"
        f"HCW-31-006023,{AAD_FATHER},Odalys Treverro,1987-06-14\n",
    }
    recs = _run_link(tmp_path, files)
    assert not _same(recs, "harlowcare_hospital/bundle.json#doc", "harlowcare_hospital/opd_feb.csv#row:0")
