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
from clinveil.linking.normalize import (
    _initial_matches,
    _tokens_variant_equal,
    best_name_grade,
    compare_names,
    id_type,
    is_authoritative_core,
)

_FULL_MATCH_GRADES = frozenset({NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL, NameGrade.ABBREVIATED_FULL})
_COMPATIBLE_GRADES = _FULL_MATCH_GRADES | frozenset({NameGrade.FIRST_ONLY_MATCH})
#: Independent non-DOB-derived corroborators permitted to pair with exact DOB for R7 re-registration (F6).
_REREG_INDEPENDENT_CORROBS = frozenset({"corrob_phone", "corrob_relative", "corrob_insurance", "corrob_email"})
#: Reason tag of a Tier-2a decision: the MRN match was verified inside one reliably known hospital.
VERIFIED_SAME_HOSPITAL = "verified_same_hospital"


@dataclass(slots=True)
class ClusterProfile:
    """Aggregate identity evidence across all records currently in one cluster (memory-only)."""

    members: list[RecordKey] = field(default_factory=list)
    hospitals: set[str] = field(default_factory=set)
    #: Hospitals reliably established for this cluster (R5): only these can prove "different issuer".
    reliable_hospitals: set[str] = field(default_factory=set)
    has_non_lab_hospital: bool = False
    is_external_lab_only: bool = True
    #: True ONLY when every member is an explicitly identified external pathology/lab document (F1).
    is_true_external_lab_only: bool = True
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
            is_true_external_lab_only=ev.is_external_lab,
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
        self.is_true_external_lab_only = self.is_true_external_lab_only and other.is_true_external_lab_only
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


def _exact_dob_matches(a: set[DateEvidence], b: set[DateEvidence]) -> bool:
    """Unambiguous exact DOB match for R7 re-registration (rejects swapped slash dates 03/04 vs 04/03, F6)."""
    return any(
        da.primary == db.primary or ((da.alternate is None or db.alternate is None) and da.matches(db))
        for da in a
        for db in b
    )


def _age_min_diff(a: set[int], b: set[int]) -> int:
    return min(abs(x - y) for x in a for y in b)


def _year_min_diff(a: set[int], b: set[int]) -> int:
    return min(abs(x - y) for x in a for y in b)


def _age_max_diff(a: set[int], b: set[int]) -> int:
    return max(abs(x - y) for x in a for y in b)


def _authoritative_ids_by_scope(c: ClusterProfile) -> dict[str, set[str]]:
    """Known-issuer scope -> the patient's own MRN/UHID keys (``type:digits``; admissions/visits excluded).

    Compared by type + last digit run without leading zeros, so ``UHID-0045123`` and
    ``UHID/45123`` are the same key (the veto errs towards NOT firing). For unreliable-stem
    documents carrying a distinctive issuer prefix (``KSR-26-000111`` in ``export_jan.csv``),
    also keys by ``issuer_pfx:<type>`` so distinct same-issuer UHIDs across generic filenames
    still trigger R7 (F6).

    The issuer-prefix key is recorded for EVERY scope, reliable hospital or not (Phase 3.3
    PASS1-NEW-5): ``KSR-26-004417`` from ``kestrel_hospital/…`` and ``KSR-26-004981`` from an
    ``export_jan.csv`` share the issuer ``pfx_ksr`` even though their file scopes differ. This key
    is only ever used to VETO (two different numbers from one issuer); it never creates a match.
    """
    distinctive_mrns = {m for m, dist in c.raw_mrns if dist}
    out: dict[str, set[str]] = {}
    for scope, canon in c.local_ids:
        if scope == "unscoped":
            continue
        t = id_type(canon)
        core = mrn_digit_core(canon).lstrip("0") or "0"
        key = f"{t}:{core}"
        if is_authoritative_core(key):
            out.setdefault(scope, set()).add(key)
            if t.startswith("pfx_") and canon in distinctive_mrns:
                out.setdefault(f"issuer_pfx:{t}", set()).add(key)
    return out


def _distinct_mrns_same_issuer(a: ClusterProfile, b: ClusterProfile) -> bool:
    sa, sb = _authoritative_ids_by_scope(a), _authoritative_ids_by_scope(b)
    return any(sa[s].isdisjoint(sb[s]) for s in sa.keys() & sb.keys())


