"""Identity resolution data models (memory-only, redacting ``repr``, unpicklable).

No raw PII values ever appear in ``repr`` output, logs, or serialised artefacts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple


class MatchOutcome(str, Enum):
    CONFIDENT_MATCH = "CONFIDENT_MATCH"
    DISTINCT = "DISTINCT"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICT = "CONFLICT"


class MatchStrength(str, Enum):
    STRONG_GLOBAL = "strong_global"
    STRONG_SCOPED_ID = "strong_scoped_id"
    CORROBORATED_NAME = "corroborated_name"
    FRAGMENTED_UNIQUE = "fragmented_unique"
    NONE = "none"


class NameGrade(str, Enum):
    EXACT_FULL = "exact_full"
    VARIANT_FULL = "variant_full"
    ABBREVIATED_FULL = "abbreviated_full"
    FIRST_ONLY_MATCH = "first_only_match"
    CONFLICT = "conflict"
    NONE = "none"


class RecordKey(NamedTuple):
    """Deterministic locator of one record inside the input tree."""

    file_rel: str
    loc: str


@dataclass(frozen=True, slots=True)
class NameEvidence:
    """Normalised name representations for one patient or relative mention."""

    strict_tokens: tuple[str, ...] = field(repr=False)
    skeleton_tokens: tuple[str, ...] = field(repr=False)
    identifying_strict: tuple[str, ...] = field(repr=False)
    initials: tuple[str, ...] = field(repr=False)
    is_single_token: bool
    is_initial_only: bool
    confidence: float
    source: str

    def __repr__(self) -> str:
        return (
            f"NameEvidence(tokens={len(self.strict_tokens)}, single={self.is_single_token}, "
            f"init_only={self.is_initial_only}, src={self.source})"
        )

    def __reduce__(self) -> Any:
        raise TypeError("NameEvidence cannot be serialised")


@dataclass(frozen=True, slots=True)
class DateEvidence:
    """Normalised DOB with optional alternate when an unlabelled slash date is day/month ambiguous."""

    primary: tuple[int, int, int] = field(repr=False)  # (year, month, day)
    alternate: tuple[int, int, int] | None = field(default=None, repr=False)

    @property
    def year(self) -> int:
        return self.primary[0]

    def candidates(self) -> tuple[tuple[int, int, int], ...]:
        return (self.primary, self.alternate) if self.alternate is not None else (self.primary,)

    def matches(self, other: DateEvidence) -> bool:
        return bool(set(self.candidates()) & set(other.candidates()))

    def __repr__(self) -> str:
        return f"DateEvidence(ambiguous={self.alternate is not None})"

    def __reduce__(self) -> Any:
        raise TypeError("DateEvidence cannot be serialised")


@dataclass(slots=True)
class RecordEvidence:
    """Normalised identity evidence extracted from one IR record (in memory only)."""

    record: RecordKey
    hospital: str | None = None
    is_external_lab: bool = False
    #: The hospital was reliably established (FHIR system / Organization, facility field, letterhead,
    #: or a file name containing a hospital word), not guessed from an arbitrary file-name stem (R5).
    hospital_reliable: bool = False
    aadhaar: frozenset[str] = field(default_factory=frozenset, repr=False)
    abha_number: frozenset[str] = field(default_factory=frozenset, repr=False)
    abha_address: frozenset[str] = field(default_factory=frozenset, repr=False)
    pan: frozenset[str] = field(default_factory=frozenset, repr=False)
    insurance_id: frozenset[str] = field(default_factory=frozenset, repr=False)
    email: frozenset[str] = field(default_factory=frozenset, repr=False)
    local_ids: frozenset[tuple[str, str]] = field(default_factory=frozenset, repr=False)  # (scope, canonical_mrn)
    local_id_cores: frozenset[tuple[str, str]] = field(default_factory=frozenset, repr=False)  # (scope, digit_core)
    raw_mrns: frozenset[tuple[str, bool]] = field(
        default_factory=frozenset, repr=False
    )  # (canonical_mrn, has_distinctive_prefix)
    patient_names: tuple[NameEvidence, ...] = field(default_factory=tuple, repr=False)
    relative_names: tuple[NameEvidence, ...] = field(default_factory=tuple, repr=False)
    phones: frozenset[str] = field(default_factory=frozenset, repr=False)
    dobs: frozenset[DateEvidence] = field(default_factory=frozenset, repr=False)
    birth_years: frozenset[int] = field(default_factory=frozenset, repr=False)
    ages: frozenset[int] = field(default_factory=frozenset, repr=False)
    genders: frozenset[str] = field(default_factory=frozenset, repr=False)
    villages: frozenset[str] = field(default_factory=frozenset, repr=False)
    districts: frozenset[str] = field(default_factory=frozenset, repr=False)
    pins: frozenset[str] = field(default_factory=frozenset, repr=False)
    #: Person-unique identifiers that belong to a RELATIVE of this record's patient
    #: (``"aadhaar|…"``, ``"abha|…"``, ``"pan|…"``). Never identity evidence for the patient;
    #: used only as a veto (a patient whose own ID is this record's relative ID is someone else).
    relative_global_ids: frozenset[str] = field(default_factory=frozenset, repr=False)
    ambiguous_doc: bool = False

    def __repr__(self) -> str:
        loc_kind = "doc" if self.record.loc == "doc" else ("row" if self.record.loc.startswith("row:") else "ptr")
        return (
            f"RecordEvidence(loc_kind={loc_kind}, has_global={self.has_global_id}, "
            f"local_ids={len(self.local_ids)}, names={len(self.patient_names)})"
        )

    def __reduce__(self) -> Any:
        raise TypeError("RecordEvidence cannot be serialised")

    @property
    def has_global_id(self) -> bool:
        """Person-unique validated identifiers only. Insurance / policy IDs and e-mail addresses are
        often shared by a household (ESIC / PMJAY family cards, family mailbox), so they are
        corroborating evidence, never a global identity (Phase 3.1, R3)."""
        return bool(self.aadhaar or self.abha_number or self.abha_address or self.pan)

    @property
    def has_strong_anchor(self) -> bool:
        """True if this record carries a validated global ID or hospital-scoped patient ID."""
        return self.has_global_id or bool(self.local_ids)

    @property
    def has_any_evidence(self) -> bool:
        """True if ANY identity field is populated (Phase 3.3 NEW-6B): a partial record holding only
        an age, a gender, a village or a relative's ID still takes part in conflict checks."""
        return bool(
            self.has_strong_anchor
            or self.patient_names
            or self.relative_names
            or self.phones
            or self.dobs
            or self.birth_years
            or self.ages
            or self.genders
            or self.insurance_id
            or self.email
            or self.raw_mrns
            or self.villages
            or self.districts
            or self.pins
            or self.relative_global_ids
        )

    def all_birth_years(self) -> frozenset[int]:
        return self.birth_years | frozenset(d.year for d in self.dobs)

    def canonical_signature(self) -> tuple[str, ...]:
        """Content-derived deterministic ordering key (independent of file traversal order)."""
        parts: list[str] = []
        if self.aadhaar:
            parts.append("a:" + min(self.aadhaar))
        if self.abha_number:
            parts.append("b:" + min(self.abha_number))
        if self.local_ids:
            parts.append("m:" + min(f"{s}/{m}" for s, m in self.local_ids))
        if self.patient_names:
            parts.append("n:" + min(" ".join(n.strict_tokens) for n in self.patient_names))
        if self.dobs:
            parts.append("d:" + min(f"{d.primary[0]:04d}-{d.primary[1]:02d}-{d.primary[2]:02d}" for d in self.dobs))
        if self.phones:
            parts.append("p:" + min(self.phones))
        if self.villages:
            parts.append("v:" + min(self.villages))
        parts.append(f"r:{self.record.file_rel}#{self.record.loc}")
        return tuple(parts)


