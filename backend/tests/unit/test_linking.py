"""Unit tests for Phase 3 identity resolution: normalisation, matching, clustering, pseudonyms.

All names, identifiers, and hospitals are completely invented synthetic fixtures.
"""

from __future__ import annotations

import hashlib
import pickle
import random
import re

import pytest

from clinveil.detection import caches
from clinveil.linking.cluster import MAX_NAME_BLOCK, cluster_records
from clinveil.linking.linker import resolve_identities
from clinveil.linking.matcher import ClusterProfile, compare_profiles
from clinveil.linking.models import (
    DateEvidence,
    LinkingStats,
    MatchOutcome,
    NameGrade,
    RecordEvidence,
    RecordKey,
)
from clinveil.linking.normalize import (
    build_name_evidence,
    combine_name_parts,
    compare_names,
    extract_ages,
    extract_genders,
    normalize_aadhaar,
    normalize_abha_number,
    normalize_dob,
    normalize_hospital,
    normalize_mrn,
    normalize_phone,
    normalize_village,
    strict_name_token,
)
from clinveil.linking.pseudonyms import assign_pseudonyms, canonical_cluster_key
from clinveil.privacy.pseudonym import ALPHABET, Pseudonymizer
from clinveil.security.secrets import ReleaseSecret

PSN_RE = re.compile(rf"^PSN-[{ALPHABET}]{{6}}$")


def _make_verhoeff_aadhaar(prefix11: str) -> str:
    """Compute the 12th Verhoeff check digit for a synthetic 11-digit prefix."""
    from clinveil.detection.identifiers import verhoeff_valid

    for d in "0123456789":
        cand = prefix11 + d
        if verhoeff_valid(cand):
            return cand
    raise AssertionError("no valid check digit found")


SYNTH_AADHAAR_1 = _make_verhoeff_aadhaar("23456789012")
SYNTH_AADHAAR_2 = _make_verhoeff_aadhaar("34567890123")
SYNTH_AADHAAR_BAD = SYNTH_AADHAAR_1[:-1] + ("0" if SYNTH_AADHAAR_1[-1] != "0" else "1")


def _ev(
    rel: str,
    loc: str = "doc",
    *,
    hospital: str | None = None,
    is_lab: bool = False,
    aadhaar: str | None = None,
    abha: str | None = None,
    mrn: str | None = None,
    name: str | None = None,
    relative: str | None = None,
    phone: str | None = None,
    dob: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    village: str | None = None,
) -> RecordEvidence:
    local_ids = set()
    local_cores = set()
    raw_mrns = set()
    if mrn:
        norm = normalize_mrn(mrn, None if is_lab else hospital)
        assert norm is not None
        scope, canon, core, dist = norm
        local_ids.add((scope, canon))
        if len(core) >= 5:
            local_cores.add((scope, core))
        raw_mrns.add((canon, dist))
    dobs = set()
    years = set()
    if dob:
        de, by = normalize_dob(dob)
        if de:
            dobs.add(de)
        if by:
            years.add(by)
    pnames = ()
    if name:
        ne = build_name_evidence(name, confidence=0.95, source="field")
        if ne:
            pnames = (ne,)
    rnames = ()
    if relative:
        re_ev = build_name_evidence(relative, confidence=0.9, source="relation_marker")
        if re_ev:
            rnames = (re_ev,)
    return RecordEvidence(
        record=RecordKey(rel, loc),
        hospital=hospital,
        is_external_lab=is_lab,
        aadhaar=frozenset([aadhaar]) if aadhaar else frozenset(),
        abha_number=frozenset([abha]) if abha else frozenset(),
        local_ids=frozenset(local_ids),
        local_id_cores=frozenset(local_cores),
        raw_mrns=frozenset(raw_mrns),
        patient_names=pnames,
        relative_names=rnames,
        phones=frozenset([phone]) if phone else frozenset(),
        dobs=frozenset(dobs),
        birth_years=frozenset(years),
        ages=frozenset([age]) if age is not None else frozenset(),
        genders=frozenset([gender]) if gender else frozenset(),
        villages=frozenset([v]) if (village and (v := normalize_village(village))) else frozenset(),
    )


