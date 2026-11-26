"""Evidence-based pairwise and cluster-level identity comparison with hard conflict vetoes.

Every decision returns a PII-free :class:`PairDecision` carrying an explicit
:class:`MatchOutcome`, :class:`MatchStrength`, supporting reason codes, and conflict codes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clinveil.detection.identifiers import mrn_digit_core
from clinveil.linking.models import (
    DateEvidence,
    MatchOutcome,
    MatchStrength,
    NameEvidence,
    NameGrade,
    PairDecision,
    RecordEvidence,
    RecordKey,
)
from clinveil.linking.normalize import best_name_grade, id_type, is_authoritative_core

_FULL_MATCH_GRADES = frozenset({NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL, NameGrade.ABBREVIATED_FULL})
_COMPATIBLE_GRADES = _FULL_MATCH_GRADES | frozenset({NameGrade.FIRST_ONLY_MATCH})


@dataclass(slots=True)
class ClusterProfile:
    """Aggregate identity evidence across all records currently in one cluster (memory-only)."""

    members: list[RecordKey] = field(default_factory=list)
    hospitals: set[str] = field(default_factory=set)
    #: Hospitals reliably established for this cluster (R5): only these can prove "different issuer".
    reliable_hospitals: set[str] = field(default_factory=set)
    has_non_lab_hospital: bool = False
    is_external_lab_only: bool = True
    aadhaar: set[str] = field(default_factory=set, repr=False)
    abha_number: set[str] = field(default_factory=set, repr=False)
    abha_address: set[str] = field(default_factory=set, repr=False)
    pan: set[str] = field(default_factory=set, repr=False)
    insurance_id: set[str] = field(default_factory=set, repr=False)
    email: set[str] = field(default_factory=set, repr=False)
    local_ids: set[tuple[str, str]] = field(default_factory=set, repr=False)
    local_id_cores: set[tuple[str, str]] = field(default_factory=set, repr=False)
    raw_mrns: set[tuple[str, bool]] = field(default_factory=set, repr=False)
    patient_names: list[NameEvidence] = field(default_factory=list, repr=False)
    relative_names: list[NameEvidence] = field(default_factory=list, repr=False)
    phones: set[str] = field(default_factory=set, repr=False)
    dobs: set[DateEvidence] = field(default_factory=set, repr=False)
    birth_years: set[int] = field(default_factory=set, repr=False)
    ages: set[int] = field(default_factory=set, repr=False)
    genders: set[str] = field(default_factory=set, repr=False)
    villages: set[str] = field(default_factory=set, repr=False)
    districts: set[str] = field(default_factory=set, repr=False)
    pins: set[str] = field(default_factory=set, repr=False)
    relative_global_ids: set[str] = field(default_factory=set, repr=False)
    ambiguous_doc: bool = False
    _seen_pnames: set[tuple[str, ...]] = field(default_factory=set, repr=False)
    _seen_rnames: set[tuple[str, ...]] = field(default_factory=set, repr=False)

    def __repr__(self) -> str:
        return f"ClusterProfile(members={len(self.members)}, strong={self.has_strong_anchor})"

    def __reduce__(self) -> Any:
        raise TypeError("ClusterProfile cannot be serialised")

    @classmethod
    def from_record(cls, ev: RecordEvidence, reliable_slugs: frozenset[str] = frozenset()) -> ClusterProfile:
        """``reliable_slugs``: hospital slugs established reliably anywhere in the run, so a file-stem
        guess that matches a real facility elsewhere (``sanjeevani_registration.csv``) also counts."""
        own = ev.hospital if (ev.hospital and not ev.is_external_lab) else None
        prof = cls(
            members=[ev.record],
            reliable_hospitals={own} if own and (ev.hospital_reliable or own in reliable_slugs) else set(),
            hospitals={ev.hospital} if (ev.hospital and not ev.is_external_lab) else set(),
            has_non_lab_hospital=bool(ev.hospital and not ev.is_external_lab),
            is_external_lab_only=ev.is_external_lab or ev.hospital is None,
            aadhaar=set(ev.aadhaar),
            abha_number=set(ev.abha_number),
            abha_address=set(ev.abha_address),
            pan=set(ev.pan),
            insurance_id=set(ev.insurance_id),
            email=set(ev.email),
            local_ids=set(ev.local_ids),
            local_id_cores=set(ev.local_id_cores),
            raw_mrns=set(ev.raw_mrns),
            phones=set(ev.phones),
            dobs=set(ev.dobs),
            birth_years=set(ev.all_birth_years()),
            ages=set(ev.ages),
            genders=set(ev.genders),
            villages=set(ev.villages),
            districts=set(ev.districts),
            pins=set(ev.pins),
            relative_global_ids=set(ev.relative_global_ids),
            ambiguous_doc=ev.ambiguous_doc,
        )
        for n in ev.patient_names:
            prof._add_pname(n)
        for n in ev.relative_names:
            prof._add_rname(n)
        return prof

    def _add_pname(self, n: NameEvidence) -> None:
        if n.strict_tokens not in self._seen_pnames:
            self._seen_pnames.add(n.strict_tokens)
            self.patient_names.append(n)

    def _add_rname(self, n: NameEvidence) -> None:
        if n.strict_tokens not in self._seen_rnames:
            self._seen_rnames.add(n.strict_tokens)
            self.relative_names.append(n)

    def absorb(self, other: ClusterProfile) -> None:
        self.members.extend(other.members)
        self.members.sort()
        self.hospitals |= other.hospitals
        self.reliable_hospitals |= other.reliable_hospitals
        self.has_non_lab_hospital = self.has_non_lab_hospital or other.has_non_lab_hospital
        self.is_external_lab_only = self.is_external_lab_only and other.is_external_lab_only
        self.aadhaar |= other.aadhaar
        self.abha_number |= other.abha_number
        self.abha_address |= other.abha_address
        self.pan |= other.pan
        self.insurance_id |= other.insurance_id
        self.email |= other.email
        self.local_ids |= other.local_ids
        self.local_id_cores |= other.local_id_cores
        self.raw_mrns |= other.raw_mrns
        for n in other.patient_names:
            self._add_pname(n)
        for n in other.relative_names:
            self._add_rname(n)
        self.phones |= other.phones
        self.dobs |= other.dobs
        self.birth_years |= other.birth_years
        self.ages |= other.ages
        self.genders |= other.genders
        self.villages |= other.villages
        self.districts |= other.districts
        self.pins |= other.pins
        self.relative_global_ids |= other.relative_global_ids
        self.ambiguous_doc = self.ambiguous_doc or other.ambiguous_doc

    @property
    def has_global_id(self) -> bool:
        """Person-unique identifiers only (insurance and e-mail are household-shareable, R3)."""
        return bool(self.aadhaar or self.abha_number or self.abha_address or self.pan)

    def own_global_ids(self) -> set[str]:
        """The patient's own person-unique IDs in the ``relative_global_ids`` key format."""
        return (
            {"aadhaar|" + x for x in self.aadhaar}
            | {"abha|" + x for x in self.abha_number}
            | {"abhaa|" + x for x in self.abha_address}
            | {"pan|" + x for x in self.pan}
        )

    @property
    def has_strong_anchor(self) -> bool:
        return self.has_global_id or bool(self.local_ids)

    @property
    def has_full_patient_name(self) -> bool:
        return any(not n.is_single_token and not n.is_initial_only for n in self.patient_names)