@dataclass(frozen=True, slots=True)
class PairDecision:
    """Explainable, PII-free outcome of comparing two records or clusters."""

    outcome: MatchOutcome
    strength: MatchStrength = MatchStrength.NONE
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass
class LinkingStats:
    """Safe aggregate linking metrics (counts only; zero PII, zero paths, zero keys)."""

    records_total: int = 0
    records_with_evidence: int = 0
    records_linked: int = 0
    records_unlinked: int = 0
    clusters_total: int = 0
    clusters_multi_record: int = 0
    clusters_singleton_anchored: int = 0
    merges_by_strength: Counter = field(default_factory=Counter)
    outcomes_by_type: Counter = field(default_factory=Counter)
    merges_blocked_by_conflict: int = 0
    blocks_capped_ambiguous: int = 0
    pseudonym_collisions_resolved: int = 0
    cluster_size_buckets: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "records_total": self.records_total,
            "records_with_evidence": self.records_with_evidence,
            "records_linked": self.records_linked,
            "records_unlinked": self.records_unlinked,
            "clusters_total": self.clusters_total,
            "clusters_multi_record": self.clusters_multi_record,
            "clusters_singleton_anchored": self.clusters_singleton_anchored,
            "merges_by_strength": dict(sorted(self.merges_by_strength.items())),
            "outcomes_by_type": dict(sorted(self.outcomes_by_type.items())),
            "merges_blocked_by_conflict": self.merges_blocked_by_conflict,
            "blocks_capped_ambiguous": self.blocks_capped_ambiguous,
            "pseudonym_collisions_resolved": self.pseudonym_collisions_resolved,
            "cluster_size_buckets": dict(sorted(self.cluster_size_buckets.items())),
        }