# --------------------------------------------------------------------------- normalisation
def test_strict_name_normalisation_cross_script_and_variants():
    assert strict_name_token("प्रणव") == strict_name_token("Pranav")
    assert strict_name_token("Tripathy") == strict_name_token("Tripathi") == strict_name_token("त्रिपाठी")
    assert strict_name_token("Chaudhary") == strict_name_token("Choudhary")
    assert strict_name_token("Mohammad") == strict_name_token("Mohd.") == strict_name_token("मोहम्मद")
    assert strict_name_token("Bimla") == strict_name_token("Vimla")
    assert strict_name_token("Neeta") == strict_name_token("Nita") == strict_name_token("नीता")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Kiran Solanki", "Karan Solanki"),
        ("Sita Deshmukh", "Satya Deshmukh"),
        ("Alok Sengupta", "Alka Sengupta"),
        ("Rohan Kulkarni", "Mohan Kulkarni"),
        ("Sunita Rathore", "Anita Rathore"),
    ],
)
def test_coarse_transliteration_collisions_stay_distinct(a, b):
    na = build_name_evidence(a, confidence=0.95, source="field")
    nb = build_name_evidence(b, confidence=0.95, source="field")
    assert na is not None and nb is not None
    assert compare_names(na, nb) is NameGrade.CONFLICT


def test_name_comparison_handles_order_abbreviations_and_schwa():
    n_full = build_name_evidence("Mr. Pranav Kulkarni", confidence=0.95, source="field")
    n_rev = build_name_evidence("Kulkarni, Pranav", confidence=0.95, source="field")
    n_deva = build_name_evidence("श्री प्रणव कुलकर्णी जी", confidence=0.95, source="patient_label")
    n_abbr = build_name_evidence("P. Kulkarni", confidence=0.9, source="field")
    n_init_only = build_name_evidence("P. K.", confidence=0.9, source="field")
    n_split = combine_name_parts(["Pranav", "Kulkarni"], confidence=0.95, source="structured_split")
    assert n_full and n_rev and n_deva and n_abbr and n_init_only and n_split
    assert compare_names(n_full, n_rev) is NameGrade.EXACT_FULL
    assert compare_names(n_full, n_deva) in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
    assert compare_names(n_full, n_split) is NameGrade.EXACT_FULL
    assert compare_names(n_full, n_abbr) is NameGrade.ABBREVIATED_FULL
    assert compare_names(n_full, n_init_only) is NameGrade.NONE

    k1 = build_name_evidence("Kamlesh Rathore", confidence=0.95, source="field")
    k2 = build_name_evidence("Kamalesh Rathore", confidence=0.95, source="field")
    assert k1 and k2 and compare_names(k1, k2) is NameGrade.VARIANT_FULL


def test_identifier_validation_and_hospital_scoping():
    assert normalize_aadhaar(SYNTH_AADHAAR_1) == SYNTH_AADHAAR_1
    assert normalize_aadhaar(SYNTH_AADHAAR_BAD) is None
    assert normalize_aadhaar("XXXX XXXX 0123") is None
    assert normalize_aadhaar("1234 5678 9012") is None  # starts with 1
    assert normalize_abha_number("91-2233-4455-6677") == "91223344556677"
    assert normalize_phone("+91 98201 11223") == "9820111223"
    assert normalize_phone("098201-11223") == "9820111223"
    assert normalize_phone("९८२०१११२२३") == "9820111223"

    ha, _ = normalize_hospital("Hospital-A")
    hb, _ = normalize_hospital("Hospital-B")
    assert ha != hb
    ma = normalize_mrn("MRN-12345", ha)
    mb = normalize_mrn("MRN-12345", hb)
    assert ma and mb and ma[0] != mb[0]  # hospital-namespaced scopes differ


def test_dob_age_and_gender_extraction():
    d_dmy, y1 = normalize_dob("14/05/1982")
    d_mdy, y2 = normalize_dob("05/14/1982", month_first_hint=True)
    d_iso, y3 = normalize_dob("1982-05-14")
    assert d_dmy and d_mdy and d_iso
    assert d_dmy.matches(d_mdy) and d_dmy.matches(d_iso) and y1 == y2 == y3 == 1982
    assert normalize_dob("04/05/1982")[0].matches(DateEvidence((1982, 4, 5), None))
    assert extract_ages("Age: 47, 47/M. History x 12 yrs, 7 yrs back.") == {47}
    assert extract_genders("47/M, S/o Mohan") == {"M"}
    assert extract_genders("Female", structured=True) == {"F"}


