"""Phase 3.3 Pass 2: regression tests for NEW-5/6/7 and PASS1-NEW-5/6/7.

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
from clinveil.linking.cluster import cluster_records
from clinveil.linking.matcher import ClusterProfile, _authoritative_ids_by_scope, compare_profiles
from clinveil.linking.models import DateEvidence, MatchOutcome, NameGrade, RecordEvidence, RecordKey
from clinveil.linking.normalize import build_name_evidence, compare_names
from clinveil.pipeline import _pass1_collect, run
from clinveil.security.secrets import ReleaseSecret
from clinveil.validation.contract import _check_records_pseudonyms, _ParsedOutput
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_1 = _aadhaar("62847193055")
AAD_2 = _aadhaar("73958204166")
AAD_3 = _aadhaar("84069315277")
PAN_1 = "CTRPV4821M"
PAN_2 = "DLMPK7310Q"


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _run_link(tmp_path: Path, files: dict[str, str]) -> tuple[object, dict[str, str | None]]:
    """Run the full pipeline; map ``<input rel>#<loc>`` -> pseudonym (inputs keep their names here)."""
    inp, out = _write(tmp_path / "in", files), tmp_path / "out"
    summary = run(inp, out, ReleaseSecret(TEST_SECRET.encode()), Policy())
    assert summary.ok, summary.problems
    recs: dict[str, str | None] = {}
    for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[f"{r['file'].removeprefix('sanitized/')}#{r['loc']}"] = r["patient"]
    return summary, recs


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


# =========================================================================== PASS1-NEW-5: issuer prefix vs reliability
def test_pass1_new5_issuer_prefix_recorded_for_reliable_hospital_scope():
    ev = _rec(
        "r",
        hospital="kestrel",
        hospital_reliable=True,
        local_ids=frozenset({("hosp:kestrel", "KSR-26-004417")}),
        raw_mrns=frozenset({("KSR-26-004417", True)}),
    )
    scopes = _authoritative_ids_by_scope(ClusterProfile.from_record(ev))
    assert scopes.get("issuer_pfx:pfx_ksr") == {"pfx_ksr:4417"}


@pytest.mark.parametrize("with_phone", [True, False])
def test_pass1_new5_reliable_hospital_vs_unreliable_export_distinct_same_issuer_uhids_never_merge(tmp_path, with_phone):
    phone = ",9876501234" if with_phone else ","
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": f"UHID,Patient Name,Mobile\nKSR-26-004417,Tamsin Okafor{phone}\n",
            "exports/export_jan.csv": f"UHID,Patient Name,Mobile\nKSR-26-004981,Tamsin Okafor{phone}\n",
        },
    )
    assert not _same(recs, "kestrel_hospital/registration.csv#row:0", "exports/export_jan.csv#row:0")


def test_pass1_new5_same_issuer_distinct_uhids_across_two_hospitals_never_merge(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": "UHID,Patient Name,Mobile\nKSR-26-004417,Tamsin Okafor,9876501234\n",
            "wrenfield_hospital/referrals.csv": "UHID,Patient Name,Mobile\nKSR-26-004981,Tamsin Okafor,9876501234\n",
        },
    )
    assert not _same(recs, "kestrel_hospital/registration.csv#row:0", "wrenfield_hospital/referrals.csv#row:0")


def test_pass1_new5_positive_same_uhid_cited_at_another_hospital_still_links(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": "UHID,Patient Name,Mobile\nKSR-26-004417,Tamsin Okafor,9876501234\n",
            "wrenfield_hospital/referrals.csv": "UHID,Patient Name,Mobile\nKSR-26-004417,Tamsin Okafor,9876501234\n",
            "exports/export_jan.csv": "UHID,Patient Name\nKSR-26-004417,Tamsin Okafor\n",
        },
    )
    assert _same(recs, "kestrel_hospital/registration.csv#row:0", "wrenfield_hospital/referrals.csv#row:0")
    assert _same(recs, "kestrel_hospital/registration.csv#row:0", "exports/export_jan.csv#row:0")


