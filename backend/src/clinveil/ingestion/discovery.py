# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Deterministic, containment-checked input discovery."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from clinveil.security.paths import is_within

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class InputFile:
    path: Path
    rel: str  # POSIX path relative to the input root (may itself contain PII: never log it)
    size: int
    is_symlink: bool
    escapes_root: bool

    def __repr__(self) -> str:  # never let a filename reach a log line by accident
        return f"InputFile(size={self.size})"


def discover(root: Path) -> Iterator[InputFile]:
    """Yield every file under ``root`` in the starter's order (sorted ``rglob``).

    Symlinked *directories* are not traversed (``rglob`` default). Symlinked *files*
    are yielded but flagged so the pipeline can quarantine them without parsing.
    """
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        link = p.is_symlink()
        escapes = link and not is_within(p, root)
        try:
            size = p.stat().st_size
        except OSError:
            size = -1
        yield InputFile(path=p, rel=p.relative_to(root).as_posix(), size=size, is_symlink=link, escapes_root=escapes)


def sha256_file(path: Path) -> str:
    """Streamed SHA-256 so oversized files are hashed without loading them."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
