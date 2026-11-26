"""Public identity resolution facade (Phase 3).

Coordinates extraction, conflict-aware conservative clustering, and keyed cryptographic
pseudonym assignment while ensuring cleartext identity evidence never outlives the call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

    by_file: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    multi_by_file: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)

    def for_document(self, file_rel: str) -> tuple[dict[str, str], frozenset[str]]:
        """Return ``(loc -> PSN-XXXXXX, multi_record_locs)`` for every linked record of ``file_rel``.

        O(records in the file): the per-file index is built once (the previous full scan per file
        was O(files x records)).
        """
        return dict(self.by_file.get(file_rel, {})), self.multi_by_file.get(file_rel, frozenset())


def resolve_identities(evidence: list[RecordEvidence], pseudonymizer: Pseudonymizer) -> LinkResult:
    """Resolve all extracted record evidence into keyed patient pseudonyms, then discard clusters."""
    clusters, stats = cluster_records(evidence)
    try:
        mapping, multi = assign_pseudonyms(clusters, pseudonymizer, stats)
    finally:
        clusters.clear()
        del clusters
    by_file: dict[str, dict[str, str]] = {}
    for rk, psn in mapping.items():
        by_file.setdefault(rk.file_rel, {})[rk.loc] = psn
    multi_tmp: dict[str, set[str]] = {}
    for rk in multi:
        multi_tmp.setdefault(rk.file_rel, set()).add(rk.loc)
    multi_by_file = {k: frozenset(v) for k, v in multi_tmp.items()}
    return LinkResult(
        pseudonyms=mapping, multi_records=multi, stats=stats, by_file=by_file, multi_by_file=multi_by_file
    )


def link_record(_record_text: str) -> str | None:
    """Legacy single-record stub retained for backwards compatibility (always abstains)."""
    return None