def _full_names_have_any_conflict(
    fa: tuple[NameEvidence, ...],
    fb: tuple[NameEvidence, ...],
    *,
    allow_phonetic: bool = False,
) -> bool:
    """Complete-linkage full-name check (F2): an abbreviated name (``N. Vermeer``) inside a
    cluster must NEVER override a concrete full-name conflict (``Nolan Vermeer`` vs ``Nathan Vermeer``).

    When the clusters already share an ``EXACT_FULL`` or ``VARIANT_FULL`` concrete name match,
    an additional spelling/transliteration variant already merged into the cluster via a strong ID
    (phonetically compatible as a whole name) does not cause a false split; any phonetically
    incompatible full name still vetoes the merge.
    """
    best = best_name_grade(fa, fb)
    has_concrete_match = best in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
    for na in fa:
        for nb in fb:
            if compare_names(na, nb) is NameGrade.CONFLICT:
                if (allow_phonetic or has_concrete_match) and _names_phonetically_compatible([na], [nb]):
                    continue
                return True
    return False


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


def _fragment_contradicts(names: list[NameEvidence], full_other: tuple[NameEvidence, ...]) -> bool:
    """A single-token patient name on one side conflicts (also phonetically) with a full name on the other."""
    return any(
        compare_names(s, f) is NameGrade.CONFLICT and not _names_phonetically_compatible([s], [f])
        for s in names
        if s.is_single_token and not s.is_initial_only
        for f in full_other
    )


def _full_names(names: list[NameEvidence]) -> tuple[NameEvidence, ...]:
    return tuple(n for n in names if not n.is_single_token and not n.is_initial_only)


def _translit_u_e_skeleton(strict_tok: str, skel_tok: str) -> str:
    """Fold silent trailing ``-e`` and English short ``u`` (transliterated as Devanagari ``अ``/``a``)
    while keeping ``i``, ``e``, ``o`` intact (so ``Dunmore`` == ``डनमोर`` -> ``dnmor``)."""
    vowels = set("aeiou")
    has_silent_e = len(strict_tok) >= 5 and strict_tok.endswith("e") and strict_tok[-2] not in vowels
    s = strict_tok[:-1] if has_silent_e else strict_tok
    if len(s) <= 2:
        return skel_tok
    out = [s[0]]
    for i in range(1, len(s)):
        ch = s[i]
        if ch in ("a", "u") and i + 1 < len(s) and s[i - 1] not in vowels and s[i + 1] not in vowels:
            continue
        out.append(ch)
    return "".join(out)


def _tokens_phonetically_compatible(sa: str, ka: str, sb: str, kb: str) -> bool:
    """Token-level phonetic check under a strong ID match that preserves primary vowel distinctions (NEW-4).

    Accepts exact/schwa variants (``Kamlesh``/``Kamalesh``), cross-script short-``u``/silent-``e``
    transliterations (``Dunmore``/``डनमोर``), ``-e``/``-eya`` suffix variants (``Pande``/``Pandeya``),
    and single unstressed medial vowel elision in 5+ char tokens with matching consonant skeleton
    (``Zarina``/``Zarna``), while rejecting vowel substitutions between distinct Indian names
    (``Kiran``/``Karan``, ``Alok``/``Alka``, ``Sunil``/``Sonal``).
    """
    from clinveil.detection.translit import name_key

    if _tokens_variant_equal(sa, ka, sb, kb):
        return True
    nka, nkb = name_key(sa), name_key(sb)
    if not nka or not nkb:
        return False
    if nka == nkb and len(nka) >= 4 and _translit_u_e_skeleton(sa, ka) == _translit_u_e_skeleton(sb, kb):
        return True
    # Suffix variant on >=4-char shared root (e.g. "pande" vs "pandeya")
    short_s, long_s = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if len(short_s) >= 4 and long_s.startswith(short_s) and long_s[len(short_s) :] in ("a", "ya", "ia", "iya"):
        return True
    # Single medial vowel elision in a >=5-char token with identical >=3-consonant skeleton ("jarina" vs "jarna")
    if nka == nkb and len(nka) >= 3 and len(long_s) - len(short_s) == 1 and len(short_s) >= 5:
        vowels = set("aeiou")
        for i in range(1, len(long_s) - 1):
            if long_s[i] in vowels and (long_s[:i] + long_s[i + 1 :]) == short_s:
                return True
    return False


