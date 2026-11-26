"""Path containment: inputs never escape the input root, outputs never escape ``sanitized/``."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class PathEscapeError(Exception):
    pass


def is_within(path: Path, root: Path) -> bool:
    """True if ``path`` (after resolving existing symlinks) lies inside ``root``."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def safe_join(root: Path, rel_posix: str) -> Path:
    """Join a relative POSIX path under ``root``.

    Rejects absolute paths, ``..``/``.`` components, and destinations that a
    pre-existing symlinked directory would redirect outside ``root``.
    """
    rel = PurePosixPath(rel_posix)
    if rel.is_absolute() or not rel.parts or any(p in ("..", ".") for p in rel.parts):
        raise PathEscapeError("unsafe relative path")
    dest = root.joinpath(*rel.parts)
    if not is_within(dest, root):
        raise PathEscapeError("path escapes output root")
    return dest
