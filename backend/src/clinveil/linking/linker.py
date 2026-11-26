"""Public identity resolution facade (Phase 3).

Coordinates extraction, conflict-aware conservative clustering, and keyed cryptographic
pseudonym assignment while ensuring cleartext identity evidence never outlives the call.
"""

from __future__ import annotations

from dataclasses import dataclass

from clinveil.linking.cluster import cluster_records
from clinveil.linking.extract import extract_document_evidence
from clinveil.linking.models import LinkingStats, RecordEvidence, RecordKey
from clinveil.linking.pseudonyms import assign_pseudonyms
from clinveil.privacy.pseudonym import Pseudonymizer

__all__ = [
    "LinkResult",
    "LinkingStats",
    "RecordEvidence",
    "RecordKey",
    "extract_document_evidence",
    "link_record",
    "resolve_identities",
]


@dataclass(frozen=True, slots=True)
class LinkResult:
    """Output of Phase 3 identity resolution: pseudonyms per record + safe aggregate stats."""

    pseudonyms: dict[RecordKey, str]
    multi_records: frozenset[RecordKey]
    stats: LinkingStats

    def for_document(self, file_rel: str) -> tuple[dict[str, str], frozenset[str]]:
        """Return ``(loc -> PSN-XXXXXX, multi_record_locs)`` for every linked record of ``file_rel``."""
        psns = {rk.loc: psn for rk, psn in self.pseudonyms.items() if rk.file_rel == file_rel}
        multi = frozenset(rk.loc for rk in self.multi_records if rk.file_rel == file_rel)
        return psns, multi


def resolve_identities(evidence: list[RecordEvidence], pseudonymizer: Pseudonymizer) -> LinkResult:
    """Resolve all extracted record evidence into keyed patient pseudonyms, then discard clusters."""
    clusters, stats = cluster_records(evidence)
    try:
        mapping, multi = assign_pseudonyms(clusters, pseudonymizer, stats)
    finally:
        clusters.clear()
        del clusters
    return LinkResult(pseudonyms=mapping, multi_records=multi, stats=stats)


def link_record(_record_text: str) -> str | None:
    """Legacy single-record stub retained for backwards compatibility (always abstains)."""
    return None