def test_pass1_new5_positive_different_issuers_with_similar_formats_are_not_vetoed(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": "UHID,Patient Name,Mobile\nKSR-26-004417,Tamsin Okafor,9876501234\n",
            "exports/export_jan.csv": "UHID,Patient Name,Mobile\nKSD-26-004981,Tamsin Okafor,9876501234\n",
        },
    )
    assert _same(recs, "kestrel_hospital/registration.csv#row:0", "exports/export_jan.csv#row:0")


def test_pass1_new5_positive_legitimate_reregistration_across_reliable_and_export_still_links(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/registration.csv": (
                "UHID,Patient Name,DOB,Mobile\nKSR-26-004417,Tamsin Okafor,1988-07-19,9876501234\n"
            ),
            "exports/export_jan.csv": (
                "UHID,Patient Name,DOB,Mobile\nKSR-26-004981,Tamsin Okafor,1988-07-19,9876501234\n"
            ),
        },
    )
    assert _same(recs, "kestrel_hospital/registration.csv#row:0", "exports/export_jan.csv#row:0")


# =========================================================================== PASS1-NEW-6: bridges, linkage, order
@pytest.mark.parametrize("swap", [False, True])
def test_pass1_new6_partial_bridge_between_two_identities_abstains(swap):
    """B carries A's Aadhaar and C's PAN; A and C are different people. B must not join either."""
    a_ids = {"pan": frozenset({PAN_1})} if swap else {"aadhaar": frozenset({AAD_1})}
    c_ids = {"aadhaar": frozenset({AAD_1})} if swap else {"pan": frozenset({PAN_1})}
    evs = [
        _rec("a", name="Tamsin Okafor", genders=frozenset({"F"}), **a_ids),
        _rec("b", aadhaar=frozenset({AAD_1}), pan=frozenset({PAN_1})),
        _rec("c", name="Idris Halloran", genders=frozenset({"M"}), **c_ids),
    ]
    part = _partition(evs)
    assert part == [["a"], ["b"], ["c"]]


def test_pass1_new6_abstained_bridge_never_reenters_through_a_later_stage():
    """The nameless bridge B is ambiguous in Stage A (Aadhaar of A, PAN of C). It ALSO shares A's
    verified same-hospital MRN, which Stage B would accept: it must stay excluded."""
    kest = {
        "hospital": "kestrel",
        "hospital_reliable": True,
        "local_ids": frozenset({("hosp:kestrel", "MRN-55501")}),
        "raw_mrns": frozenset({("MRN-55501", False)}),
    }
    evs = [
        _rec("a", name="Tamsin Okafor", aadhaar=frozenset({AAD_1}), **kest),
        _rec("b", aadhaar=frozenset({AAD_1}), pan=frozenset({PAN_1}), **kest),
        _rec("c", name="Idris Halloran", pan=frozenset({PAN_1})),
    ]
    assert _partition(evs) == [["a"], ["b"], ["c"]]


def test_pass1_new6_positive_consistent_bridge_still_links_one_patient():
    evs = [
        _rec("a", name="Tamsin Okafor", aadhaar=frozenset({AAD_1})),
        _rec("b", name="Tamsin Okafor", aadhaar=frozenset({AAD_1}), pan=frozenset({PAN_1})),
        _rec("c", name="Tamsin Okafor", pan=frozenset({PAN_1}), dobs=frozenset({DateEvidence((1988, 7, 19))})),
    ]
    assert _partition(evs) == [["a", "b", "c"]]


def test_pass1_new6_conflicting_partial_records_sharing_one_id_never_end_up_together():
    evs = [
        _rec("t", name="Tamsin Okafor", aadhaar=frozenset({AAD_1})),
        _rec("s1", aadhaar=frozenset({AAD_1}), genders=frozenset({"F"})),
        _rec("s2", aadhaar=frozenset({AAD_1}), genders=frozenset({"M"})),
    ]
    assert not _together(_partition(evs), "s1", "s2")
    assert _partition(evs[:2]) == [["s1", "t"]]


