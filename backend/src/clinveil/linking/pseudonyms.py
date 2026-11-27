"""Canonical cluster-key derivation and collision-free keyed HMAC pseudonym assignment.

* Canonical keys are derived ONLY from sorted normalised cluster evidence (never from
  file traversal order or temporary cluster numbers).
* Pseudonyms use domain-separated, versioned HMAC-SHA256 keyed strictly by ``RAKSHA_SECRET``.
* Distinct clusters that collide in the 30-bit Crockford base32 code space are resolved
  deterministically via a counter suffix (D8).
* Canonical keys live only inside this function call and are never returned, logged, or saved.
"""

from __future__ import annotations

from clinveil.linking.matcher import ClusterProfile
from clinveil.linking.models import LinkingStats, RecordKey
from clinveil.privacy.pseudonym import Pseudonymizer


def canonical_cluster_key(cluster: ClusterProfile) -> str:
    """Order-independent canonical key for a resolved patient cluster (memory-only)."""
    if cluster.aadhaar:
        return "aadhaar|" + min(cluster.aadhaar)
    if cluster.abha_number:
        return "abha|" + min(cluster.abha_number)
    if cluster.abha_address:
        return "abhaa|" + min(cluster.abha_address)
    if cluster.pan:
        return "pan|" + min(cluster.pan)
    # insurance / e-mail are household-shareable (R3): never canonical identity material
    if cluster.local_ids:
        return "mrn|" + min(f"{s}/{m}" for s, m in cluster.local_ids)
    # Demographic fallback for multi-record corroborated clusters without strong IDs
    parts: list[str] = []
    if cluster.patient_names:
        parts.append("n:" + min(" ".join(n.strict_tokens) for n in cluster.patient_names))
    if cluster.dobs:
        parts.append("d:" + min(f"{d.primary[0]:04d}-{d.primary[1]:02d}-{d.primary[2]:02d}" for d in cluster.dobs))
    if cluster.phones:
        parts.append("p:" + min(cluster.phones))
    if cluster.relative_names:
        parts.append("r:" + min(" ".join(n.strict_tokens) for n in cluster.relative_names))
    if cluster.villages:
        parts.append("v:" + min(cluster.villages))
    if parts:
        return "demo|" + "|".join(parts)
    # Unreachable for linked clusters, kept as safe fallback
    first = min(cluster.members)
    return f"rec|{first.file_rel}#{first.loc}"


def is_eligible_for_pseudonym(cluster: ClusterProfile) -> bool:
    """A cluster receives a pseudonym if it links >=2 records OR is anchored by a strong patient ID."""
    if cluster.ambiguous_doc:
        return False
    return len(cluster.members) >= 2 or cluster.has_strong_anchor


def assign_pseudonyms(
    clusters: list[ClusterProfile],
    pseudonymizer: Pseudonymizer,
    stats: LinkingStats,
) -> tuple[dict[RecordKey, str], frozenset[RecordKey]]:
    """Assign one unique keyed pseudonym per eligible patient cluster.

    Returns ``(RecordKey -> PSN-XXXXXX, multi_record_keys)`` (no canonical keys or raw evidence escape).
    """
    eligible = [c for c in clusters if is_eligible_for_pseudonym(c)]
    # Sort eligible clusters purely by their canonical content key (traversal-order-independent)
    keyed = sorted(
        ((canonical_cluster_key(c), min(c.members), c) for c in eligible),
        key=lambda item: (item[0], item[1]),
    )

    used: set[str] = set()
    next_attempt: dict[str, int] = {}
    mapping: dict[RecordKey, str] = {}
    multi_records: set[RecordKey] = set()
    for key, _tie, cluster in keyed:
        attempt = next_attempt.get(key, 0)
        if attempt > 0:
            stats.pseudonym_collisions_resolved += 1
        psn = pseudonymizer.pseudonym(key, attempt=attempt)
        while psn in used:
            attempt += 1
            stats.pseudonym_collisions_resolved += 1
            psn = pseudonymizer.pseudonym(key, attempt=attempt)
        next_attempt[key] = attempt + 1
        used.add(psn)
        size = len(cluster.members)
        for rec in cluster.members:
            mapping[rec] = psn
            if size >= 2:
                multi_records.add(rec)

        stats.clusters_total += 1
        if size >= 2:
            stats.clusters_multi_record += 1
        else:
            stats.clusters_singleton_anchored += 1
        bucket = "1" if size == 1 else ("2-4" if size <= 4 else ("5-15" if size <= 15 else "16+"))
        stats.cluster_size_buckets[bucket] += 1

    # Explicitly drop local references to canonical keys
    del keyed
    stats.records_linked = len(mapping)
    stats.records_unlinked = stats.records_total - stats.records_linked
    return mapping, frozenset(multi_records)