# --------------------------------------------------------------------------- conflict checking
def _dob_matches(a: set[DateEvidence], b: set[DateEvidence]) -> bool:
    return any(da.matches(db) for da in a for db in b)


def _age_min_diff(a: set[int], b: set[int]) -> int:
    return min(abs(x - y) for x in a for y in b)


def _year_min_diff(a: set[int], b: set[int]) -> int:
    return min(abs(x - y) for x in a for y in b)


def _age_max_diff(a: set[int], b: set[int]) -> int:
    return max(abs(x - y) for x in a for y in b)


def _authoritative_ids_by_scope(c: ClusterProfile) -> dict[str, set[str]]:
    """Known-issuer scope -> the patient's own MRN/UHID keys (``type:digits``; admissions/visits excluded).

    Compared by type + last digit run without leading zeros, so ``UHID-0045123`` and
    ``UHID/45123`` are the same key (the veto errs towards NOT firing).
    """
    out: dict[str, set[str]] = {}
    for scope, canon in c.local_ids:
        if scope == "unscoped":
            continue
        t = id_type(canon)
        core = mrn_digit_core(canon).lstrip("0") or "0"
        key = f"{t}:{core}"
        if is_authoritative_core(key):
            out.setdefault(scope, set()).add(key)
    return out


def _distinct_mrns_same_issuer(a: ClusterProfile, b: ClusterProfile) -> bool:
    sa, sb = _authoritative_ids_by_scope(a), _authoritative_ids_by_scope(b)
    return any(sa[s].isdisjoint(sb[s]) for s in sa.keys() & sb.keys())