def test_pass1_new6_weak_name_match_cannot_bridge_two_incompatible_full_identities(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/register_a.csv": "Patient Name,Mobile,DOB\nRhea Castellan,9812304567,1979-03-02\n",
            "reg/register_b.csv": "Patient Name,Mobile\nRhea Castellan,9812304567\n",
            "reg/register_c.csv": "Patient Name,Mobile,DOB\nRhea Castellan,9812304567,1994-11-23\n",
        },
    )
    a, b, c = "reg/register_a.csv#row:0", "reg/register_b.csv#row:0", "reg/register_c.csv#row:0"
    assert not _same(recs, a, c)
    assert not _same(recs, a, b)
    assert not _same(recs, b, c)


def test_pass1_new6_fragmented_singletons_conflicting_with_each_other_do_not_both_attach():
    anchor = _rec("t", name="Tamsin Okafor", aadhaar=frozenset({AAD_1}), phones=frozenset({"9876501234"}))
    s1 = _rec("s1", name="Tamsin", phones=frozenset({"9876501234"}), ages=frozenset({31}))
    s2 = _rec("s2", name="Tamsin", phones=frozenset({"9876501234"}), ages=frozenset({58}))
    part = _partition([anchor, s1, s2])
    assert not _together(part, "s1", "s2")
    assert not _together(part, "t", "s1")
    assert not _together(part, "t", "s2")
    assert _partition([anchor, s1]) == [["s1", "t"]]


def test_pass1_new6_single_token_name_cannot_join_a_contradicting_full_name_across_stages():
    """Stage A joins "N. Vermeer" and "Joaquin" via PAN; Stage B would add "Nathan Vermeer" through a
    verified MRN. "Joaquin" contradicts "Nathan Vermeer", so the cluster must not hold both."""
    kest = {
        "hospital": "kestrel",
        "hospital_reliable": True,
        "local_ids": frozenset({("hosp:kestrel", "MRN-55501")}),
        "raw_mrns": frozenset({("MRN-55501", False)}),
    }
    evs = [
        _rec("a", pan=frozenset({PAN_2}), **kest),
        _rec("b", name="Nathan Vermeer", **kest),
        _rec("c", name="N. Vermeer", pan=frozenset({PAN_2})),
        _rec("d", name="Joaquin", pan=frozenset({PAN_2}), aadhaar=frozenset({AAD_2})),
    ]
    part = _partition(evs)
    assert not _together(part, "b", "d")
    # positive control: a compatible fragment ("Nathan") still joins
    evs[3] = _rec("d", name="Nathan", pan=frozenset({PAN_2}), aadhaar=frozenset({AAD_2}))
    assert _partition(evs) == [["a", "b", "c", "d"]]


def _adversarial_corpus() -> list[dict]:
    d1, d2 = DateEvidence((1979, 3, 2)), DateEvidence((1994, 11, 23))
    kest = {"hospital": "kestrel", "hospital_reliable": True}
    wren = {"hospital": "wrenfield", "hospital_reliable": True}
    return [
        {"name": "Tamsin Okafor", "aadhaar": frozenset({AAD_1}), "genders": frozenset({"F"})},
        {"aadhaar": frozenset({AAD_1}), "pan": frozenset({PAN_1})},
        {"name": "Idris Halloran", "pan": frozenset({PAN_1}), "genders": frozenset({"M"})},
        {"name": "Tamsin Okafor", "phones": frozenset({"9876501234"}), "dobs": frozenset({d1})},
        {"name": "Tamsin Okafor", "phones": frozenset({"9876501234"})},
        {"name": "Tamsin Okafor", "phones": frozenset({"9876501234"}), "dobs": frozenset({d2})},
        {"name": "T. Okafor", "aadhaar": frozenset({AAD_2})},
        {"name": "Tamsin Okafor", "aadhaar": frozenset({AAD_2}), "dobs": frozenset({d1})},
        {
            "name": "Rhea Castellan",
            "local_ids": frozenset({("hosp:kestrel", "MRN-55501")}),
            "raw_mrns": frozenset({("MRN-55501", False)}),
            **kest,
        },
        {
            "name": "Joaquin Ferro",
            "local_ids": frozenset({("hosp:wrenfield", "MRN-55501")}),
            "raw_mrns": frozenset({("MRN-55501", False)}),
            **wren,
        },
        {"raw_mrns": frozenset({("MRN-55501", False)}), "is_external_lab": True, "hospital": "citypath"},
        {"name": "Tamsin", "phones": frozenset({"9876501234"}), "ages": frozenset({44})},
        {"name": "Omar Kadri", "aadhaar": frozenset({AAD_3})},
        {"name": "O. Kadri", "aadhaar": frozenset({AAD_3})},
    ]