# --------------------------------------------------------------------------- matching & conflict vetoes
def test_cross_hospital_generic_mrn_never_merges():
    a = ClusterProfile.from_record(
        _ev("a.csv", "row:0", hospital="hospital_a", mrn="MRN-12345", name="Pranav Kulkarni")
    )
    b = ClusterProfile.from_record(
        _ev("b.csv", "row:0", hospital="hospital_b", mrn="MRN-12345", name="Devendra Rathore")
    )
    dec = compare_profiles(a, b)
    assert dec.outcome is MatchOutcome.CONFLICT

    # Even with identical full name, two DIFFERENT hospitals' generic MRN-12345 gives NO scoped ID match!
    a2 = ClusterProfile.from_record(_ev("a.csv", "row:0", hospital="hospital_a", mrn="MRN-12345", name="Bhanu Pratap"))
    b2 = ClusterProfile.from_record(_ev("b.csv", "row:0", hospital="hospital_b", mrn="MRN-12345", name="Bhanu Pratap"))
    dec2 = compare_profiles(a2, b2)
    assert dec2.outcome is MatchOutcome.INSUFFICIENT_EVIDENCE


def test_family_members_and_twins_and_homonyms_blocked():
    # Family sharing a phone
    fam1 = ClusterProfile.from_record(_ev("a.csv", "row:0", name="Kavya Deshmukh", phone="9820111223"))
    fam2 = ClusterProfile.from_record(_ev("a.csv", "row:1", name="Raghav Deshmukh", phone="9820111223"))
    assert compare_profiles(fam1, fam2).outcome is MatchOutcome.CONFLICT

    # Twins sharing surname, DOB, relative, village
    tw1 = ClusterProfile.from_record(
        _ev("a.csv", "row:0", name="Nikhil Sengupta", dob="2005-08-19", relative="Vijay Sengupta", village="Rampur")
    )
    tw2 = ClusterProfile.from_record(
        _ev("b.csv", "row:0", name="Akhil Sengupta", dob="2005-08-19", relative="Vijay Sengupta", village="Rampur")
    )
    assert compare_profiles(tw1, tw2).outcome is MatchOutcome.CONFLICT

    # Homonyms with same full name, different relative/village/age
    h1 = ClusterProfile.from_record(
        _ev("a.csv", "row:0", name="Bhanu Pratap", relative="Harish Pratap", village="Alipur", age=44)
    )
    h2 = ClusterProfile.from_record(
        _ev("b.csv", "row:0", name="Bhanu Pratap", relative="Dinesh Pratap", village="Sonpur", age=58)
    )
    dec = compare_profiles(h1, h2)
    assert dec.outcome is MatchOutcome.CONFLICT
    assert (
        "conflict_relative" in dec.conflicts and "conflict_village" in dec.conflicts and "conflict_age" in dec.conflicts
    )

    # Same name & birth year, conflicting valid Aadhaar
    c1 = ClusterProfile.from_record(
        _ev("a.csv", "row:0", name="Zoya Qureshi", dob="1990-03-11", aadhaar=SYNTH_AADHAAR_1)
    )
    c2 = ClusterProfile.from_record(
        _ev("b.csv", "row:0", name="Zoya Qureshi", dob="1990-03-11", aadhaar=SYNTH_AADHAAR_2)
    )
    dec_id = compare_profiles(c1, c2)
    assert dec_id.outcome is MatchOutcome.CONFLICT and "conflict_aadhaar" in dec_id.conflicts


def test_no_transitive_weak_bridge_across_conflicting_clusters():
    """A strongly matches B; B shares name+phone with C; A and C have conflicting Aadhaar -> never merge A, B, C."""
    rec_a = _ev(
        "h1.csv",
        "row:0",
        hospital="sunrise",
        mrn="SUN-101",
        aadhaar=SYNTH_AADHAAR_1,
        name="Pranav Kulkarni",
        phone="9820111223",
    )
    rec_b = _ev("h1.csv", "row:1", hospital="sunrise", mrn="SUN-101", name="Pranav Kulkarni", phone="9820111223")
    rec_c = _ev(
        "h2.csv",
        "row:0",
        hospital="lotus",
        mrn="LOT-202",
        aadhaar=SYNTH_AADHAAR_2,
        name="Pranav Kulkarni",
        phone="9820111223",
    )
    psn = Pseudonymizer(ReleaseSecret(b"transitive-test"), 180)
    res = resolve_identities([rec_a, rec_b, rec_c], psn)
    pa = res.pseudonyms[rec_a.record]
    pb = res.pseudonyms[rec_b.record]
    pc = res.pseudonyms[rec_c.record]
    assert pa == pb
    assert pc != pa
    assert res.stats.merges_blocked_by_conflict >= 1