def _complete_linkage_conflicts(a: ClusterProfile, b: ClusterProfile) -> list[str]:
    """Weak-merge vetoes checked against EVERY member value, not the closest one (Phase 3.1).

    A cluster's evidence is the union of its members, so "closest value" checks become more
    permissive as a cluster grows (A=30, B=33 joined strongly; C=36 then looks only 3 years
    from B). For merges that rest on names and corroborators only, every pair must agree.
    """
    out: list[str] = []
    if a.ages and b.ages and _age_max_diff(a.ages, b.ages) > 3:
        out.append("conflict_age_span")
    if a.birth_years and b.birth_years and _age_max_diff(a.birth_years, b.birth_years) > 1:
        out.append("conflict_birth_year_span")
    if a.dobs and b.dobs and not all(da.matches(db) for da in a.dobs for db in b.dobs):
        out.append("conflict_dob_any")
    if a.genders and b.genders and len(a.genders | b.genders) > 1:
        out.append("conflict_gender_any")
    return out


def _full_names(names: list[NameEvidence]) -> tuple[NameEvidence, ...]:
    return tuple(n for n in names if not n.is_single_token and not n.is_initial_only)


def _names_phonetically_compatible(a: list[NameEvidence], b: list[NameEvidence]) -> bool:
    """Coarse consonant-skeleton compatibility used ONLY when an MRN or global ID already matches.

    Tolerates spelling variants of the same person sharing a hospital-scoped MRN (e.g.
    ``Zarina Qureshi`` vs ``Zarna Qureshi``) while still vetoing genuinely different people
    (``Rohan`` vs ``Mohan``, ``Sunita`` vs ``Anita``).
    """
    from clinveil.detection.translit import name_key

    def keys(ev: NameEvidence) -> tuple[str, ...]:
        return tuple(name_key(t) for t in ev.strict_tokens if name_key(t))

    for na in a:
        ka = keys(na)
        if not ka:
            continue
        for nb in b:
            kb = keys(nb)
            if not kb:
                continue
            if ka == kb:
                return True
            if len(ka) == 2 and len(kb) == 2 and ka == (kb[1], kb[0]):
                return True
            if len(ka) >= 2 and len(kb) >= 2 and ka[0] == kb[0] and ka[-1] == kb[-1]:
                return True
            if (len(ka) == 1 and ka[0] in kb) or (len(kb) == 1 and kb[0] in ka):
                return True
            # Same-position phonetic match + other token prefix match (e.g. "Pande" vs "Pandeya")
            if len(ka) == len(kb) and len(ka) >= 2:
                exact = sum(x == y for x, y in zip(ka, kb, strict=True))
                near = sum(
                    x == y or (len(x) >= 3 and len(y) >= 3 and (x.startswith(y) or y.startswith(x)))
                    for x, y in zip(ka, kb, strict=True)
                )
                if exact >= 1 and near == len(ka):
                    return True
    return False