def test_pass1_new6_metamorphic_partition_identical_under_order_file_and_locator_permutations():
    corpus = _adversarial_corpus()
    base = _partition([_rec(f"f{i:02d}", **kw) for i, kw in enumerate(corpus)])
    rng = random.Random(20261127)
    for _ in range(40):
        order = list(range(len(corpus)))
        rng.shuffle(order)
        names = {i: f"{rng.choice('xyzabc')}{rng.randrange(10**6):06d}/{i}.csv" for i in order}
        evs = [
            RecordEvidence(
                record=RecordKey(names[i], f"row:{rng.randrange(50)}"),
                **{k: v for k, v in corpus[i].items() if k != "name"},
                patient_names=(_name(corpus[i]["name"]),) if "name" in corpus[i] else (),
            )
            for i in order
        ]
        back = {names[i]: f"f{i:02d}" for i in order}
        clusters, _ = cluster_records(evs)
        perm = sorted(sorted(back[m.file_rel] for m in c.members) for c in clusters)
        assert perm == base


def test_pass1_new6_metamorphic_end_to_end_file_renames_and_row_order(tmp_path):
    rows = [
        f"Tamsin Okafor,{AAD_1},,F",
        f",{AAD_1},{PAN_1},",
        f"Idris Halloran,,{PAN_1},M",
        f"Omar Kadri,{AAD_3},,M",
        f"O. Kadri,{AAD_3},,M",
    ]
    header = "Patient Name,Aadhaar,PAN,Gender\n"

    def partition(files: dict[str, str], row_of: dict[str, tuple[str, int]], sub: Path) -> list[list[str]]:
        _, recs = _run_link(sub, files)
        groups: dict[str, list[str]] = {}
        for label, (rel, i) in row_of.items():
            psn = recs[f"{rel}#row:{i}"]
            groups.setdefault(psn or f"none:{label}", []).append(label)
        return sorted(sorted(g) for g in groups.values())

    base = partition(
        {
            "reg/a_registry.csv": header + "\n".join(rows[:3]) + "\n",
            "reg/b_registry.csv": header + "\n".join(rows[3:]) + "\n",
        },
        {f"r{i}": ("reg/a_registry.csv", i) for i in range(3)}
        | {f"r{i}": ("reg/b_registry.csv", i - 3) for i in range(3, 5)},
        tmp_path / "base",
    )
    perm = partition(
        {
            "zz/omega_registry.csv": header + "\n".join([rows[2], rows[0], rows[1]]) + "\n",
            "aa/alpha_registry.csv": header + "\n".join([rows[4], rows[3]]) + "\n",
        },
        {
            "r2": ("zz/omega_registry.csv", 0),
            "r0": ("zz/omega_registry.csv", 1),
            "r1": ("zz/omega_registry.csv", 2),
            "r4": ("aa/alpha_registry.csv", 0),
            "r3": ("aa/alpha_registry.csv", 1),
        },
        tmp_path / "perm",
    )
    assert base == perm
    assert ["r3", "r4"] in base
    assert ["r1"] in base or not any("r1" in g and len(g) > 1 for g in base)


# =========================================================================== PASS1-NEW-7 / NEW-5: facility provenance
def test_pass1_new7_blank_facility_cell_keeps_reliable_document_scope(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "kestrel_hospital/register.csv": (
                "Facility,MRN,Patient Name\nKestrel Hospital,MRN-55501,Tamsin Okafor\n,MRN-55502,Idris Halloran\n"
            )
        },
    )
    row1 = ev["kestrel_hospital/register.csv#row:1"]
    assert row1.hospital == "kestrel"
    assert row1.hospital_reliable


