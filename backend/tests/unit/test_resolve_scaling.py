"""Audit E4: the bisection-based resolver equals the original quadratic algorithm and scales."""

from __future__ import annotations

import random
import time

from clinveil.detection.clinical import KeepSpan
from clinveil.detection.identifiers import Hit
from clinveil.detection.resolve import _MERGE_GAP, NAME_TYPES, REDACT_THRESHOLD, STRONG_NAME_DETECTORS, resolve
from clinveil.models.findings import EntityType as E


def _reference(hits, keeps, text):
    """The Phase 2 algorithm (O(H*K + H^2)), kept here as the specification."""

    def ov(a0, a1, b0, b1):
        return a0 < b1 and b0 < a1

    cands = []
    for h in hits:
        if h.confidence < REDACT_THRESHOLD or h.end <= h.start:
            continue
        if h.entity in NAME_TYPES:
            hk = [k for k in keeps if ov(h.start, h.end, k.start, k.end)]
            if any(k.kind == "doctor" for k in hk) or (hk and h.detector not in STRONG_NAME_DETECTORS):
                continue
        cands.append(h)
    cands.sort(key=lambda h: (-h.confidence, -(h.end - h.start), h.start, h.entity.value))
    acc = []
    for h in cands:
        if not any(ov(h.start, h.end, a.start, a.end) for a in acc):
            acc.append(h)
    merged: list[tuple[int, int, E]] = []
    for h in sorted(acc, key=lambda h: h.start):
        if merged and merged[-1][2] is h.entity and _MERGE_GAP.fullmatch(text[merged[-1][1] : h.start]):
            merged[-1] = (merged[-1][0], h.end, h.entity)
        else:
            merged.append((h.start, h.end, h.entity))
    return merged


def test_resolver_matches_reference_on_random_inputs():
    rng = random.Random(7)
    ents = [E.PATIENT_NAME, E.PHONE, E.MRN, E.RELATIVE_NAME]
    text = "a b" * 40
    for _ in range(3000):
        hits = []
        for _ in range(rng.randint(0, 15)):
            s = rng.randint(0, 80)
            hits.append(
                Hit(
                    s,
                    s + rng.randint(1, 12),
                    rng.choice(ents),
                    rng.choice([0.6, 0.75, 0.8, 0.85, 0.9, 0.95]),
                    rng.choice(["x", "field", "title"]),
                )
            )
        keeps = []
        for _ in range(rng.randint(0, 5)):
            s = rng.randint(0, 80)
            keeps.append(KeepSpan(s, s + rng.randint(1, 20), rng.choice(["doctor", "lab"])))
        got, _ = resolve(hits, keeps, text)
        assert [(r.hit.start, r.hit.end, r.hit.entity) for r in got] == _reference(hits, keeps, text)


def test_resolver_is_near_linear():
    n = 64_000
    hits = [Hit(i * 10, i * 10 + 6, E.PATIENT_NAME, 0.9, "x") for i in range(n)]
    keeps = [KeepSpan(i * 50, i * 50 + 4, "lab") for i in range(n // 5)]
    t0 = time.perf_counter()
    resolve(hits, keeps, "x" * (n * 10))
    assert time.perf_counter() - t0 < 5  # the quadratic version needed ~10 s for 16,000 hits
