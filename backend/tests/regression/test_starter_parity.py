"""Phase 0 guarantee: the modular refactor is byte-identical to the official starter.

Retire (delete) this test deliberately at the first Phase 1/2 change that is
*meant* to alter output. Until then it proves the refactor broke nothing.
"""

import json
import os
import subprocess
import sys

import pytest

from conftest import TEST_SECRET, run_cli

pytestmark = [pytest.mark.toolkit, pytest.mark.starter_parity]


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_byte_parity_with_starter_on_practice_data(toolkit, tmp_path):
    inp = toolkit / "dev" / "input"
    starter_out, ours_out = tmp_path / "starter", tmp_path / "ours"
    env = dict(os.environ, RAKSHA_SECRET=TEST_SECRET)
    subprocess.run(
        [sys.executable, str(toolkit / "starter" / "main.py"), "--input", str(inp), "--output", str(starter_out)],
        env=env,
        check=True,
        capture_output=True,
    )
    ours = run_cli(inp, ours_out)
    assert ours.code == 0, ours.stderr

    assert _tree(starter_out / "sanitized") == _tree(ours_out / "sanitized")
    assert (starter_out / "records.jsonl").read_bytes() == (ours_out / "records.jsonl").read_bytes()
    a = json.loads((starter_out / "report.json").read_text(encoding="utf-8"))
    b = json.loads((ours_out / "report.json").read_text(encoding="utf-8"))
    assert a["files"] == b["files"]
    assert a["counts"] == b["counts"]
    assert a["schema"] == b["schema"]
