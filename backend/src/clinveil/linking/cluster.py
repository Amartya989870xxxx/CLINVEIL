"""Bounded blocking and 3-stage conflict-aware conservative patient clustering.

Never runs naive transitive connected components. Every stage first collects its candidate
edges between the CURRENT clusters, then resolves each connected group of edges as a whole
(Phase 3.3, PASS1-NEW-6) instead of merging greedily in key or record order:

* a group merges only if EVERY pair of its clusters is compatible (complete linkage);
* a cluster that links two mutually incompatible clusters (a partial-evidence "bridge", e.g. a
  record carrying one person's Aadhaar and another person's PAN) ABSTAINS and stays frozen for
  all later stages, so its excluded evidence cannot re-enter through a weaker stage;
* the result depends only on the set of records and their evidence, never on input order,
  file names or record locators.

Stages:
* Stage A: Validated global IDs.
* Stage B: Hospital-scoped local IDs.
* Stage C1: Corroborated full-name merges (bounded convergence passes).
* Stage C2: Unique singleton/fragmented attachments (e.g. ``<first name>, W/o <relative>``
  or ``<first name> + <phone>``) attached ONLY when exactly one existing cluster matches
  with zero conflicts, and never together with a conflicting co-attachment. Never chains weak
  singletons together.
"""

from __future__ import annotations

from collections import defaultdict

from clinveil.linking.matcher import (
    ClusterProfile,
    compare_profiles,
    is_weak_edge,
    shared_global_ids,
    strong_pair_conflicts,
    weak_path_conflicts,
)
from clinveil.linking.models import (
    LinkingStats,
    MatchOutcome,
    MatchStrength,
    PairDecision,
    RecordEvidence,
)

#: Maximum distinct clusters in a single blocking bucket before skipping as pathological/ambiguous.
MAX_ID_BLOCK = 128
MAX_NAME_BLOCK = 64
#: Maximum clusters in one connected group of candidate edges. Complete-linkage verification is
#: pairwise inside a group, so larger groups abstain (bounded work, never quadratic in the input).
MAX_COMPONENT = 256
_GENERIC_MRN_REASONS = frozenset({"shared_external_mrn", "shared_external_mrn_with_name"})


