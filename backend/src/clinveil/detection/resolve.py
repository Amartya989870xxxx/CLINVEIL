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
    """Return accepted findings (sorted by start) and the number dropped by clinical protection."""
    protected = 0
    cands: list[Resolved] = []
    for h in hits:
        if h.confidence < REDACT_THRESHOLD or h.end <= h.start:
            continue
        conflict = False
        if h.entity in NAME_TYPES:
            hit_keeps = [k for k in keeps if _overlaps(h.start, h.end, k.start, k.end)]
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
    for c in cands:
        if not any(_overlaps(c.hit.start, c.hit.end, a.hit.start, a.hit.end) for a in accepted):
            accepted.append(c)
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
