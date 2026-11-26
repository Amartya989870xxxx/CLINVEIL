"""Deterministic finding resolution and span application.

1. Drop candidates below the redaction threshold (``REDACT_THRESHOLD``).
2. Clinical protection: a person-name candidate overlapping a doctor keep span is
   always dropped; one overlapping any other keep span is dropped unless it rests
   on strong evidence (structured field, explicit label, relationship marker).
   Identifiers are never blocked by clinical spans (a validated phone cannot be a dose).
3. Overlaps: candidates are accepted greedily by (confidence, span length), so a
   full ABHA number beats the Aadhaar-shaped digits inside it and an insurance ID
   beats the phone-shaped digits inside it.
4. Adjacent spans of the same entity separated only by spaces/underscores/hyphens
   merge into one placeholder (``Orvila Tamsen`` -> one ``[NAME]``).
"""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass

from clinveil.detection.clinical import KeepSpan
from clinveil.detection.identifiers import Hit
from clinveil.models.findings import EntityType

REDACT_THRESHOLD = 0.7
NAME_TYPES = frozenset({EntityType.PATIENT_NAME, EntityType.RELATIVE_NAME})
STRONG_NAME_DETECTORS = frozenset(
    {"field", "patient_label", "relative_label", "relation_marker", "by_cue", "message_sender", "role_suffix"}
)
_MERGE_GAP = re.compile(r"[ _\- ]{0,2}")


@dataclass(frozen=True, slots=True)
class Resolved:
    hit: Hit
    clinical_conflict: bool


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def resolve(hits: list[Hit], keeps: list[KeepSpan], text: str) -> tuple[list[Resolved], int]:
    """Return accepted findings (sorted by start) and the number dropped by clinical protection.

    ``O((H + K) log(H + K))``: keep spans are sorted once and queried by bisection (a hit
    only looks at keeps that start before it ends and are long enough to reach it), and
    accepted spans are kept in a sorted, non-overlapping list, so an overlap test is one
    bisection instead of a scan of everything accepted so far.
    """
    protected = 0
    cands: list[Resolved] = []
    ks = sorted(keeps, key=lambda k: (k.start, k.end))
    k_starts = [k.start for k in ks]
    max_len = max((k.end - k.start for k in ks), default=0)
    for h in hits:
        if h.confidence < REDACT_THRESHOLD or h.end <= h.start:
            continue
        conflict = False
        if h.entity in NAME_TYPES and ks:
            hi = bisect_left(k_starts, h.end)  # keeps starting before the hit ends
            lo = bisect_left(k_starts, h.start - max_len)  # earlier ones cannot reach the hit
            hit_keeps = [k for k in ks[lo:hi] if k.end > h.start]
            if any(k.kind == "doctor" for k in hit_keeps):
                protected += 1
                continue
            if hit_keeps:
                if h.detector not in STRONG_NAME_DETECTORS:
                    protected += 1
                    continue
                conflict = True
        cands.append(Resolved(h, conflict))
    cands.sort(key=lambda r: (-r.hit.confidence, -(r.hit.end - r.hit.start), r.hit.start, r.hit.entity.value))
    accepted: list[Resolved] = []
    a_starts: list[int] = []
    a_ends: list[int] = []
    for c in cands:
        i = bisect_left(a_starts, c.hit.end)  # accepted spans starting before c ends
        if i and a_ends[i - 1] > c.hit.start:
            continue  # the closest one overlaps (accepted spans are disjoint, so ends ascend too)
        a_starts.insert(i, c.hit.start)
        a_ends.insert(i, c.hit.end)
        accepted.insert(i, c)
    accepted.sort(key=lambda r: r.hit.start)
    merged: list[Resolved] = []
    for r in accepted:
        if (
            merged
            and merged[-1].hit.entity is r.hit.entity
            and _MERGE_GAP.fullmatch(text[merged[-1].hit.end : r.hit.start])
        ):
            prev = merged[-1]
            merged[-1] = Resolved(
                Hit(
                    prev.hit.start,
                    r.hit.end,
                    r.hit.entity,
                    max(prev.hit.confidence, r.hit.confidence),
                    prev.hit.detector,
                ),
                prev.clinical_conflict or r.clinical_conflict,
            )
        else:
            merged.append(r)
    return merged, protected


def apply_spans(text: str, spans: list[tuple[int, int, str]]) -> str:
    """Replace non-overlapping ``(start, end, replacement)`` spans (any order)."""
    out = text
    for start, end, rep in sorted(spans, key=lambda s: s[0], reverse=True):
        out = out[:start] + rep + out[end:]
    return out