def _names_phonetically_compatible(a: list[NameEvidence], b: list[NameEvidence]) -> bool:
    """Whole-name phonetic compatibility used ONLY when an MRN or global ID already matches (NEW-4).

    Tolerates transliteration, schwa, middle-name omission, and 1-char medial vowel elision
    (``Zarina Qureshi`` vs ``Zarna Qureshi``) while vetoing distinct given names (``Kiran`` vs
    ``Karan``, ``Alok`` vs ``Alka``, ``Sunil`` vs ``Sonal``) and conflicting middle names
    (``Anil Kumar Solanki`` vs ``Anil Prakash Solanki``).
    """
    for na in a:
        if na.is_initial_only:
            continue
        sa, ka = na.strict_tokens, na.skeleton_tokens
        for nb in b:
            if nb.is_initial_only:
                continue
            if compare_names(na, nb) in _COMPATIBLE_GRADES:
                return True
            sb, kb = nb.strict_tokens, nb.skeleton_tokens
            if len(sa) >= 2 and len(sb) >= 2:
                if len(sa) == len(sb) and all(
                    _tokens_phonetically_compatible(sa[i], ka[i], sb[i], kb[i])
                    or _initial_matches(na, i, nb, i)
                    or _initial_matches(nb, i, na, i)
                    for i in range(len(sa))
                ):
                    return True
                if (
                    len(sa) == 2
                    and len(sb) == 2
                    and _tokens_phonetically_compatible(sa[0], ka[0], sb[1], kb[1])
                    and _tokens_phonetically_compatible(sa[1], ka[1], sb[0], kb[0])
                ):
                    return True
                # Middle-name omission ONLY when token counts differ (never when middle tokens conflict, NEW-4)
                if (
                    len(sa) != len(sb)
                    and _tokens_phonetically_compatible(sa[0], ka[0], sb[0], kb[0])
                    and _tokens_phonetically_compatible(sa[-1], ka[-1], sb[-1], kb[-1])
                ):
                    return True
            elif len(sa) == 1 or len(sb) == 1:
                single, other = (na, nb) if len(sa) == 1 else (nb, na)
                ts, tk = single.strict_tokens[0], single.skeleton_tokens[0]
                if (
                    len(ts) >= 2
                    and single.identifying_strict
                    and any(
                        _tokens_phonetically_compatible(ts, tk, other.strict_tokens[i], other.skeleton_tokens[i])
                        for i, st in enumerate(other.strict_tokens)
                        if st in other.identifying_strict or i == 0
                    )
                ):
                    return True
    return False