def cluster_records(evidence_list: list[RecordEvidence]) -> tuple[list[ClusterProfile], LinkingStats]:
    """Conservatively resolve ``evidence_list`` into disjoint patient :class:`ClusterProfile` s."""
    stats = LinkingStats(records_total=len(evidence_list))
    # Sort input evidence deterministically by content signature (traversal-order-independent)
    ordered = sorted(evidence_list, key=lambda e: e.canonical_signature())
    # Hospital slugs established reliably anywhere in this run (facility fields, FHIR, letterheads, …)
    reliable_slugs = frozenset(
        e.hospital for e in ordered if e.hospital and e.hospital_reliable and not e.is_external_lab
    )
    active_ids: list[int] = []
    clusters: dict[int, ClusterProfile] = {}
    sigs: dict[int, tuple[str, ...]] = {}
    for idx, ev in enumerate(ordered):
        if ev.has_any_evidence and not ev.ambiguous_doc:
            stats.records_with_evidence += 1
        elif ev.ambiguous_doc:
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += 1
        clusters[idx] = ClusterProfile.from_record(ev, reliable_slugs)
        sigs[idx] = ev.canonical_signature()
        if ev.has_any_evidence and not ev.ambiguous_doc:
            active_ids.append(idx)

    parent = {i: i for i in clusters}
    #: Ambiguous bridge clusters: never merged again in any later stage (PASS1-NEW-6).
    frozen: set[int] = set()

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
    global_blocks = _build_global_blocks(active_ids, clusters)  # nothing is frozen yet
    _merge_from_blocks(
        global_blocks,
        clusters=clusters,
        sigs=sigs,
        find=find,
        merge_roots=merge_roots,
        stats=stats,
        allowed_strengths={MatchStrength.STRONG_GLOBAL},
        max_block=MAX_ID_BLOCK,
        frozen=frozen,
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
        frozen=frozen,
    )

    # ------------------------------------------------------------------ Stage C1: Corroborated Full Names
    # Bounded convergence (up to 3 passes) so multi-hospital clusters that gain a corroborator
    # from an earlier merge can cleanly link in the next pass; each pass is resolved set-wise.
    for _ in range(3):
        before = len(clusters)
        _merge_corroborated_full_names(clusters, sigs, find, merge_roots, stats, frozen)
        if len(clusters) == before:
            break

    # ------------------------------------------------------------------ Stage C2: Unique Fragmented Attachments
    _attach_fragmented_singletons(clusters, sigs, find, merge_roots, stats, frozen)

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
        # insurance / e-mail are household-shareable: corroborators only (Stage C), never Stage A (R3)
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
    frozen: set[int],
) -> None:
    """Collect identifier edges between the current clusters, then resolve them set-wise."""
    edges: dict[tuple[int, int], PairDecision] = {}
    seen: set[tuple[int, int]] = set()
    for _key in sorted(blocks):
        roots = sorted({find(m) for m in blocks[_key]} - frozen, key=lambda r: sigs[r])
        if len(roots) < 2:
            continue
        if len(roots) > max_block:
            stats.blocks_capped_ambiguous += 1
            continue
        for i in range(len(roots)):
            for j in range(i + 1, len(roots)):
                pair = _pair(roots[i], roots[j])
                if pair in seen:
                    continue
                seen.add(pair)
                dec = compare_profiles(clusters[pair[0]], clusters[pair[1]], allow_fragmented=False)
                if dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength in allowed_strengths:
                    edges[pair] = dec
                elif dec.outcome is MatchOutcome.CONFLICT:
                    stats.merges_blocked_by_conflict += 1
                    stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1
    _resolve_edge_groups(
        edges, clusters=clusters, sigs=sigs, find=find, merge_roots=merge_roots, stats=stats, frozen=frozen
    )


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _resolve_edge_groups(
    edges: dict[tuple[int, int], PairDecision],
    *,
    clusters: dict[int, ClusterProfile],
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
    stats: LinkingStats,
    frozen: set[int],
    name_stage: bool = False,
) -> None:
    """Merge each connected group of candidate edges only if it is complete-linkage consistent.

    Order-independent by construction: groups, conflicts and bridges are computed on sets of the
    clusters that existed when the stage started; merging happens only after a group is accepted.

    ``conflict(u, w)`` for two clusters of a group that are not directly matched:
    * identifier groups, when ``u`` and ``w`` are joined by a path of STRONG edges only (validated
      global IDs / verified same-hospital MRNs): :func:`strong_pair_conflicts`, i.e. contradicting
      person-unique IDs, relative-owned IDs, gender, DOB, birth year, age or whole names. Soft
      homonym vetoes (relative name, village, district) are not applied between such pairs, because
      one patient's records legitimately name different relatives (father in one, spouse in another)
      and the strong IDs already prove identity;
    * identifier groups, when every path between ``u`` and ``w`` uses a WEAK edge (unverified-scope,
      prefixed or external-lab MRN, which does not prove identity on its own):
      :func:`weak_path_conflicts`, i.e. every homonym (relative name, village, district), R7 and
      complete-linkage veto that a DIRECT weak MRN match between ``u`` and ``w`` would have to pass
      (P33-F1). Otherwise a partial record (an MRN and a name only) could join two homonyms that a
      direct comparison keeps apart;
    * name groups: the full :func:`compare_profiles` verdict is ``CONFLICT`` (all homonym and
      complete-linkage vetoes), because names alone do not prove identity.

    A cluster adjacent to two mutually conflicting clusters is an ambiguous bridge. A cluster that
    links two clusters of different hospitals through a generic external-lab MRN edge is also
    ambiguous (the same generic MRN number exists at both, NEW-3). Bridges abstain and are frozen; the remainder is
    split and re-resolved. If conflicts remain without a direct bridge, the non-conflicting
    connector clusters are frozen; if there are none, the whole group abstains and every member is
    frozen. A group above :data:`MAX_COMPONENT` abstains and every member is frozen (P33-F5), so no
    abstained record can re-enter through a later, weaker stage.
    """
    adj: dict[int, set[int]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    memo: dict[tuple[int, int], bool] = {}
    strong_memo: dict[tuple[int, int, bool], bool] = {}
    weak_memo: dict[tuple[int, int], bool] = {}
    global_label: dict[int, int] = {}

    def strong_conflict(u: int, w: int) -> bool:
        # A strong path that needs a verified local ID (not validated global IDs alone) keeps R7
        # (P33-PASS3-F2): shared OPD numbers cannot chain two different UHIDs together.
        via_local = global_label[u] != global_label[w]
        skey = (*_pair(u, w), via_local)
        if skey not in strong_memo:
            strong_memo[skey] = bool(strong_pair_conflicts(clusters[u], clusters[w], via_local_id=via_local))
        return strong_memo[skey]

    def conflict(u: int, w: int, label: dict[int, int], profiles: dict[int, ClusterProfile]) -> bool:
        key = _pair(u, w)
        cu, cw = clusters[u], clusters[w]
        if name_stage:
            if key not in memo:
                memo[key] = compare_profiles(cu, cw, allow_fragmented=False).outcome is MatchOutcome.CONFLICT
            return memo[key]
        if label[u] == label[w]:
            return strong_conflict(u, w)
        # Linked only through a weak edge: judge the two strong sub-components (each already proven
        # to be one patient) as a direct weak MRN match between them would be judged (P33-F1).
        lkey = _pair(label[u], label[w])
        if lkey not in weak_memo:
            weak_memo[lkey] = bool(weak_path_conflicts(profiles[label[u]], profiles[label[w]]))
        return weak_memo[lkey] or strong_conflict(u, w)

    def components(nodes: set[int]) -> list[list[int]]:
        out: list[list[int]] = []
        todo = set(nodes)
        for start in sorted(nodes, key=lambda r: sigs[r]):
            if start not in todo:
                continue
            todo.discard(start)
            comp, stack = [start], [start]
            while stack:
                for nb in adj[stack.pop()]:
                    if nb in todo:
                        todo.discard(nb)
                        comp.append(nb)
                        stack.append(nb)
            out.append(sorted(comp, key=lambda r: sigs[r]))
        return out

    work = components(set(adj))
    while work:
        comp = work.pop(0)
        if len(comp) < 2:
            continue
        if len(comp) > MAX_COMPONENT:
            # Abstain AND freeze every member: none may re-enter Stage B, C1 or C2 (P33-F5).
            stats.blocks_capped_ambiguous += 1
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += len(comp)
            frozen.update(comp)
            continue
        members = set(comp)
        strong_label = _strong_edge_labels(comp, adj, edges, name_stage=name_stage)
        global_label.clear()
        if not name_stage:
            global_label.update(_strong_edge_labels(comp, adj, edges, name_stage=False, global_only=True))
        weak_memo.clear()  # sub-component labels are per group
        profiles = {} if name_stage else _sub_component_profiles(comp, strong_label, clusters)
        bad_pairs = {
            (u, w)
            for i, u in enumerate(comp)
            for w in comp[i + 1 :]
            if _pair(u, w) not in edges and conflict(u, w, strong_label, profiles)
        }
        bridges: set[int] = set()
        for v in comp:
            nbrs = sorted((n for n in adj[v] if n in members), key=lambda r: sigs[r])
            for i, u in enumerate(nbrs):
                for w in nbrs[i + 1 :]:
                    if _pair(u, w) in edges:
                        continue
                    clash = (u, w) in bad_pairs or (w, u) in bad_pairs
                    if clash or (
                        not name_stage and _weak_cross_hospital(edges[_pair(v, u)], edges[_pair(v, w)], u, w, clusters)
                    ):
                        bridges.add(v)
        if not bad_pairs and not bridges:
            _merge_group(comp, adj, edges, sigs=sigs, find=find, merge_roots=merge_roots)
            continue
        if not bridges:
            in_conflict = {x for p in bad_pairs for x in p}
            bridges = members - in_conflict
        if not bridges:
            stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += len(comp)
            frozen.update(comp)
            continue
        frozen |= bridges
        stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += len(bridges)
        rest = members - bridges
        sub_adj_nodes = {x for x in rest if adj[x] & rest}
        for sub in components(sub_adj_nodes):
            work.append([x for x in sub if x in rest])


def _strong_edge_labels(
    comp: list[int],
    adj: dict[int, set[int]],
    edges: dict[tuple[int, int], PairDecision],
    *,
    name_stage: bool,
    global_only: bool = False,
) -> dict[int, int]:
    """Label each member of ``comp`` by its sub-component under STRONG identifier edges only.

    Two members with the same label are linked by validated global IDs / verified same-hospital
    MRNs alone; two members with different labels are linked only through at least one weak edge
    (P33-F1). In a name stage no edge proves identity, so every member gets its own label.
    ``global_only``: label by validated global-ID edges (Tier 1) alone (P33-PASS3-F2)."""
    if name_stage:
        return {v: i for i, v in enumerate(comp)}
    members = set(comp)
    label: dict[int, int] = {}
    for start in comp:  # ``comp`` is sorted by signature: labels are deterministic
        if start in label:
            continue
        label[start] = start
        stack = [start]
        while stack:
            v = stack.pop()
            for nb in adj[v]:
                dec = edges[_pair(v, nb)]
                linked = dec.strength is MatchStrength.STRONG_GLOBAL if global_only else not is_weak_edge(dec)
                if nb in members and nb not in label and linked:
                    label[nb] = start
                    stack.append(nb)
    return label


def _sub_component_profiles(
    comp: list[int], label: dict[int, int], clusters: dict[int, ClusterProfile]
) -> dict[int, ClusterProfile]:
    """Union profile of each strong sub-component (a fresh object: ``clusters`` is never mutated)."""
    by_label: dict[int, list[int]] = defaultdict(list)
    for v in comp:
        by_label[label[v]].append(v)
    out: dict[int, ClusterProfile] = {}
    for lab, vs in by_label.items():
        if len(vs) == 1:
            out[lab] = clusters[vs[0]]
            continue
        merged = ClusterProfile()
        for v in vs:
            merged.absorb(clusters[v])
        out[lab] = merged
    return out


def _weak_cross_hospital(
    e1: PairDecision, e2: PairDecision, u: int, w: int, clusters: dict[int, ClusterProfile]
) -> bool:
    """``u`` and ``w`` come from different hospitals and at least one of them is reached only through
    a GENERIC external-lab MRN number, which both hospitals may have issued to different patients (NEW-3).

    Distinctive issuer-prefixed UHIDs (``JJH-…``, ``SNJ-…``) name their issuer, so a document citing
    two of them is cross-hospital evidence, not an ambiguity.
    """
    if not (_GENERIC_MRN_REASONS & set(e1.reasons) or _GENERIC_MRN_REASONS & set(e2.reasons)):
        return False
    cu, cw = clusters[u], clusters[w]
    disjoint = bool(cu.hospitals and cw.hospitals and cu.hospitals.isdisjoint(cw.hospitals))
    return disjoint and not shared_global_ids(cu, cw)


def _merge_group(
    comp: list[int],
    adj: dict[int, set[int]],
    edges: dict[tuple[int, int], PairDecision],
    *,
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
) -> None:
    """Merge an accepted group along a deterministic spanning tree (the union does not depend on it)."""
    members = set(comp)
    seen = {comp[0]}
    queue = [comp[0]]
    while queue:
        v = queue.pop(0)
        for nb in sorted((n for n in adj[v] if n in members and n not in seen), key=lambda r: sigs[r]):
            seen.add(nb)
            queue.append(nb)
            merge_roots(find(v), find(nb), edges[_pair(v, nb)].strength)


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
    frozen: set[int],
) -> None:
    blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    for cid, c in clusters.items():
        if cid in frozen or not c.has_full_patient_name:
            continue
        for k in _name_block_keys(c):
            blocks[k].append(cid)

    # A full-name block above the cap is a dense homonym group that cannot be evaluated safely:
    # its members ABSTAIN from name-based merging, instead of being re-reached through phone or
    # DOB blocks (Phase 3.1). Strong-ID merges (Stages A/B) are unaffected.
    capped_ids: set[int] = set()
    for _key, members in blocks.items():
        if _key[0] == "full" and len({find(m) for m in members}) > MAX_NAME_BLOCK:
            capped_ids.update(find(m) for m in members)

    edges: dict[tuple[int, int], PairDecision] = {}
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
                if a in capped_ids or b in capped_ids:
                    continue
                pair = _pair(a, b)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                dec = compare_profiles(clusters[pair[0]], clusters[pair[1]], allow_fragmented=False)
                if dec.outcome is MatchOutcome.CONFIDENT_MATCH and dec.strength is MatchStrength.CORROBORATED_NAME:
                    edges[pair] = dec
                elif dec.outcome is MatchOutcome.CONFLICT:
                    stats.merges_blocked_by_conflict += 1
                    stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1

    # A name-matched cluster adjacent to two mutually conflicting clusters is ambiguous and abstains;
    # a group merges only if every pair in it is conflict-free (complete linkage).
    _resolve_edge_groups(
        edges,
        clusters=clusters,
        sigs=sigs,
        find=find,
        merge_roots=merge_roots,
        stats=stats,
        frozen=frozen,
        name_stage=True,
    )


