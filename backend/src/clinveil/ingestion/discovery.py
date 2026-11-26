# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Deterministic, containment-checked input discovery."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from clinveil.security.errors import QuarantineError

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class InputFile:
    path: Path
    rel: str  # POSIX path relative to the input root (may itself contain PII: never log it)
    size: int
    is_symlink: bool
    escapes_root: bool
    broken: bool = False  # a symlink whose target does not exist (nothing can be read)
    special: bool = False  # a FIFO, socket or device node: never opened (it could block or never end)
    ordinal: int = 0  # position in the sorted discovery order (stable, non-identifying)

    def __repr__(self) -> str:  # never let a filename reach a log line by accident
        return f"InputFile(size={self.size})"


def discover(root: Path) -> Iterator[InputFile]:
    """Yield every file under ``root`` in the starter's order (sorted ``rglob``).

    Classification uses ``lstat`` and symlink resolution only (metadata, never file
    content). Symlinked *directories* are not traversed (``rglob`` default) and, like
    ``os.walk`` in the official validator, are not files. A symlink to a non-directory
    is yielded and flagged: ``broken`` (target missing) or ``escapes_root`` (target
    outside the input root). Neither kind is ever opened (see :func:`read_input`).
    """
    root_real = root.resolve()
    candidates = []
    for x in root.rglob("*"):
        try:
            st = x.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            try:
                if x.is_dir():  # follows the link for metadata only; directories are not files
                    continue
            except OSError:
                pass
            candidates.append(x)
        elif not stat.S_ISDIR(st.st_mode):  # regular files, and special files to be reported unopened
            candidates.append(x)
    for n, p in enumerate(sorted(candidates)):
        link = p.is_symlink()
        broken = escapes = special = False
        size = -1
        if link:
            try:
                real = p.resolve(strict=True)
            except (OSError, RuntimeError):  # missing target or a symlink loop
                broken = True
            else:
                escapes = not _within(real, root_real)
                if not escapes:
                    # an internal link may point at a FIFO/socket/device: metadata only, never opened
                    with contextlib.suppress(OSError):
                        st_real = real.stat()
                        size = st_real.st_size
                        special = not stat.S_ISREG(st_real.st_mode)
        else:
            with contextlib.suppress(OSError):
                st = p.lstat()
                size = st.st_size
                special = not stat.S_ISREG(st.st_mode)
        yield InputFile(
            path=p,
            rel=p.relative_to(root).as_posix(),
            size=0 if (broken or escapes) else size,
            is_symlink=link,
            escapes_root=escapes,
            broken=broken,
            special=special,
            ordinal=n,
        )


def _within(real: Path, root_real: Path) -> bool:
    try:
        real.relative_to(root_real)
    except ValueError:
        return False
    return True


def _open_regular(path: Path, root: Path) -> int:
    """Open the *real* file behind ``path`` read-only, refusing anything that is not a regular file
    inside ``root``.

    * the path is resolved first and must stay inside the input root (an escaping or dangling
      symlink is never opened: callers must not even ask, but this is the last line of defence);
    * the resolved path is opened with ``O_NOFOLLOW`` (its last component cannot have been swapped
      for a symlink since resolution) and ``O_NONBLOCK`` (a FIFO or device cannot hang the run);
    * ``fstat`` on the opened descriptor must report a regular file.
    """
    try:
        real = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise QuarantineError("broken_symlink") from exc
    if not _within(real, root.resolve()):
        raise QuarantineError("symlink_outside_input")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(real, flags)
    except OSError as exc:
        raise QuarantineError("not_a_regular_file") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise QuarantineError("not_a_regular_file")
    return fd


def read_input(path: Path, root: Path, max_bytes: int) -> bytes:
    """Bytes of an input file inside ``root`` (at most ``max_bytes``; larger raises ``file_too_large``)."""
    fd = _open_regular(path, root)
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise QuarantineError("file_too_large")
    return data


def sha256_input(path: Path, root: Path) -> str:
    """Streamed SHA-256 of an input file inside ``root`` (oversized files are hashed, never loaded)."""
    h = hashlib.sha256()
    with os.fdopen(_open_regular(path, root), "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def unread_id(f: InputFile) -> str:
    """Report identifier for an input whose bytes are deliberately never read (escaping or broken
    symlink). It is not a content hash: it is derived only from the file's discovery position,
    so it reveals nothing about the link, its target path or its content."""
    return hashlib.sha256(f"clinveil/unread-input/{f.ordinal}".encode()).hexdigest()


def sha256_file(path: Path) -> str:
    """Streamed SHA-256 of a path already known to be safe (kept for tools and tests)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