def hard_conflicts(
    a: ClusterProfile,
    b: ClusterProfile,
    *,
    has_global_match: bool = False,
    has_scoped_id_match: bool = False,
) -> tuple[str, ...]:
    """Return all conflict codes between clusters ``a`` and ``b``."""
    conflicts: list[str] = []
    if a.ambiguous_doc or b.ambiguous_doc:
        conflicts.append("conflict_ambiguous_doc")
    # 0. One side's own person-unique ID is the other side's RELATIVE's ID: different people (R1/R2)
    if (a.relative_global_ids & b.own_global_ids()) or (b.relative_global_ids & a.own_global_ids()):
        conflicts.append("conflict_relative_id_owner")
    # 1. Conflicting validated global identifiers (always fatal)
    if a.aadhaar and b.aadhaar and a.aadhaar.isdisjoint(b.aadhaar):
        conflicts.append("conflict_aadhaar")
    if a.abha_number and b.abha_number and a.abha_number.isdisjoint(b.abha_number):
        conflicts.append("conflict_abha")
    if a.pan and b.pan and a.pan.isdisjoint(b.pan):
        conflicts.append("conflict_pan")
    # 2. Incompatible explicit gender
    if a.genders and b.genders and a.genders.isdisjoint(b.genders):
        conflicts.append("conflict_gender")
    # 3. Incompatible DOB or birth year
    if a.dobs and b.dobs and not _dob_matches(a.dobs, b.dobs):
        conflicts.append("conflict_dob")
    elif a.birth_years and b.birth_years and _year_min_diff(a.birth_years, b.birth_years) > 1:
        conflicts.append("conflict_birth_year")
    # 4. Large age discrepancy (> 3 years; allows multi-year encounter drift)
    if a.ages and b.ages and _age_min_diff(a.ages, b.ages) > 3:
        conflicts.append("conflict_age")
    # 5. Incompatible patient names
    fa, fb = _full_names(a.patient_names), _full_names(b.patient_names)
    if has_global_match and a.patient_names and b.patient_names:
        # Even with a person-unique ID match, names must be phonetically compatible as WHOLE names
        # (given name included). A shared surname alone no longer passes (Phase 3.1, R4); spelling,
        # script, order and missing-given-name variants still do. When both sides have full names,
        # only full names decide: a surname-only fragment cannot vouch for a different given name.
        na, nb = (list(fa), list(fb)) if (fa and fb) else (a.patient_names, b.patient_names)
        if best_name_grade(tuple(na), tuple(nb)) is NameGrade.CONFLICT and not _names_phonetically_compatible(na, nb):
            conflicts.append("conflict_name_disjoint")
    elif fa and fb:
        grade = best_name_grade(fa, fb)
        if grade is NameGrade.CONFLICT:
            if has_scoped_id_match:
                if not _names_phonetically_compatible(a.patient_names, b.patient_names):
                    conflicts.append("conflict_name")
            else:
                conflicts.append("conflict_name")
    elif a.patient_names and b.patient_names and not has_global_match:
        grade = best_name_grade(tuple(a.patient_names), tuple(b.patient_names))
        if grade is NameGrade.CONFLICT and not (
            has_scoped_id_match and _names_phonetically_compatible(a.patient_names, b.patient_names)
        ):
            conflicts.append("conflict_name")
    # 6. Homonym vetoes (apply when there is NO validated global ID or scoped hospital ID match)
    if not has_global_match and not has_scoped_id_match:
        if a.relative_names and b.relative_names:
            rgrade = best_name_grade(tuple(a.relative_names), tuple(b.relative_names))
            if rgrade is NameGrade.CONFLICT:
                conflicts.append("conflict_relative")
        if a.villages and b.villages and a.villages.isdisjoint(b.villages):
            conflicts.append("conflict_village")
        if a.districts and b.districts and a.districts.isdisjoint(b.districts):
            conflicts.append("conflict_district")
    return tuple(conflicts)