def _attach_fragmented_singletons(
    clusters: dict[int, ClusterProfile],
    sigs: dict[int, tuple[str, ...]],
    find,
    merge_roots,
    stats: LinkingStats,
    frozen: set[int],
) -> None:
    """Attach remaining fragmented singletons (e.g. first name + relative/phone/village+age)
    ONLY when they match a SINGLE unique anchor cluster with zero conflicts.
    """
    # Anchor targets: clusters with a strong anchor OR >= 2 members OR a full patient name
    target_blocks: dict[tuple[str, str], list[int]] = defaultdict(list)
    singletons: list[int] = []
    for cid in sorted(clusters, key=lambda r: sigs[r]):
        if cid in frozen:
            continue
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

    # Two singletons attaching to the same anchor must also be compatible with each other;
    # otherwise neither attaches (decided on the whole set, so the result is order-independent).
    by_target: dict[int, list[int]] = defaultdict(list)
    for sid, tid, _strength in attachments:
        by_target[tid].append(sid)
    for tid in sorted(by_target, key=lambda r: sigs[r]):
        sids = sorted(by_target[tid], key=lambda r: sigs[r])
        clashing = {
            x
            for i, s1 in enumerate(sids)
            for s2 in sids[i + 1 :]
            if compare_profiles(clusters[s1], clusters[s2], allow_fragmented=True).outcome is MatchOutcome.CONFLICT
            for x in (s1, s2)
        }
        stats.outcomes_by_type[MatchOutcome.AMBIGUOUS.value] += len(clashing)
        for sid in sids:
            if sid in clashing:
                continue
            rs, rt = find(sid), find(tid)
            if rs == rt:
                continue
            # Re-verify against the anchor as it stands (it may already hold a compatible co-attachment)
            dec = compare_profiles(clusters[rs], clusters[rt], allow_fragmented=True)
            if dec.outcome is MatchOutcome.CONFIDENT_MATCH:
                merge_roots(rt, rs, dec.strength)
            elif dec.outcome is MatchOutcome.CONFLICT:
                stats.merges_blocked_by_conflict += 1
                stats.outcomes_by_type[MatchOutcome.CONFLICT.value] += 1
