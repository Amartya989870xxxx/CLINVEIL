"""Phase 2.1 verification (S1): an input symlink that leaves the input root is never opened.

An audit hook records every ``open`` the pipeline performs. Escaping symlinks (to a
regular file, to a FIFO), broken symlinks and their targets must never be opened for
reading. Internal symlinks are read through their verified real path. The official
validator must still accept the release.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import TEST_SECRET

PAT = "Orvila Tamsen"


def _tree(tmp_path: Path, *, fifo: bool) -> tuple[Path, Path]:
    inp, ext = tmp_path / "in", tmp_path / "ext"
    (inp / "sub").mkdir(parents=True)
    ext.mkdir()
    (ext / "secret.txt").write_text(f"Name: {PAT}, Mob 9876543210")
    (inp / "ok.txt").write_text("BP 120/80")
    (inp / "sub" / "real.txt").write_text("Name: Kelvar Dunmore")
    (inp / "reg.csv").write_text(f"MRN,Patient Name\nTST/26/000901,{PAT}\n")
    (inp / "escape.txt").symlink_to(ext / "secret.txt")
    (inp / "Orvila_Tamsen_scan.json").symlink_to(ext / "secret.txt")  # PII in the link's own name
    (inp / "internal.txt").symlink_to(Path("sub") / "real.txt")
    if fifo:
        os.mkfifo(ext / "pipe")
        (inp / "to_fifo.txt").symlink_to(ext / "pipe")
        (inp / "dangling.txt").symlink_to(ext / "missing.txt")
    return inp, ext


def _run_traced(inp: Path, out: Path) -> list[str]:
    from clinveil.config.policy import Policy
    from clinveil.pipeline import run
    from clinveil.security.secrets import ReleaseSecret

    opened: list[str] = []

    def hook(event: str, args: tuple) -> None:
        if event in ("open", "os.open") and args and isinstance(args[0], str | bytes | os.PathLike):
            opened.append(os.fsdecode(args[0]))

    sys.addaudithook(hook)  # hooks cannot be removed; this one only appends to a local list
    run(inp, out, ReleaseSecret(TEST_SECRET.encode()), Policy())
    return opened


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_escaping_broken_and_fifo_links_are_never_opened(tmp_path):
    inp, ext = _tree(tmp_path, fifo=True)
    out = tmp_path / "out"
    opened = _run_traced(inp, out)
    read_side = [p for p in opened if not p.startswith(str(out))]
    forbidden = ("escape.txt", "Orvila_Tamsen_scan.json", "to_fifo.txt", "dangling.txt", str(ext))
    assert not [p for p in read_side if any(f in p for f in forbidden)]
    # the internal link is read through its verified real path
    assert any(p.endswith(os.path.join("sub", "real.txt")) for p in read_side)
    rep = json.loads((out / "report.json").read_text())
    statuses = sorted((e.get("reason") or "", e["status"]) for e in rep["files"])
    assert statuses.count(("symlink_outside_input", "suppressed")) == 3
    assert ("broken_symlink", "quarantined") in statuses
    released = "".join(p.read_text() for p in out.rglob("*") if p.is_file()) + " ".join(p.name for p in out.rglob("*"))
    assert "Orvila" not in released and "Tamsen" not in released and "9876543210" not in released


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_fifo_inside_the_root_is_reported_not_opened(tmp_path):
    """A FIFO inside the input root used to be dropped silently; it is now reported unopened."""
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "ok.txt").write_text("BP 120/80")
    os.mkfifo(inp / "pipe.txt")
    out = tmp_path / "out"
    opened = _run_traced(inp, out)
    assert not [p for p in opened if p.endswith("pipe.txt") and not p.startswith(str(out))]
    rep = json.loads((out / "report.json").read_text())
    assert [e.get("reason") for e in rep["files"] if e["status"] == "quarantined"] == ["not_a_regular_file"]
    assert rep["counts"]["files_total"] == 2


def test_internal_link_exported_and_external_placeholders_are_empty(tmp_path):
    inp, _ = _tree(tmp_path, fifo=False)
    out = tmp_path / "out"
    _run_traced(inp, out)
    san = out / "sanitized"
    assert "Kelvar" not in (san / "internal.txt").read_text() and (san / "internal.txt").read_text()
    assert (san / "escape.txt").read_bytes() == b""
    json_placeholders = [p for p in san.iterdir() if p.suffix == ".json"]
    assert len(json_placeholders) == 1 and json.loads(json_placeholders[0].read_text()) == {}
    assert "Orvila" not in json_placeholders[0].name  # the link's PII filename is renamed


def _validate(toolkit: Path, inp: Path, out: Path) -> str:
    return subprocess.run(
        [sys.executable, str(toolkit / "validate_output.py"), "--input", str(inp), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout


@pytest.mark.toolkit
def test_official_validator_accepts_release_with_symlinks(toolkit, tmp_path):
    """No FIFO and no dangling link here: the official validator itself reads link targets
    (it would block on a FIFO and crash on a dangling link)."""
    inp, _ = _tree(tmp_path, fifo=False)
    (inp / "Orvila_Tamsen_scan.json").unlink()
    out = tmp_path / "out"
    _run_traced(inp, out)
    assert "CONTRACT OK" in _validate(toolkit, inp, out)


@pytest.mark.toolkit
def test_pii_named_escaping_link_trades_one_contract_error_for_privacy(toolkit, tmp_path):
    """Known, documented conflict (PHASE2_REMEDIATION.md, S1): an escaping link whose own name
    holds PII is renamed. Without reading the target there is no SHA-256 to declare the mapping
    with, so the official validator reports exactly that one input as undeclared."""
    inp, _ = _tree(tmp_path, fifo=False)
    out = tmp_path / "out"
    _run_traced(inp, out)
    v = _validate(toolkit, inp, out)
    assert "ERROR 1 input files are neither exported (same path) nor declared" in v
    assert v.count("ERROR") == 1