def test_pass1_new7_conflicting_explicit_facility_never_gets_document_hospital(tmp_path):
    ev = _evidence(
        tmp_path,
        {
            "kestrel_hospital/register.csv": (
                "Facility,MRN,Patient Name\nWrenfield Clinic,MRN-55501,Tamsin Okafor\n,MRN-55502,Idris Halloran\n"
            )
        },
    )
    row0 = ev["kestrel_hospital/register.csv#row:0"]
    assert row0.hospital == "wrenfield"
    assert ("hosp:kestrel", "MRN-55501") not in row0.local_ids


def test_pass1_new7_document_reliability_is_never_upgraded_onto_an_unreliable_stem(tmp_path):
    ev = _evidence(tmp_path, {"exports/kestrel_batch.csv": "MRN,Patient Name\nMRN-55501,Tamsin Okafor\n"})
    assert not ev["exports/kestrel_batch.csv#row:0"].hospital_reliable


def test_pass1_new7_end_to_end_blank_facility_row_still_links_within_reliable_hospital(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "kestrel_hospital/register.csv": (
                "Facility,MRN,Patient Name\nKestrel Hospital,MRN-55501,Tamsin Okafor\n,MRN-55502,Idris Halloran\n"
            ),
            "kestrel_hospital/ward.csv": "MRN,Patient Name\nMRN-55502,Idris Halloran\n",
        },
    )
    assert _same(recs, "kestrel_hospital/register.csv#row:1", "kestrel_hospital/ward.csv#row:0")
    assert not _same(recs, "kestrel_hospital/register.csv#row:0", "kestrel_hospital/register.csv#row:1")


def test_new5_nested_facility_name_metadata_is_the_document_issuer(tmp_path):
    doc = {
        "facility": {"name": "Kestrel Hospital", "address": "Ward Road"},
        "patients": [{"mrn": "MRN-55501", "name": "Tamsin Okafor"}, {"mrn": "MRN-55502", "name": "Idris Halloran"}],
    }
    ev = _evidence(tmp_path, {"exports/batch.json": json.dumps(doc)})
    for loc in ("/patients/0", "/patients/1"):
        assert ev[f"exports/batch.json#{loc}"].hospital == "kestrel"
        assert ev[f"exports/batch.json#{loc}"].hospital_reliable


def test_new5_sparse_nested_per_record_facility_does_not_leak_to_other_records(tmp_path):
    doc = {
        "patients": [
            {"facility": {"name": "Kestrel Hospital"}, "mrn": "MRN-55501", "name": "Tamsin Okafor"},
            {"mrn": "MRN-55501", "name": "Tamsin Okafor"},
        ]
    }
    ev = _evidence(tmp_path, {"exports/batch.json": json.dumps(doc)})
    assert ev["exports/batch.json#/patients/0"].hospital == "kestrel"
    assert ev["exports/batch.json#/patients/1"].hospital != "kestrel"
    assert not ev["exports/batch.json#/patients/1"].hospital_reliable


@pytest.mark.parametrize(
    "meta",
    [
        {"provider": "MedLink Data Aggregator"},
        {"source": {"provider": "CareBridge Health Exchange"}},
        {"provider": {"name": "Nimbus Records Platform"}},
    ],
)
def test_new5_aggregator_provider_is_never_a_verified_hospital(tmp_path, meta):
    doc = {**meta, "patients": [{"mrn": "MRN-55501", "name": "Tamsin Okafor"}]}
    ev = _evidence(tmp_path, {"exports/batch.json": json.dumps(doc)})["exports/batch.json#/patients/0"]
    assert not ev.hospital_reliable


def test_new5_aggregator_exports_from_different_sources_do_not_merge_on_generic_mrn(tmp_path):
    a = {"provider": "MedLink Data Aggregator", "patients": [{"mrn": "MRN-55501", "name": "Tamsin Okafor"}]}
    _, recs = _run_link(
        tmp_path,
        {"exports/pull_one.json": json.dumps(a), "exports/pull_two.json": json.dumps(a).replace("pull", "x")},
    )
    assert not _same(recs, "exports/pull_one.json#/patients/0", "exports/pull_two.json#/patients/0")


