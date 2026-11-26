"""Linker interface. Phase 0 links nothing (starter behaviour).

A wrong link costs more than no link, so returning ``None`` is always *safe*;
it just scores 0 for identity resolution. The real implementation is a two-pass
design: pass 1 extracts evidence from every record of every file, pass 2 clusters
and returns a canonical cluster key per record locator.
"""

from __future__ import annotations


def link_record(_record_text: str) -> str | None:
    """Return a canonical patient cluster key for a record, or ``None``."""
    return None