# --------------------------------------------------------------------------- scoped MRN matching
def shared_global_ids(a: ClusterProfile, b: ClusterProfile) -> list[str]:
    reasons: list[str] = []
    if a.aadhaar & b.aadhaar:
        reasons.append("shared_aadhaar")
    if a.abha_number & b.abha_number:
        reasons.append("shared_abha_number")
    if a.abha_address & b.abha_address:
        reasons.append("shared_abha_address")
    if a.pan & b.pan:
        reasons.append("shared_pan")
    return reasons


def shared_scoped_mrns(a: ClusterProfile, b: ClusterProfile, name_grade: NameGrade) -> list[str]:
    """Check hospital-namespaced MRN/UHID matches while strictly blocking cross-hospital collisions."""
    reasons: list[str] = []
    # Two DIFFERENT reliably known (non-lab) hospitals: a shared MRN string, prefixed or not, is no
    # evidence (R5). A slug merely guessed from a file name is not proof of a different issuer.
    if a.reliable_hospitals and b.reliable_hospitals and a.reliable_hospitals.isdisjoint(b.reliable_hospitals):
        return reasons
    # Exact same (hospital_scope, canonical_mrn) excluding "unscoped"
    scoped_a = {(s, m) for s, m in a.local_ids if s != "unscoped"}
    scoped_b = {(s, m) for s, m in b.local_ids if s != "unscoped"}
    if scoped_a & scoped_b:
        reasons.append("shared_scoped_mrn")
        return reasons
    # Same (hospital_scope, digit_core >= 5) excluding "unscoped"
    cores_a = {(s, c) for s, c in a.local_id_cores if s != "unscoped"}
    cores_b = {(s, c) for s, c in b.local_id_cores if s != "unscoped"}
    if cores_a & cores_b and name_grade is not NameGrade.CONFLICT:
        reasons.append("shared_scoped_mrn_core")
        return reasons
    # Distinctive hospital-prefixed MRN (e.g. SUN-26-100101 cited inside an external lab or cross-hospital doc)
    dist_a = {m for m, is_dist in a.raw_mrns if is_dist}
    dist_b = {m for m, is_dist in b.raw_mrns if is_dist}
    if dist_a & dist_b:
        reasons.append("shared_prefixed_mrn")
        return reasons
    # Generic MRN shared with an external lab / unknown-hospital document (different known
    # hospitals were already excluded above)
    raw_a = {m for m, _ in a.raw_mrns}
    raw_b = {m for m, _ in b.raw_mrns}
    if raw_a & raw_b:
        # Require compatible patient name if either side lacks a verified shared hospital scope
        if name_grade in _COMPATIBLE_GRADES or _names_phonetically_compatible(a.patient_names, b.patient_names):
            reasons.append("shared_external_mrn_with_name")
        elif (a.is_external_lab_only or b.is_external_lab_only) and not (a.patient_names and b.patient_names):
            # External doc quoting the MRN with no conflicting name
            reasons.append("shared_external_mrn")
    return reasons