def test_new5_multiple_facilities_in_one_json_make_document_scope_unreliable(tmp_path):
    doc = {
        "hospital": "Kestrel Hospital",
        "facility": "Wrenfield Hospital",
        "patients": [{"mrn": "MRN-55501", "name": "Tamsin Okafor"}],
    }
    ev = _evidence(tmp_path, {"exports/batch.json": json.dumps(doc)})["exports/batch.json#/patients/0"]
    assert not ev.hospital_reliable
    assert ev.hospital not in ("kestrel", "wrenfield")


def test_new5_referral_facility_is_not_the_issuer(tmp_path):
    doc = {
        "hospital": "Kestrel Hospital",
        "referral": {"facility": {"name": "Wrenfield Hospital"}},
        "patients": [{"mrn": "MRN-55501", "name": "Tamsin Okafor"}],
    }
    ev = _evidence(tmp_path, {"exports/batch.json": json.dumps(doc)})["exports/batch.json#/patients/0"]
    assert ev.hospital == "kestrel"
    assert ev.hospital_reliable


def test_new5_positive_unanimous_per_record_facility_still_links(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "exports/batch.csv": (
                "Facility,MRN,Patient Name\n"
                "Kestrel Hospital,MRN-55501,Tamsin Okafor\nKestrel Hospital,MRN-55501,Tamsin Okafor\n"
            ),
        },
    )
    assert _same(recs, "exports/batch.csv#row:0", "exports/batch.csv#row:1")


# =========================================================================== NEW-6A: contract parsing by content
def test_new6a_json_content_under_csv_tsv_dat_extensions_is_located_by_pointer(tmp_path):
    payload = json.dumps({"patients": [{"name": "PSN-4MZ8XH"}]})
    for ext in (".csv", ".tsv", ".dat", ".json"):
        p = tmp_path / f"out{ext}"
        p.write_text(payload, encoding="utf-8")
        parsed = _ParsedOutput.load(p)
        assert parsed is not None
        assert "PSN-4MZ8XH" in (parsed.record_text("/patients/0") or "")


def test_new6a_valid_csv_tsv_and_malformed_content():
    csv_text = "Patient,Note\nPSN-4MZ8XH,stable\nPSN-9TQ3RW,review\n"
    assert _ParsedOutput(csv_text, ".csv").record_text("row:1") == "PSN-9TQ3RW\x1freview"
    tsv_text = "Patient\tNote\nPSN-4MZ8XH\tstable, afebrile\n"
    assert _ParsedOutput(tsv_text, ".tsv").record_text("row:0") == "PSN-4MZ8XH\x1fstable, afebrile"
    broken = _ParsedOutput('{"patients": [', ".csv")
    assert broken.record_text("/patients/0") is None
    assert _ParsedOutput(csv_text, ".csv").record_text("row:9") is None


def test_new6a_end_to_end_json_in_csv_file_passes_self_check(tmp_path):
    doc = {
        "hospital": "Kestrel Hospital",
        "patients": [
            {"uhid": "KSR-26-004417", "name": "Tamsin Okafor", "aadhaar": AAD_1},
            {"uhid": "KSR-26-004418", "name": "Idris Halloran", "aadhaar": AAD_2},
        ],
    }
    summary, recs = _run_link(tmp_path, {"exports/batch.csv": json.dumps(doc)})
    assert summary.ok
    assert recs["exports/batch.csv#/patients/0"] is not None


def _release(tmp_path: Path, rows: list[str], claims: list[str | None]) -> tuple[Path, Path, dict]:
    out = tmp_path / "rel"
    (out / "sanitized").mkdir(parents=True)
    (out / "sanitized" / "reg.csv").write_text("Patient,Note\n" + "\n".join(rows) + "\n", encoding="utf-8")
    lines = [json.dumps({"file": "sanitized/reg.csv", "loc": f"row:{i}", "patient": c}) for i, c in enumerate(claims)]
    rj = out / "records.jsonl"
    rj.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {"counts": {"records_linked": sum(c is not None for c in claims)}}
    return out, rj, report


