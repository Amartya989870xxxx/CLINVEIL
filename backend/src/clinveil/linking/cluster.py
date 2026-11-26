"""Bounded blocking and 3-stage conflict-aware conservative patient clustering.

Never runs naive transitive connected components:
* Stage A: Validated global IDs (cluster-level conflict check before every merge).
* Stage B: Hospital-scoped local IDs (cluster-level conflict check before every merge).
* Stage C1: Corroborated full-name merges in strict priority order, with ambiguity guard
  against competing clusters and cluster-level conflict re-verification.
* Stage C2: Unique singleton/fragmented attachments (e.g. ``<first name>, W/o <relative>``
  or ``<first name> + <phone>``) attached ONLY when exactly one existing cluster matches
  with zero conflicts. Never chains weak singletons together.

All operations use bounded candidate blocks and canonical content-derived ordering so
decisions are deterministic regardless of input file traversal order.
"""

from __future__ import annotations

from collections import defaultdict

from clinveil.linking.matcher import ClusterProfile, compare_profiles
from clinveil.linking.models import (
    LinkingStats,
    MatchOutcome,
    MatchStrength,
    RecordEvidence,
)

#: Maximum distinct clusters in a single blocking bucket before skipping as pathological/ambiguous.
MAX_ID_BLOCK = 128
MAX_NAME_BLOCK = 64

_CORROB_PRIORITY = {
    "corrob_dob": 4,
    "corrob_phone": 3,
    "corrob_relative": 2,
    "corrob_village_age": 1,
    "corrob_village_birth_year": 1,
}


def cluster_records(evidence_list: list[RecordEvidence]) -> tuple[list[ClusterProfile], LinkingStats]:
    """Conservatively resolve ``evidence_list`` into disjoint patient :class:`ClusterProfile` s."""
    stats = LinkingStats(records_total=len(evidence_list))
    # Sort input evidence deterministically by content signature (traversal-order-independent)
    ordered = sorted(evidence_list, key=lambda e: e.canonical_signature())
    active_ids: list[int] = []
    clusters: dict[int, ClusterProfile] = {}
    sigs: dict[int, tuple[str, ...]] = {}
    for idx, ev in enumerate(ordered):
        if ev.has_any_evidence and not ev.ambiguous_doc:
            stats.records_with_evidence += 1
        elif ev.ambiguous_doc:
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += 1
        clusters[idx] = ClusterProfile.from_record(ev)
        sigs[idx] = ev.canonical_signature()
        if ev.has_any_evidence and not ev.ambiguous_doc:
            active_ids.append(idx)

    parent = {i: i for i in clusters}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def merge_roots(ra: int, rb: int, strength: MatchStrength) -> int:
        # Always merge into the canonically smaller signature root for determinism
        if sigs[rb] < sigs[ra]:
            ra, rb = rb, ra
        clusters[ra].absorb(clusters[rb])
        parent[rb] = ra
        del clusters[rb]
        stats.merges_by_strength[strength.value] += 1
        stats.outcomes_by_type[MatchOutcome.CONFIDENT_MATCH.value] += 1
        return ra

    # ------------------------------------------------------------------ Stage A: Global IDs
    global_blocks = _build_global_blocks(active_ids, clusters)
    _merge_from_blocks(
        global_blocks,
        clusters=clusters,
        sigs=sigs,
        find=find,
        merge_roots=merge_roots,
        stats=stats,
        allowed_strengths={MatchStrength.STRONG_GLOBAL},
        max_block=MAX_ID_BLOCK,
    )

    # ------------------------------------------------------------------ Stage B: Hospital-Scoped Local IDs
    mrn_blocks = _build_mrn_blocks(clusters)
    _merge_from_blocks(
        mrn_blocks,
        clusters=clusters,
        sigs=sigs,
        find=find,
        merge_roots=merge_roots,
        stats=stats,
        allowed_strengths={MatchStrength.STRONG_GLOBAL, MatchStrength.STRONG_SCOPED_ID},
        max_block=MAX_ID_BLOCK,
    )

    # ------------------------------------------------------------------ Stage C1: Corroborated Full Names
    # Bounded convergence (up to 3 passes) so multi-hospital clusters that gain a corroborator
    # from an earlier merge can cleanly link in the next pass, while always re-checking conflicts.
    for _ in range(3):
        before = len(clusters)
        _merge_corroborated_full_names(clusters, sigs, find, merge_roots, stats)
        if len(clusters) == before:
            break

    # ------------------------------------------------------------------ Stage C2: Unique Fragmented Attachments
    _attach_fragmented_singletons(clusters, sigs, find, merge_roots, stats)

    final_clusters = sorted(clusters.values(), key=lambda c: tuple(c.members))
    return final_clusters, stats