def test_blocking_cap_skips_pathological_name_block_safely():
    """A pathological block > MAX_NAME_BLOCK distinct clusters must be capped, not O(N^2) merged."""
    evs = [
        _ev(
            f"f_{i:03d}.csv",
            "row:0",
            hospital=f"hosp_{i}",
            mrn=f"ID-{i:04d}",
            name="Rameshwar Solanki",
            village=f"Vill{i}",
            age=20 + (i % 60),
        )
        for i in range(MAX_NAME_BLOCK + 10)
    ]
    clusters, stats = cluster_records(evs)
    assert len(clusters) == MAX_NAME_BLOCK + 10
    assert stats.blocks_capped_ambiguous >= 1


# --------------------------------------------------------------------------- cryptographic & safety invariants
def test_pseudonyms_order_independent_collision_safe_and_secret_keyed():
    evs = [
        _ev("z_file.csv", "row:0", hospital="sunrise", mrn="SUN-1001", aadhaar=SYNTH_AADHAAR_1, name="Pranav Kulkarni"),
        _ev("a_file.csv", "row:3", hospital="lotus", mrn="LOT-2002", aadhaar=SYNTH_AADHAAR_1, name="प्रणव कुलकर्णी"),
        _ev("m_file.csv", "row:1", hospital="sunrise", mrn="SUN-1002", aadhaar=SYNTH_AADHAAR_2, name="Zoya Qureshi"),
    ]
    psn1 = Pseudonymizer(ReleaseSecret(b"secret-alpha"), 180)
    psn2 = Pseudonymizer(ReleaseSecret(b"secret-beta"), 180)
    r_base = resolve_identities(evs, psn1)
    assert r_base.pseudonyms[evs[0].record] == r_base.pseudonyms[evs[1].record]
    assert r_base.pseudonyms[evs[0].record] != r_base.pseudonyms[evs[2].record]
    assert all(PSN_RE.fullmatch(v) for v in r_base.pseudonyms.values())

    # Shuffled input order must yield IDENTICAL pseudonyms
    rng = random.Random(42)
    for _ in range(5):
        shuffled = list(evs)
        rng.shuffle(shuffled)
        r_shuf = resolve_identities(shuffled, psn1)
        assert r_shuf.pseudonyms == r_base.pseudonyms

    # Different secret -> completely different pseudonyms
    r_other = resolve_identities(evs, psn2)
    assert set(r_base.pseudonyms.values()).isdisjoint(set(r_other.pseudonyms.values()))

    # Not an unkeyed hash of raw PII
    for psn_val in r_base.pseudonyms.values():
        code = psn_val[4:].lower()
        for raw in (SYNTH_AADHAAR_1, SYNTH_AADHAAR_2, "Pranav Kulkarni", "SUN-1001"):
            for algo in ("md5", "sha1", "sha256", "sha512"):
                assert code not in hashlib.new(algo, raw.encode()).hexdigest()


def test_pseudonym_collision_rederivation_with_counter():
    class CollidingPseudonymizer:
        def pseudonym(self, patient_key: str, *, attempt: int = 0) -> str:
            return "PSN-AAAAAA" if attempt == 0 else f"PSN-AAAA{attempt:02d}"

    c1 = ClusterProfile.from_record(_ev("a.csv", "row:0", aadhaar=SYNTH_AADHAAR_1))
    c2 = ClusterProfile.from_record(_ev("b.csv", "row:0", aadhaar=SYNTH_AADHAAR_2))
    assert canonical_cluster_key(c1) != canonical_cluster_key(c2)
    stats = LinkingStats(records_total=2)
    mapping, _ = assign_pseudonyms([c1, c2], CollidingPseudonymizer(), stats)  # type: ignore[arg-type]
    assert len(set(mapping.values())) == 2
    assert stats.pseudonym_collisions_resolved == 1


def test_evidence_objects_redact_repr_refuse_pickling_and_clear_caches():
    ev = _ev("a.csv", "row:0", aadhaar=SYNTH_AADHAAR_1, name="Pranav Kulkarni", phone="9820111223")
    prof = ClusterProfile.from_record(ev)
    for obj in (ev, ev.patient_names[0], prof):
        rep = repr(obj)
        assert "Pranav" not in rep and "Kulkarni" not in rep and SYNTH_AADHAAR_1 not in rep and "9820111223" not in rep
        with pytest.raises(TypeError):
            pickle.dumps(obj)
    strict_name_token("Pranav")
    assert caches.total_cached_entries() > 0
    caches.clear_all()
    assert caches.total_cached_entries() == 0