def test_new6a_literal_psn_text_is_not_foreign_but_real_issued_pseudonym_is(tmp_path):
    out, rj, rep = _release(tmp_path / "lit", ["PSN-4MZ8XH,code PSN-7RW2KD batch"], ["PSN-4MZ8XH"])
    assert _check_records_pseudonyms(out, rj, rep, issued_pseudonyms=frozenset({"PSN-4MZ8XH"})) == []
    out, rj, rep = _release(
        tmp_path / "real", ["PSN-4MZ8XH,see PSN-9TQ3RW", "PSN-9TQ3RW,ok"], ["PSN-4MZ8XH", "PSN-9TQ3RW"]
    )
    problems = _check_records_pseudonyms(out, rj, rep, issued_pseudonyms=frozenset({"PSN-4MZ8XH", "PSN-9TQ3RW"}))
    assert any("another patient's pseudonym" in p for p in problems)


# =========================================================================== NEW-6B: partial evidence
@pytest.mark.parametrize(
    "field",
    [
        {"ages": frozenset({41})},
        {"genders": frozenset({"F"})},
        {"birth_years": frozenset({1983})},
        {"villages": frozenset({"pinewick"})},
        {"districts": frozenset({"harrowdale"})},
        {"insurance_id": frozenset({"ESIC4471902233"})},
        {"email": frozenset({"t.okafor@example.test"})},
        {"pins": frozenset({"560071"})},
        {"relative_global_ids": frozenset({"aadhaar|" + AAD_2})},
        {"raw_mrns": frozenset({("MRN-55501", False)})},
    ],
)
def test_new6b_any_populated_identity_field_counts_as_evidence(field):
    assert _rec("r", **field).has_any_evidence
    assert not _rec("r").has_any_evidence


def _bundle(*patients: dict) -> str:
    return json.dumps(
        {
            "resourceType": "Bundle",
            "id": "b-pass2",
            "type": "collection",
            "entry": [
                {
                    "fullUrl": f"urn:uuid:7e1c0d52-0000-4000-8000-00000000000{i}",
                    "resource": {"resourceType": "Patient", **p},
                }
                for i, p in enumerate(patients)
            ],
        }
    )


_FULL = {
    "id": "p0",
    "name": [{"given": ["Tamsin"], "family": "Okafor"}],
    "gender": "female",
    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_1}],
}


@pytest.mark.parametrize(
    "partial",
    [
        {"id": "p1", "gender": "male"},
        {"id": "p1", "telecom": [{"system": "phone", "value": "9811177720"}]},
        {"id": "p1", "birthDate": "2019-05-14"},
    ],
)
def test_new6b_partial_second_patient_makes_bundle_ambiguous(tmp_path, partial):
    ev = _evidence(tmp_path, {"fhir/bundle.json": _bundle(_FULL, partial)})["fhir/bundle.json#doc"]
    assert ev.ambiguous_doc


def test_new6b_positive_partial_duplicate_of_same_patient_is_not_rejected(tmp_path):
    dup = {"id": "p1", "name": [{"given": ["Tamsin"], "family": "Okafor"}], "gender": "female"}
    ev = _evidence(tmp_path, {"fhir/bundle.json": _bundle(_FULL, dup)})["fhir/bundle.json#doc"]
    assert not ev.ambiguous_doc
    assert AAD_1 in ev.aadhaar


def test_new6b_positive_evidence_free_patient_stub_is_ignored(tmp_path):
    ev = _evidence(tmp_path, {"fhir/bundle.json": _bundle(_FULL, {"id": "p1", "active": True})})["fhir/bundle.json#doc"]
    assert not ev.ambiguous_doc