# --------------------------------------------------------------------------- blocking helpers
def _build_global_blocks(
    active_ids: list[int], clusters: dict[int, ClusterProfile]
) -> dict[tuple[str, str], list[int]]:
    blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for cid in active_ids:
        c = clusters[cid]
        for a in c.aadhaar:
            blocks[("aadhaar", a)].append(cid)
        for ab in c.abha_number:
            blocks[("abha", ab)].append(cid)
        for aba in c.abha_address:
            blocks[("abhaa", aba)].append(cid)
        for p in c.pan:
            blocks[("pan", p)].append(cid)
        for ins in c.insurance_id:
            blocks[("ins", ins)].append(cid)
        for em in c.email:
            blocks[("email", em)].append(cid)
    return blocks


def _build_mrn_blocks(clusters: dict[int, ClusterProfile]) -> dict[tuple[str, str], list[int]]:
    blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for cid, c in clusters.items():
        if not c.local_ids and not c.raw_mrns:
            continue
        for scope, mrn in c.local_ids:
            if scope != "unscoped":
                blocks[("scoped", f"{scope}|{mrn}")].append(cid)
        for scope, core in c.local_id_cores:
            if scope != "unscoped":
                blocks[("core", f"{scope}|{core}")].append(cid)
        for mrn, _distinctive in c.raw_mrns:
            blocks[("raw_mrn", mrn)].append(cid)
    return blocks


def _merge_from_blocks(
    blocks: dict[tuple[str, str], list[int]],
    *,
    clusters: dict[int, ClusterProfile],
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
    stats: LinkingStats,
    allowed_strengths: set[MatchStrength],
    max_block: int,
) -> None:
    for _key in sorted(blocks):
        members = blocks[_key]
        unique_roots = sorted({find(m) for m in members}, key=lambda r: sigs[r])
        if len(unique_roots) < 2:
            continue
        if len(unique_roots) > max_block:
            stats.blocks_capped_ambiguous += 1
            continue
        for i in range(len(unique_roots)):
            ra = find(unique_roots[i])
            if ra not in clusters:
                continue
            for j in range(i + 1, len(unique_roots)):
                rb = find(unique_roots[j])
                if rb == ra or rb not in clusters:
                    continue
                dec = compare_profiles(clusters[ra], clusters[rb], allow_fragmented=False)
                if dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength in allowed_strengths:
                    ra = merge_roots(ra, rb, dec.strength)
                elif dec.outcome is MatchOutcome.CONFLICT:
                    stats.merges_blocked_by_conflict += 1
                    stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1


def _name_block_keys(c: ClusterProfile) -> set[tuple[str, str]]:
    """Generate bounded blocking keys for clusters with full patient names."""
    keys: set[tuple[str, str]] = set()
    for n in c.patient_names:
        if n.is_single_token or n.is_initial_only:
            continue
        # Sorted pair of first + last skeleton tokens (handles Last/First swap and schwa variants)
        pair = tuple(sorted((n.skeleton_tokens[0], n.skeleton_tokens[-1])))
        keys.add(("full", f"{pair[0]}|{pair[1]}"))
        # Surname + first initial (handles "R. Sharma" vs "Rajesh Sharma")
        keys.add(("init", f"{n.skeleton_tokens[-1]}|{n.initials[0]}"))
        # Also handle reversed "Sharma, R."
        keys.add(("init", f"{n.skeleton_tokens[0]}|{n.initials[-1]}"))
    for ph in c.phones:
        keys.add(("phone", ph))
    for d in c.dobs:
        keys.add(("dob", f"{d.year:04d}"))
    return keys


