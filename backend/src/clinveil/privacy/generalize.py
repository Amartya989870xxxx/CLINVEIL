"""Quasi-identifier generalisation.

Scoring rule to respect: a generalised value must stay *truthful* (an age band that
excludes the real age scores 0 and is flagged). Location/PIN generalisation and
rare-value suppression arrive in Phase 4.
"""

from __future__ import annotations


def age_band(age: int, width: int = 5) -> str:
    """``47 -> "45-49"`` for width 5. The band always contains ``age``."""
    if age < 0:
        raise ValueError("age must be non-negative")
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"
