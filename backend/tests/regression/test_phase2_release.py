"""Phase 2 release regression on the organiser practice data (replaces the Phase 1 delta test).

Pins: ingestion outcomes for every ``misc/`` trap file; structure preservation
(CSV rows/columns, JSON key paths and value types except renamed PII keys, FHIR
references and date syntax); filename renames declared by hash; and the official
``check_dev.py`` thresholds (run unmodified, parsed from its output). The answer key
is only read by the official checker, never by this test or the engine.
"""

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import TEST_SECRET, run_cli

pytestmark = pytest.mark.toolkit

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
FHIR_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?")


@pytest.fixture(scope="module")
def release(toolkit, tmp_path_factory):
    inp = toolkit / "dev" / "input"
    out = tmp_path_factory.mktemp("p2") / "out"
    r = run_cli(inp, out, secret=TEST_SECRET)
    assert r.code == 0, r.stderr
    import hashlib

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    by_sha = {e["input_sha256"]: e for e in report["files"]}
    entries = {
        p.relative_to(inp).as_posix(): by_sha[hashlib.sha256(p.read_bytes()).hexdigest()]
        for p in inp.rglob("*")
        if p.is_file()
    }
    return toolkit, inp, out, report, entries


def test_misc_outcomes(release):
    _, _, out, _, entries = release
    for rel, (status, reason) in MISC_OUTCOMES.items():
        assert entries[rel]["status"] == status and entries[rel].get("reason") == reason, rel


def test_csv_shape_preserved(release):
    _, inp, out, _, entries = release
    for rel, e in entries.items():
        if e["status"] != "sanitized" or not rel.endswith((".csv", ".tsv")) or rel == "misc/mislabeled_export.csv":
            continue
        delim = "\t" if rel.endswith(".tsv") else ","
        raw = (inp / rel).read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig", "replace")
        before = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
        after = list(
            csv.reader(io.StringIO((out / e["output"]).read_text(encoding="utf-8"), newline=""), delimiter=delim)
        )
        assert len(before) == len(after), rel
        assert [len(r) for r in before] == [len(r) for r in after], rel


def _shape(o, path=()):
    if isinstance(o, dict):
        return {(*path, "{}")} | {x for k, v in o.items() for x in _shape(v, (*path, k))}
    if isinstance(o, list):
        return {(*path, "[]")} | {x for v in o for x in _shape(v, (*path, "*"))}
    return {(*path, type(o).__name__)}


def test_json_structure_and_types_preserved_except_renamed_pii_keys(release):
    _, inp, out, _, entries = release
    for rel, e in entries.items():
        if e["status"] != "sanitized" or not rel.endswith(".json"):
            continue
        before = json.loads((inp / rel).read_bytes().decode("utf-8-sig"))
        after = json.loads((out / e["output"]).read_text(encoding="utf-8"))
        a, b = _shape(before), _shape(after)
        if a != b:  # only dynamic PII keys may differ (patient_index-style maps)
            assert rel == "misc/patient_index.json", rel
            assert {p[:1] for p in a} == {p[:1] for p in b}


def test_fhir_bundles_stay_valid(release):
    _, inp, out, _, entries = release
    from clinveil.parsing.fhir import build_index

    for rel, e in entries.items():
        if not rel.startswith("fhir/"):
            continue
        before = json.loads((inp / rel).read_text(encoding="utf-8"))
        after = json.loads((out / e["output"]).read_text(encoding="utf-8"))
        assert [r.target_entry for r in build_index(after).references] == [
            r.target_entry for r in build_index(before).references
        ]
        assert not build_index(after).unresolved
        for entry in after["entry"]:
            res = entry["resource"]
            if res["resourceType"] == "Patient" and "birthDate" in res:
                assert FHIR_DATE.fullmatch(res["birthDate"]), "birthDate must stay a valid FHIR date"


def test_renamed_files_are_declared_and_exist(release):
    _, _, out, report, entries = release
    renamed = [e for rel, e in entries.items() if e["output"] and e["output"] != f"sanitized/{rel}"]
    assert renamed, "practice filenames contain names, phones and MRNs"
    assert all((out / e["output"]).is_file() for e in renamed)
    assert len({e["output"] for e in report["files"] if e["output"]}) == sum(1 for e in report["files"] if e["output"])


def test_official_checker_thresholds(release):
    toolkit, _, out, report, _ = release
    res = subprocess.run(
        [sys.executable, str(toolkit / "check_dev.py"), "--output", str(out)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    leaked, total = map(int, re.search(r"PERSONAL DATA: (\d+) of (\d+)", res).groups())
    canaries = int(re.search(r"CANARIES: (\d+) of", res).group(1))
    kept, probes = map(int, re.search(r"MEDICAL DATA KEPT: (\d+) of (\d+)", res).groups())
    raw_copies = int(re.search(r"RAW COPIES: (\d+)", res).group(1))
    assert leaked / total <= 0.01, f"leak {leaked}/{total}"
    assert canaries == 0
    assert kept / probes >= 0.99
    assert raw_copies == 0
    assert sum(report["entities"].values()) == report["counts"]["identifiers_detected"]


def test_official_validator(release):
    toolkit, inp, out, _, _ = release
    v = subprocess.run(
        [sys.executable, str(toolkit / "validate_output.py"), "--input", str(inp), "--output", str(out)],
        capture_output=True,
        text=True,
    )
    assert "CONTRACT OK" in v.stdout, v.stdout


def test_dev_eval_script_runs(release):
    toolkit, _, out, _, _ = release
    script = Path(__file__).resolve().parents[2] / "scripts" / "dev_eval.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--output", str(out), "--truth", str(toolkit / "dev/truth/truth.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"dev_eval.py failed (exit {proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "OFFICIAL-STYLE LEAK" in proc.stdout and "PRESERVE PROBES" in proc.stdout