def _merge_corroborated_full_names(
    clusters: dict[int, ClusterProfile],
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
    stats: LinkingStats,
) -> None:
    blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for cid, c in clusters.items():
        if not c.has_full_patient_name:
            continue
        for k in _name_block_keys(c):
            blocks[k].append(cid)

    # Collect candidate corroborated edges with priority
    cand_edges: list[tuple[int, tuple[str, ...], tuple[str, ...], int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for _key in sorted(blocks):
        roots = sorted({find(m) for m in blocks[_key]}, key=lambda r: sigs[r])
        if len(roots) < 2:
            continue
        cap = MAX_ID_BLOCK if _key[0] in ("phone", "dob") else MAX_NAME_BLOCK
        if len(roots) > cap:
            stats.blocks_capped_ambiguous += 1
            continue
        for i in range(len(roots)):
            for j in range(i + 1, len(roots)):
                a, b = roots[i], roots[j]
                pair = (a, b) if a < b else (b, a)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                dec = compare_profiles(clusters[a], clusters[b], allow_fragmented=False)
                if dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength is MatchStrength.CORROBORATED_NAME:
                    prio = max((_CORROB_PRIORITY.get(r, 0) for r in dec.reasons), default=0)
                    sa, sb = (sigs[a], sigs[b]) if sigs[a] <= sigs[b] else (sigs[b], sigs[a])
                    cand_edges.append((-prio, sa, sb, a, b))
                elif dec.outcome is MatchOutcome.CONFLICT:
                    stats.merges_blocked_by_conflict += 1
                    stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1

    # Ambiguity check: build adjacency of candidate edges so if node X matches Y and Z
    # where Y and Z CONFLICT with each other, X's weaker ambiguous edges are withheld.
    adj: dict[int, set[int]] = defaultdict(set)
    for _, _, _, a, b in cand_edges:
        adj[a].add(b)
        adj[b].add(a)

    cand_edges.sort()
    for _, _, _, a, b in cand_edges:
        ra, rb = find(a), find(b)
        if ra == rb or ra not in clusters or rb not in clusters:
            continue
        # Check if ra or rb has a competing candidate that conflicts with the other
        if _has_competing_conflict(ra, rb, adj, clusters, find):
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += 1
            continue
        # Always re-verify cluster-level conflicts immediately before merging!
        dec = compare_profiles(clusters[ra], clusters[rb], allow_fragmented=False)
        if dec.outcome is MatchOutcome.CONFIDENT_MATCH:
            merge_roots(ra, rb, dec.strength)
        elif dec.outcome is MatchOutcome.CONFLICT:
            stats.merges_blocked_by_conflict += 1
            stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1


def _has_competing_conflict(
    ra: int,
    rb: int,
    adj: dict[int, set[int]],
    clusters: dict[int, ClusterProfile],
    find,
) -> bool:
    for node, partner in ((ra, rb), (rb, ra)):
        for nbr in adj.get(node, ()):
            rn = find(nbr)
            if rn in (ra, rb) or rn not in clusters:
                continue
            d_self = compare_profiles(clusters[node], clusters[rn], allow_fragmented=False)
            if d_self.outcome is MatchOutcome.CONFIDENT_MATCH:
                d_cross = compare_profiles(clusters[partner], clusters[rn], allow_fragmented=False)
                if d_cross.outcome is MatchOutcome.CONFLICT:
                    return True
    return False


def _attach_fragmented_singletons(
    clusters: dict[int, ClusterProfile],
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
    stats: LinkingStats,
) -> None:
    """Attach remaining fragmented singletons (e.g. first name + relative/phone/village+age)
    ONLY when they match a SINGLE unique anchor cluster with zero conflicts.
    """
    # Anchor targets: clusters with a strong anchor OR >= 2 members OR a full patient name
    target_blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    singletons: list[int] = []
    for cid in sorted(clusters, key=lambda r: sigs[r]):
        c = clusters[cid]
        if len(c.members) == 1 and c.patient_names and not c.has_full_patient_name and not c.has_global_id:
            singletons.append(cid)
            continue
        if c.has_strong_anchor or len(c.members) >= 2 or c.has_full_patient_name:
            for n in c.patient_names:
                for tok in n.skeleton_tokens:
                    if len(tok) >= 2:
                        target_blocks[("tok", tok)].append(cid)
            for ph in c.phones:
                target_blocks[("phone", ph)].append(cid)
            for d in c.dobs:
                target_blocks[("dob", f"{d.year:04d}")].append(cid)

    # Evaluate each singleton against existing anchor clusters ONLY (never singleton-to-singleton chaining)
    attachments: list[tuple[int, int, MatchStrength]] = []
    for sid in singletons:
        sc = clusters[sid]
        cands: set[int] = set()
        capped = False
        for n in sc.patient_names:
            for tok in n.skeleton_tokens:
                if len(tok) >= 2:
                    b = target_blocks.get(("tok", tok), ())
                    if len(b) > MAX_NAME_BLOCK:
                        capped = True
                    else:
                        cands.update(b)
        for ph in sc.phones:
            b = target_blocks.get(("phone", ph), ())
            if len(b) > MAX_ID_BLOCK:
                capped = True
            else:
                cands.update(b)
        for d in sc.dobs:
            b = target_blocks.get(("dob", f"{d.year:04d}"), ())
            if len(b) > MAX_ID_BLOCK:
                capped = True
            else:
                cands.update(b)

        matches: list[tuple[int, MatchStrength]] = []
        had_conflict = False
        for tid in sorted(cands, key=lambda r: sigs[r]):
            if tid == sid or tid not in clusters:
                continue
            dec = compare_profiles(sc, clusters[tid], allow_fragmented=True)
            if dec.outcome is MatchOutcome.CONFIDENT_MATCH:
                matches.append((tid, dec.strength))
            elif dec.outcome is MatchOutcome.CONFLICT:
                had_conflict = True

        if len(matches) == 1 and not capped:
            attachments.append((sid, matches[0][0], matches[0][1]))
        elif len(matches) > 1 or capped:
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += 1
        elif had_conflict:
            stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1
        else:
            stats.outcomes_by_type[MatchOutcome.INSUFFICIENT_EVIDENCE.value] += 1

    # Apply unique attachments, re-verifying conflict after any earlier attachment to the same cluster
    for sid, tid, _strength in attachments:
        rs, rt = find(sid), find(tid)
        if rs == rt or rs not in clusters or rt not in clusters:
            continue
        dec = compare_profiles(clusters[rs], clusters[rt], allow_fragmented=True)
        if dec.outcome is MatchOutcome.CONFIDENT_MATCH:
            merge_roots(rt, rs, dec.strength)
        elif dec.outcome is MatchOutcome.CONFLICT:
            stats.merges_blocked_by_conflict += 1
            stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1