def hard_conflicts(
    a: ClusterProfile,
    b: ClusterProfile,
    *,
    has_global_match: bool = False,
    has_scoped_id_match: bool = False,
    allow_phonetic_name: bool = False,
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
    # One person may hold several ABHA PHR addresses: different addresses only contradict when
    # no validated Aadhaar / ABHA number is shared (Phase 3.3 NEW-7B).
    if (
        a.abha_address
        and b.abha_address
        and a.abha_address.isdisjoint(b.abha_address)
        and a.aadhaar.isdisjoint(b.aadhaar)
        and a.abha_number.isdisjoint(b.abha_number)
    ):
        conflicts.append("conflict_abha_address")
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
    # 5. Incompatible patient names (complete-linkage across all full-name pairs, F2)
    fa, fb = _full_names(a.patient_names), _full_names(b.patient_names)
    phonetic_ok = has_global_match or has_scoped_id_match or allow_phonetic_name
    if has_global_match and a.patient_names and b.patient_names:
        # Even with a person-unique ID match, names must be phonetically compatible as WHOLE names
        # (given name included). When both sides have full names, every pair of full names must be
        # compatible so an abbreviated name cannot override a concrete full-name conflict (R4/F2).
        if fa and fb:
            if _full_names_have_any_conflict(fa, fb, allow_phonetic=True):
                conflicts.append("conflict_name_disjoint")
        else:
            if best_name_grade(tuple(a.patient_names), tuple(b.patient_names)) is NameGrade.CONFLICT and not (
                _names_phonetically_compatible(a.patient_names, b.patient_names)
            ):
                conflicts.append("conflict_name_disjoint")
    elif fa and fb:
        if _full_names_have_any_conflict(fa, fb, allow_phonetic=phonetic_ok):
            conflicts.append("conflict_name")
    elif a.patient_names and b.patient_names and not has_global_match:
        grade = best_name_grade(tuple(a.patient_names), tuple(b.patient_names))
        if grade is NameGrade.CONFLICT and not (
            phonetic_ok and _names_phonetically_compatible(a.patient_names, b.patient_names)
        ):
            conflicts.append("conflict_name")
    # 5b. A single-token name (fragment such as "Nolan") that contradicts EVERY reading of a full name
    #     on the other side ("Nathan Vermeer") is a contradiction too: otherwise a cluster could hold
    #     both once full names on each side agree with each other (complete linkage, Phase 3.3).
    if not any(c.startswith("conflict_name") for c in conflicts) and (
        _fragment_contradicts(a.patient_names, fb) or _fragment_contradicts(b.patient_names, fa)
    ):
        conflicts.append("conflict_name_fragment")
    # 6. Homonym vetoes (apply unless there is a validated global ID or VERIFIED same-hospital ID match, F1)
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


def strong_pair_conflicts(a: ClusterProfile, b: ClusterProfile, *, via_local_id: bool = False) -> tuple[str, ...]:
    """Contradictions that forbid ``a`` and ``b`` from EVER sharing a cluster, even when a
    validated identifier (directly or through a bridge record) links them (Phase 3.3 PASS1-NEW-6).

    Homonym vetoes (village, relative name, district) are relaxed exactly as they are for a direct
    validated-ID match; person-unique ID, gender, DOB, age and whole-name contradictions remain.
    ``via_local_id``: the strong path between ``a`` and ``b`` uses a verified same-hospital local ID
    (not validated global IDs alone), so R7 also applies unless ``a`` and ``b`` share a validated
    global ID themselves: a chain of shared OPD numbers cannot override two UHIDs (P33-PASS3-F2).
    """
    conflicts = hard_conflicts(a, b, has_global_match=True)
    if via_local_id and not shared_global_ids(a, b) and r7_conflict(a, b):
        conflicts = (*conflicts, "conflict_scoped_mrn")
    return conflicts


def is_weak_edge(dec: PairDecision) -> bool:
    """An identifier edge that does NOT prove identity on its own: an unverified-scope, prefixed or
    external-lab MRN match (Tier 2b). Validated global IDs and verified same-hospital MRNs are strong."""
    return dec.strength is MatchStrength.STRONG_SCOPED_ID and VERIFIED_SAME_HOSPITAL not in dec.reasons


# --------------------------------------------------------------------------- scoped MRN matching
def _mrn_reliable_hospitals(c: ClusterProfile, canon: str) -> set[str]:
    """Reliable hospital issuers that actually produced ``canon`` inside cluster ``c`` (F1)."""
    return {
        scope[5:]
        for scope, m in c.local_ids
        if m == canon and scope.startswith("hosp:") and scope[5:] in c.reliable_hospitals
    }


def _mrn_cross_hospital_disjoint(a: ClusterProfile, b: ClusterProfile, canon: str) -> bool:
    """True if ``canon`` came from two DIFFERENT reliable hospitals on ``a`` and ``b`` (F1).

    Preserves per-MRN provenance inside multi-hospital clusters so Hospital A's MRN can never
    match Hospital B's identical MRN merely because the cluster also has a record at Hospital B.
    """
    ha = _mrn_reliable_hospitals(a, canon)
    hb = _mrn_reliable_hospitals(b, canon)
    return bool(ha and hb and ha.isdisjoint(hb))


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


def shared_scoped_mrns(a: ClusterProfile, b: ClusterProfile, name_grade: NameGrade) -> tuple[list[str], bool]:
    """Check hospital-namespaced MRN/UHID matches while strictly blocking cross-hospital collisions.

    Returns ``(reasons, verified_same_hospital)``. Only verified same-hospital MRN matches may
    relax homonym/complete-linkage vetoes; unverified-scope, prefixed-only, or external-lab MRN
    matches keep homonym, complete-linkage, and R7 distinct-MRN protections active (F1).
    """
    reasons: list[str] = []
    # Two DIFFERENT reliably known (non-lab) hospitals: a shared MRN string, prefixed or not, is no
    # evidence (R5). A slug merely guessed from a file name is not proof of a different issuer.
    if a.reliable_hospitals and b.reliable_hospitals and a.reliable_hospitals.isdisjoint(b.reliable_hospitals):
        return reasons, False
    # Exact same (hospital_scope, canonical_mrn) excluding "unscoped"
    scoped_a = {(s, m) for s, m in a.local_ids if s != "unscoped"}
    scoped_b = {(s, m) for s, m in b.local_ids if s != "unscoped"}
    common_scoped = scoped_a & scoped_b
    if common_scoped:
        verified = any(
            s.startswith("hosp:") and s[5:] in (a.reliable_hospitals & b.reliable_hospitals) for s, _ in common_scoped
        )
        reasons.append("shared_scoped_mrn")
        return reasons, verified
    # Same (hospital_scope, digit_core >= 5) excluding "unscoped"
    cores_a = {(s, c) for s, c in a.local_id_cores if s != "unscoped"}
    cores_b = {(s, c) for s, c in b.local_id_cores if s != "unscoped"}
    common_cores = cores_a & cores_b
    if common_cores and name_grade is not NameGrade.CONFLICT:
        verified = any(
            s.startswith("hosp:") and s[5:] in (a.reliable_hospitals & b.reliable_hospitals) for s, _ in common_cores
        )
        reasons.append("shared_scoped_mrn_core")
        return reasons, verified
    # Distinctive hospital-prefixed MRN (e.g. SUN-26-100101 cited inside an external lab or third-party note),
    # checking per-MRN reliable hospital provenance so multi-hospital clusters cannot bridge issuers (F1).
    dist_a = {m for m, is_dist in a.raw_mrns if is_dist}
    dist_b = {m for m, is_dist in b.raw_mrns if is_dist}
    common_dist = {m for m in (dist_a & dist_b) if not _mrn_cross_hospital_disjoint(a, b, m)}
    if common_dist:
        reasons.append("shared_prefixed_mrn")
        return reasons, False
    # Generic MRN shared between a TRUE external pathology/lab document and a referring hospital
    # cluster ONLY (never between two external labs lacking a hospital anchor, never two non-lab exports
    # with unknown or different hospital stems, and never across per-MRN disjoint reliable issuers, F1/NEW-3).
    if (a.is_true_external_lab_only != b.is_true_external_lab_only) and (
        a.has_non_lab_hospital or b.has_non_lab_hospital
    ):
        raw_a = {m for m, _ in a.raw_mrns}
        raw_b = {m for m, _ in b.raw_mrns}
        common_raw = {m for m in (raw_a & raw_b) if not _mrn_cross_hospital_disjoint(a, b, m)}
        if common_raw:
            if name_grade in _COMPATIBLE_GRADES or _names_phonetically_compatible(a.patient_names, b.patient_names):
                reasons.append("shared_external_mrn_with_name")
            elif not (a.patient_names and b.patient_names):
                reasons.append("shared_external_mrn")
    return reasons, False


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
    mrn_reasons, has_verified_scoped = shared_scoped_mrns(a, b, name_grade)

    has_global = bool(global_reasons)
    has_scoped = bool(mrn_reasons)
    conflicts = hard_conflicts(
        a,
        b,
        has_global_match=has_global,
        has_scoped_id_match=has_verified_scoped,
        allow_phonetic_name=has_scoped,
    )
    if not has_global and not has_verified_scoped:
        conflicts = conflicts + tuple(_complete_linkage_conflicts(a, b))
    if conflicts:
        return PairDecision(MatchOutcome.CONFLICT, MatchStrength.NONE, tuple(global_reasons + mrn_reasons), conflicts)

    # Tier 1: Validated global identifier
    if has_global:
        return PairDecision(MatchOutcome.CONFIDENT_MATCH, MatchStrength.STRONG_GLOBAL, tuple(global_reasons), ())

    # Different authoritative patient MRNs from the SAME issuer (R7 / F1 / F6). Checked BEFORE
    # every local-identifier tier, so neither an external/prefixed MRN (Tier 2b) nor a shared
    # non-authoritative OPD / IPD / admission number at a verified hospital (Tier 2a, P33-PASS3-F2)
    # can override two different UHIDs. Only a validated global ID (Tier 1) or the DATASET.md
    # re-registration evidence takes precedence.
    corroborators = _supporting_corroborators(a, b)
    if _distinct_mrns_same_issuer(a, b):
        if not _is_reregistration(a, b, name_grade, corroborators):
            return PairDecision(MatchOutcome.CONFLICT, MatchStrength.NONE, (), ("conflict_scoped_mrn",))
        corroborators = [*corroborators, "reregistration_same_issuer"]

    # Tier 2a: Verified same-hospital local identifier
    if has_verified_scoped:
        return PairDecision(
            MatchOutcome.CONFIDENT_MATCH,
            MatchStrength.STRONG_SCOPED_ID,
            (*mrn_reasons, VERIFIED_SAME_HOSPITAL),
            (),
        )

    # Tier 2b: Unverified-scope / distinctive-prefix / external-lab MRN (all vetoes & R7 already passed)
    if has_scoped:
        return PairDecision(MatchOutcome.CONFIDENT_MATCH, MatchStrength.STRONG_SCOPED_ID, tuple(mrn_reasons), ())

    # Tier 3: Corroborated full patient name (requires >= 1 independent corroborator)
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


def _is_reregistration(a: ClusterProfile, b: ClusterProfile, name_grade: NameGrade, corroborators: list[str]) -> bool:
    """DATASET.md re-registration exception to R7: name + exact DOB + one more independent corroborator."""
    return (
        name_grade in (NameGrade.EXACT_FULL, NameGrade.VARIANT_FULL)
        and _exact_dob_matches(a.dobs, b.dobs)
        and any(c in _REREG_INDEPENDENT_CORROBS for c in corroborators)
    )


def weak_path_conflicts(a: ClusterProfile, b: ClusterProfile) -> tuple[str, ...]:
    """Every veto a DIRECT weak MRN match between ``a`` and ``b`` would have to pass (P33-F1).

    Used for two clusters joined only through a path that contains a weak (unverified-scope,
    prefixed or external-lab MRN) edge. Exactly the :func:`compare_profiles` vetoes of Tier 2b:
    contradicting IDs, gender, DOB, age, names, homonym vetoes (relative name, village, district),
    complete-linkage spans and R7 (distinct same-issuer MRNs, re-registration exception). As for a
    direct weak MRN match, names are compared with transliteration tolerance (``allow_phonetic_name``),
    so one patient's Devanagari and Latin spellings linked through a lab slip are not split.
    A shared validated ID or verified same-hospital MRN relaxes the homonym vetoes as it does in
    :func:`compare_profiles`; R7 is then still enforced unless a validated global ID is shared
    (P33-PASS3-F2).
    """
    if a.ambiguous_doc or b.ambiguous_doc:
        return ("conflict_ambiguous_doc",)
    name_grade = best_name_grade(tuple(a.patient_names), tuple(b.patient_names))
    has_global = bool(shared_global_ids(a, b))
    _mrn_reasons, has_verified_scoped = shared_scoped_mrns(a, b, name_grade)
    conflicts = hard_conflicts(
        a,
        b,
        has_global_match=has_global,
        has_scoped_id_match=has_verified_scoped,
        allow_phonetic_name=True,
    )
    if has_global:
        return conflicts
    if not has_verified_scoped:
        conflicts = conflicts + tuple(_complete_linkage_conflicts(a, b))
    if r7_conflict(a, b, name_grade):  # also when a verified local ID is shared (P33-PASS3-F2)
        conflicts = (*conflicts, "conflict_scoped_mrn")
    return conflicts


def r7_conflict(a: ClusterProfile, b: ClusterProfile, name_grade: NameGrade | None = None) -> bool:
    """R7: different authoritative patient MRNs/UHIDs from the SAME issuer, without the DATASET.md
    re-registration evidence (name + exact DOB + one more independent corroborator)."""
    if not _distinct_mrns_same_issuer(a, b):
        return False
    if name_grade is None:
        name_grade = best_name_grade(tuple(a.patient_names), tuple(b.patient_names))
    return not _is_reregistration(a, b, name_grade, _supporting_corroborators(a, b))


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
