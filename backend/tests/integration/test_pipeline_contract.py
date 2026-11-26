"""End-to-end contract tests on a synthetic heterogeneous input tree."""

import hashlib
import json
import subprocess
import sys

import pytest

from conftest import run_cli


def _report(out):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_every_input_is_reported_with_expected_status(synthetic_input, tmp_path):
    inp, expected = synthetic_input
    r = run_cli(inp, tmp_path / "out")
    assert r.code == 0, r.stderr
    rep = _report(r.out)
    by_sha = {e["input_sha256"]: e for e in rep["files"]}
    for rel, status in expected.items():
        sha = hashlib.sha256((inp / rel).read_bytes()).hexdigest()
        assert by_sha[sha]["status"] == status, rel
        if status == "sanitized":
            assert (r.out / by_sha[sha]["output"]).is_file()
        else:
            assert by_sha[sha]["output"] is None and by_sha[sha]["reason"]
            assert not (r.out / "sanitized" / rel).exists()  # never copied raw
    c = rep["counts"]
    assert c["files_total"] == len(expected)
    assert c["files_sanitized"] + c["files_quarantined"] == c["files_total"]
    assert isinstance(rep["timing"]["seconds"], float | int)
    assert isinstance(rep["resources"]["peak_rss_mb"], float | int)


def test_quarantine_reasons_are_codes(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    rep = _report(run_cli(inp, tmp_path / "out").out)
    reasons = {e["reason"] for e in rep["files"] if e["status"] == "quarantined"}
    assert reasons == {"unsupported_format", "empty_file", "JSONDecodeError", "undecodable_text"}


def test_outputs_are_utf8_and_formats_preserved(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    out = run_cli(inp, tmp_path / "out").out / "sanitized"
    for p in out.rglob("*"):
        if p.is_file():
            p.read_bytes().decode("utf-8")
    tsv = (out / "registration/reg_utf16.tsv").read_text(encoding="utf-8")
    assert tsv.splitlines()[0] == "Reg No\tNaam\tUmar"
    data = json.loads((out / "opd/visits.json").read_text(encoding="utf-8"))
    assert data["visits"][1]["vitals"]["pulse"] == 88  # value types kept


def test_records_jsonl_locators(synthetic_input, tmp_path):
    inp, _ = synthetic_input
    out = run_cli(inp, tmp_path / "out").out
    recs = [json.loads(line) for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    locs = {(r["file"], r["loc"]) for r in recs}
    assert ("sanitized/registration/reg_bom.csv", "row:0") in locs
    assert ("sanitized/registration/reg_bom.csv", "row:1") in locs
    assert ("sanitized/opd/visits.json", "/visits/1") in locs
    assert ("sanitized/fhir/bundle.json", "doc") in locs
    assert ("sanitized/notes/note.txt", "doc") in locs
    assert all(r["file"] != "sanitized/misc/truncated.json" for r in recs)
    assert all(set(r) >= {"file", "loc", "patient"} for r in recs)


@pytest.mark.toolkit
def test_official_validator_accepts_synthetic_release(toolkit, synthetic_input, tmp_path):
    inp, _ = synthetic_input
    out = run_cli(inp, tmp_path / "out").out
    v = subprocess.run(
        [sys.executable, str(toolkit / "validate_output.py"), "--input", str(inp), "--output", str(out)],
        capture_output=True,
        text=True,
    )
    assert "CONTRACT OK" in v.stdout, v.stdout


@pytest.mark.toolkit
def test_official_validator_accepts_practice_release(toolkit, tmp_path):
    out = run_cli(toolkit / "dev" / "input", tmp_path / "out")
    assert out.code == 0, out.stderr
    v = subprocess.run(
        [
            sys.executable,
            str(toolkit / "validate_output.py"),
            "--input",
            str(toolkit / "dev" / "input"),
            "--output",
            str(out.out),
        ],
        capture_output=True,
        text=True,
    )
    assert "CONTRACT OK" in v.stdout, v.stdout
