"""SPEC §7: same input + same secret -> byte-identical sanitized/ and records.jsonl;
a different secret -> different pseudonyms and date shifts."""

import pytest

from conftest import run_cli


def _digest(out):
    files = sorted(p for p in (out / "sanitized").rglob("*") if p.is_file())
    files.append(out / "records.jsonl")
    return [(p.relative_to(out).as_posix(), p.read_bytes()) for p in files]


def test_same_secret_is_byte_identical(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    a = run_cli(inp, tmp_path / "a", secret="same")
    b = run_cli(inp, tmp_path / "b", secret="same")
    assert a.code == b.code == 0
    assert _digest(a.out) == _digest(b.out)


@pytest.mark.xfail(
    strict=True,
    reason="Phase 3/4: nothing is linked or date-shifted yet, so output is "
    "secret-independent (check_submission.py warns about this)",
)
def test_different_secret_changes_output(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    a = run_cli(inp, tmp_path / "a", secret="one")
    b = run_cli(inp, tmp_path / "b", secret="two")
    assert _digest(a.out) != _digest(b.out)
