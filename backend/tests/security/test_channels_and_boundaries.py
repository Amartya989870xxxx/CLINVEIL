"""Side channels, input integrity and trust boundaries (SPEC §7, SANDBOX)."""

import hashlib
import json

import pytest

from conftest import SYNTH_NAME, run_cli

DISTINCT_SECRET = "zq-SECRET-canary-41d9e2"


def _all_bytes(root):
    return b"".join(p.read_bytes() + p.name.encode() for p in root.rglob("*") if p.is_file())


def _tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def test_secret_never_written(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    r = run_cli(inp, tmp_path / "out", secret=DISTINCT_SECRET)
    assert r.code == 0
    assert DISTINCT_SECRET.encode() not in _all_bytes(r.out)
    assert DISTINCT_SECRET not in r.stdout + r.stderr


def test_stdout_stderr_and_report_carry_no_pii(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    r = run_cli(inp, tmp_path / "out")
    assert SYNTH_NAME not in r.stdout + r.stderr
    report = (r.out / "report.json").read_text(encoding="utf-8")
    assert SYNTH_NAME not in report  # files are identified by hash; output paths mirror non-PII input paths
    assert "Harendra" not in (r.out / "records.jsonl").read_text(encoding="utf-8")


def test_input_is_never_modified(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    before = _tree_hash(inp)
    run_cli(inp, tmp_path / "out")
    assert _tree_hash(inp) == before


def test_missing_secret_fails_closed_and_writes_nothing(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    out = tmp_path / "out"
    r = run_cli(inp, out, secret=None)
    assert r.code == 2
    assert not out.exists() or not any(out.iterdir())


def test_overlapping_input_output_rejected(synthetic_input):
    inp, _ = synthetic_input
    before = _tree_hash(inp)
    r = run_cli(inp, inp / "out")
    assert r.code == 2
    assert _tree_hash(inp) == before


def test_symlink_escaping_input_is_never_read(synthetic_input, tmp_path):
    """Phase 2.1 (S1): the target is neither parsed nor hashed. The path is covered by an empty,
    content-free placeholder declared ``suppressed`` (see PHASE2_REMEDIATION.md, S1)."""
    inp, _ = synthetic_input
    secret_file = tmp_path / "outside_secret.txt"
    secret_file.write_text(f"Name: {SYNTH_NAME}\n", encoding="utf-8")
    (inp / "notes" / "linked.txt").symlink_to(secret_file)
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0
    rep = json.loads((r.out / "report.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(secret_file.read_bytes()).hexdigest() not in json.dumps(rep)
    entry = next(e for e in rep["files"] if e.get("reason") == "symlink_outside_input")
    assert entry["status"] == "suppressed" and entry["output"] == "sanitized/notes/linked.txt"
    assert (r.out / "sanitized" / "notes" / "linked.txt").read_bytes() == b""


def test_oversized_file_quarantined_without_reading(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    policy = tmp_path / "policy.yaml"
    policy.write_text("max_file_bytes: 64\n", encoding="utf-8")
    r = run_cli(inp, tmp_path / "out", extra_args=["--policy", str(policy)])
    assert r.code == 0
    rep = json.loads((r.out / "report.json").read_text(encoding="utf-8"))
    assert any(e.get("reason") == "file_too_large" for e in rep["files"])


def test_unexpected_exception_reason_has_no_content(synthetic_input, tmp_path, monkeypatch):
    """A processor crash whose message contains PII must quarantine with the type name only."""
    from clinveil import pipeline
    from clinveil.config.policy import Policy
    from clinveil.sanitization.processors import Sanitizer
    from clinveil.security.secrets import ReleaseSecret

    def boom(self, doc, out_rel, analysis):
        raise ValueError(SYNTH_NAME)

    monkeypatch.setattr(Sanitizer, "sanitize", boom)
    inp, _ = synthetic_input
    out = tmp_path / "out"
    summary = pipeline.run(inp, out, ReleaseSecret(b"k"), Policy())
    assert summary.ok
    report = (out / "report.json").read_text(encoding="utf-8")
    assert SYNTH_NAME not in report
    assert '"reason": "ValueError"' in report


@pytest.mark.parametrize("payload", [b"[" * 3000 + b"]" * 3000])
def test_pathologically_deep_json_does_not_crash(tmp_path, payload):
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "deep.json").write_bytes(payload)
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    rep = json.loads((r.out / "report.json").read_text(encoding="utf-8"))
    assert rep["counts"]["files_total"] == 1
    assert rep["files"][0]["status"] == "quarantined" and rep["files"][0]["reason"] == "json_too_deep"