# --------------------------------------------------------------------------- full comparison
def compare_profiles(
    a: ClusterProfile,
    b: ClusterProfile,
    *,
    allow_fragmented: bool = False,
) -> PairDecision:
    """Compare two cluster profiles and return a deterministic, explainable :class:`PairDecision`."""
    if a.ambiguous_doc or b.ambiguous_doc:
        return PairDecision(MatchOutcome.AMBIGUOUS, MatchStrength.NONE, (), ("ambiguous_doc",))

    name_grade = best_name_grade(tuple(a.patient_names), tuple(b.patient_names))
    global_reasons = shared_global_ids(a, b)
    mrn_reasons = shared_scoped_mrns(a, b, name_grade)

    has_global = bool(global_reasons)
    has_scoped = bool(mrn_reasons)
    conflicts = hard_conflicts(a, b, has_global_match=has_global, has_scoped_id_match=has_scoped)
    if not has_global and not has_scoped:
        conflicts = conflicts + tuple(_complete_linkage_conflicts(a, b))
    if conflicts:
        return PairDecision(MatchOutcome.CONFLICT, MatchStrength.NONE, tuple(global_reasons + mrn_reasons), conflicts)

    # Tier 1: Validated global identifier
    if has_global:
        return PairDecision(MatchOutcome.CONFIDENT_MATCH, MatchStrength.STRONG_GLOBAL, tuple(global_reasons), ())

    # Tier 2: Hospital-namespaced local identifier
    if has_scoped:
        return PairDecision(MatchOutcome.CONFIDENT_MATCH, MatchStrength.STRONG_SCOPED_ID, tuple(mrn_reasons), ())

    # Tier 3: Corroborated full patient name (requires >= 1 independent corroborator)
    corroborators = _supporting_corroborators(a, b)
    # Different authoritative patient MRNs from the SAME issuer (R7). Usually two different patients;
    # but DATASET.md documents re-registration ("some re-register at the same hospital with a new ID"),
    # so the only exception is a full-name match with an exact DOB AND another independent corroborator.
    if _distinct_mrns_same_issuer(a, b):
        reregistration = (
            name_grade in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
            and "corrob_dob" in corroborators
            and len(corroborators) >= 2
        )
        if not reregistration:
            return PairDecision(MatchOutcome.CONFLICT, MatchStrength.NONE, (), ("conflict_scoped_mrn",))
        corroborators = [*corroborators, "reregistration_same_issuer"]
    if name_grade in _FULL_MATCH_GRADES:
        if corroborators:
            return PairDecision(
                MatchOutcome.CONFIDENT_MATCH,
                MatchStrength.CORROBORATED_NAME,
                (f"name_{name_grade.value}", *corroborators),
                (),
            )
        return PairDecision(
            MatchOutcome.INSUFFICIENT_EVIDENCE, MatchStrength.NONE, (f"name_{name_grade.value}_only",), ()
        )

    # Tier 4: Fragmented first-name-only attachment (only during Stage C2 unique singleton attachment)
    if allow_fragmented and name_grade is NameGrade.FIRST_ONLY_MATCH:
        if corroborators:
            return PairDecision(
                MatchOutcome.CONFIDENT_MATCH,
                MatchStrength.FRAGMENTED_UNIQUE,
                ("name_first_only", *corroborators),
                (),
            )
        return PairDecision(
            MatchOutcome.INSUFFICIENT_EVIDENCE, MatchStrength.NONE, ("name_first_only_uncorroborated",), ()
        )

    # Phone-only, address-only, relative-only, or unrelated records never merge
    outcome = MatchOutcome.DISTINCT if (a.patient_names and b.patient_names) else MatchOutcome.INSUFFICIENT_EVIDENCE
    return PairDecision(outcome)


def _supporting_corroborators(a: ClusterProfile, b: ClusterProfile) -> list[str]:
    """Independent corroborators permitted to pair with a matching patient name (per DATASET.md)."""
    out: list[str] = []
    if a.dobs and b.dobs and _dob_matches(a.dobs, b.dobs):
        out.append("corrob_dob")
    if a.phones and b.phones and (a.phones & b.phones):
        out.append("corrob_phone")
    # Household-shareable identifiers: corroborate a matching name, never identify alone (R3)
    if a.insurance_id & b.insurance_id:
        out.append("corrob_insurance")
    if a.email & b.email:
        out.append("corrob_email")
    if a.relative_names and b.relative_names:
        rgrade = best_name_grade(tuple(a.relative_names), tuple(b.relative_names))
        if rgrade in _COMPATIBLE_GRADES:
            out.append("corrob_relative")
    if a.villages and b.villages and (a.villages & b.villages):
        # Village alone is NOT enough (ambiguous prescriptions); requires age within ±1 or matching birth year ±1
        if a.ages and b.ages and _age_min_diff(a.ages, b.ages) <= 1:
            out.append("corrob_village_age")
        elif a.birth_years and b.birth_years and _year_min_diff(a.birth_years, b.birth_years) <= 1:
            out.append("corrob_village_birth_year")
    return out