# =========================================================================== NEW-7A: E/O initials
@pytest.mark.parametrize(
    ("a", "b", "compatible"),
    [
        ("Evander Vance", "E. Vance", True),
        ("Eshaan Rao", "E. Rao", True),
        ("Omar Kadri", "O. Kadri", True),
        ("Evander Vance", "A. Vance", False),
        ("Omar Kadri", "A. Kadri", False),
        ("Bilal Kadri", "O. Kadri", False),
        ("Arun Vance", "E. Vance", False),
        ("Kiran Vance", "Karan Vance", False),
    ],
)
def test_new7a_vowel_initials_match_their_names_and_keep_vowel_distinctions(a, b, compatible):
    grade = compare_names(_name(a), _name(b))
    assert (grade is not NameGrade.CONFLICT) is compatible
    if compatible:
        assert grade is NameGrade.ABBREVIATED_FULL


def test_new7a_initial_only_given_name_is_undecided_not_a_conflict_with_a_first_name():
    assert compare_names(_name("Nolan"), _name("N. Vermeer")) is NameGrade.NONE
    assert compare_names(_name("Nolan"), _name("K. Vermeer")) is NameGrade.CONFLICT


def test_new7a_end_to_end_vowel_initial_under_shared_aadhaar(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/clinic_a.csv": f"Patient Name,Aadhaar\nOmar Kadri,{AAD_3}\nEvander Vance,{AAD_1}\n",
            "reg/clinic_b.csv": f"Patient Name,Aadhaar\nO. Kadri,{AAD_3}\nE. Vance,{AAD_1}\n",
            "reg/clinic_c.csv": f"Patient Name,Aadhaar\nBilal Kadri,{AAD_2}\n",
            "reg/clinic_d.csv": f"Patient Name,Aadhaar\nO. Kadri,{AAD_2}\n",
        },
    )
    assert _same(recs, "reg/clinic_a.csv#row:0", "reg/clinic_b.csv#row:0")
    assert _same(recs, "reg/clinic_a.csv#row:1", "reg/clinic_b.csv#row:1")
    assert not _same(recs, "reg/clinic_c.csv#row:0", "reg/clinic_d.csv#row:0")


# =========================================================================== NEW-7B: multiple ABHA addresses
def test_new7b_multiple_abha_addresses_do_not_split_shared_aadhaar_or_abha_number(tmp_path):
    _, recs = _run_link(
        tmp_path,
        {
            "reg/clinic_a.csv": f"Patient Name,Aadhaar,ABHA Address\nTamsin Okafor,{AAD_1},tamsin.okafor@abdm\n",
            "reg/clinic_b.csv": f"Patient Name,Aadhaar,ABHA Address\nTamsin Okafor,{AAD_1},t.okafor88@abdm\n",
        },
    )
    assert _same(recs, "reg/clinic_a.csv#row:0", "reg/clinic_b.csv#row:0")
    a = ClusterProfile.from_record(
        _rec("a", abha_number=frozenset({"91-4417-2093-6658"}), abha_address=frozenset({"x@abdm"}))
    )
    b = ClusterProfile.from_record(
        _rec("b", abha_number=frozenset({"91-4417-2093-6658"}), abha_address=frozenset({"y@abdm"}))
    )
    assert compare_profiles(a, b).outcome is MatchOutcome.CONFIDENT_MATCH


def test_new7b_different_abha_addresses_without_shared_validated_id_still_contradict():
    a = ClusterProfile.from_record(_rec("a", name="Tamsin Okafor", abha_address=frozenset({"x@abdm"})))
    b = ClusterProfile.from_record(_rec("b", name="Tamsin Okafor", abha_address=frozenset({"y@abdm"})))
    assert compare_profiles(a, b).outcome is MatchOutcome.CONFLICT


def test_new7b_hard_contradiction_still_splits_shared_aadhaar_with_two_abha_addresses():
    a = ClusterProfile.from_record(
        _rec("a", aadhaar=frozenset({AAD_1}), abha_address=frozenset({"x@abdm"}), genders=frozenset({"F"}))
    )
    b = ClusterProfile.from_record(
        _rec("b", aadhaar=frozenset({AAD_1}), abha_address=frozenset({"y@abdm"}), genders=frozenset({"M"}))
    )
    assert compare_profiles(a, b).outcome is MatchOutcome.CONFLICT
