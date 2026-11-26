"""Phase 1 regression: the only differences from the official starter are the
intended ingestion changes, and each is the exact expected transformation.

Replaces the Phase 0 byte-parity test. On the organiser practice data:

1. every exported file is byte-identical to the starter's output, EXCEPT
   a. files now quarantined by content checks (corrupt text, over-deep JSON),
   b. JSON content behind a ``.csv`` extension, now parsed and rendered as JSON,
   c. JSON files whose only changed values are base64 payloads, where each new
      payload decodes to exactly the baseline-cleaned original payload text;
2. every ``misc/`` trap file has its expected outcome and reason code;
3. ``records.jsonl`` changes only for the files in 1a/1b.

File names below are practice-kit file names (not patient data).
"""

import base64
import json
import os
import subprocess
import sys

import pytest

from clinveil.detection.baseline_regex import redact
from conftest import TEST_SECRET, run_cli

pytestmark = pytest.mark.toolkit

NOW_QUARANTINED = {"misc/corrupt_bytes_note.txt": "implausible_text", "misc/deep_export.json": "json_too_deep"}
NOW_JSON = {"misc/mislabeled_export.csv"}
MISC_OUTCOMES = {
    "misc/README_export.txt": ("sanitized", None),
    "misc/ambulance_log.csv": ("sanitized", None),
    "misc/corrupt_bytes_note.txt": ("quarantined", "implausible_text"),
    "misc/deep_export.json": ("quarantined", "json_too_deep"),
    "misc/empty_export.csv": ("quarantined", "empty_file"),
    "misc/helpdesk_tickets.json": ("sanitized", None),
    "misc/hl7_cda_discharge.xml": ("quarantined", "unsupported_xml"),
    "misc/mislabeled_export.csv": ("sanitized", None),
    "misc/patient_index.json": ("sanitized", None),
    "misc/photo_rx.jpg": ("quarantined", "unsupported_image"),
    "misc/scanned_consent_form.json": ("sanitized", None),
    "misc/scanned_discharge.pdf": ("quarantined", "unsupported_pdf"),
    "misc/truncated_opd.json": ("quarantined", "invalid_json"),
    "misc/ward_vitals_sheet.csv": ("sanitized", None),
}


@pytest.fixture(scope="module")
def runs(toolkit, tmp_path_factory):
    inp = toolkit / "dev" / "input"
    base = tmp_path_factory.mktemp("p1delta")
    starter, ours = base / "starter", base / "ours"
    subprocess.run(
        [sys.executable, str(toolkit / "starter" / "main.py"), "--input", str(inp), "--output", str(starter)],
        env=dict(os.environ, RAKSHA_SECRET=TEST_SECRET),
        check=True,
        capture_output=True,
    )
    r = run_cli(inp, ours)
    assert r.code == 0, r.stderr
    return inp, starter, ours


def _leaves(o, p=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _leaves(v, (*p, k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _leaves(v, (*p, i))
    else:
        yield p, o


def _status_by_rel(inp, out):
    import hashlib

    by_sha = {e["input_sha256"]: e for e in json.loads((out / "report.json").read_text(encoding="utf-8"))["files"]}
    return {
        p.relative_to(inp).as_posix(): by_sha[hashlib.sha256(p.read_bytes()).hexdigest()]
        for p in inp.rglob("*")
        if p.is_file()
    }


def test_misc_trap_files_have_expected_outcomes(runs):
    inp, _, ours = runs
    status = _status_by_rel(inp, ours)
    for rel, (st, reason) in MISC_OUTCOMES.items():
        assert status[rel]["status"] == st, rel
        assert status[rel].get("reason") == reason, rel
        exported = ours / "sanitized" / rel
        assert exported.exists() == (st == "sanitized"), rel
    # A malformed-category file we choose to export must never be a byte-for-byte copy (raw-copy penalty).
    for rel in NOW_JSON:
        assert (ours / "sanitized" / rel).read_bytes() != (inp / rel).read_bytes(), rel


def test_only_intended_differences_from_starter(runs):
    inp, starter, ours = runs
    payload_files = 0
    for s_file in sorted((starter / "sanitized").rglob("*")):
        if not s_file.is_file():
            continue
        rel = s_file.relative_to(starter / "sanitized").as_posix()
        o_file = ours / "sanitized" / rel
        if rel in NOW_QUARANTINED:
            assert not o_file.exists(), rel
            continue
        if o_file.read_bytes() == s_file.read_bytes():
            continue
        if rel in NOW_JSON:
            data = json.loads(o_file.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            continue
        # Otherwise: a JSON file whose only differences are re-encoded base64 payloads.
        s_leaves = dict(_leaves(json.loads(s_file.read_text(encoding="utf-8"))))
        o_leaves = dict(_leaves(json.loads(o_file.read_text(encoding="utf-8"))))
        orig = dict(_leaves(json.loads((inp / rel).read_text(encoding="utf-8-sig"))))
        assert s_leaves.keys() == o_leaves.keys(), f"{rel}: structure changed"
        changed = [k for k in s_leaves if s_leaves[k] != o_leaves[k]]
        assert changed, rel
        for k in changed:
            assert k[-1] == "data", f"{rel}: non-payload value changed"
            expected = redact(base64.b64decode(orig[k]).decode("utf-8"))[0]
            assert base64.b64decode(o_leaves[k]).decode("utf-8") == expected, f"{rel}: payload not cleaned exactly"
        payload_files += 1
    assert payload_files >= 1  # the practice data contains base64 attachments


def test_records_change_only_for_reclassified_files(runs):
    _, starter, ours = runs

    def lines(out):
        return set((out / "records.jsonl").read_text(encoding="utf-8").splitlines())

    touched = {f"sanitized/{r}" for r in (*NOW_QUARANTINED, *NOW_JSON)}
    a = {line for line in lines(starter) if json.loads(line)["file"] not in touched}
    b = {line for line in lines(ours) if json.loads(line)["file"] not in touched}
    assert a == b
    ours_touched = [json.loads(line) for line in lines(ours) if json.loads(line)["file"] in touched]
    assert ours_touched == [{"file": "sanitized/misc/mislabeled_export.csv", "loc": "doc", "patient": None}]


def test_no_quarantined_or_unsupported_file_is_released(runs):
    inp, _, ours = runs
    status = _status_by_rel(inp, ours)
    for rel, entry in status.items():
        if entry["status"] == "quarantined":
            assert entry["output"] is None and not (ours / "sanitized" / rel).exists()
    for p in (ours / "sanitized").rglob("*"):
        if p.is_file():
            raw = p.read_bytes()
            assert not raw.startswith((b"%PDF", b"\xff\xd8\xff", b"<?xml")), p.name
            raw.decode("utf-8")
