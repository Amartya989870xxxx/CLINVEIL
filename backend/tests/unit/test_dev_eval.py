"""Isolated unit and CLI tests for ``backend/scripts/dev_eval.py``.

Uses only synthetic, invented identities and numbers (no practice data). Covers the
Python 3.10 deep-JSON ``RecursionError`` regression, optional ``--input``, error
handling for missing/malformed truth files, report-to-input SHA-256 mapping, PII
leakage metrics and clinical preservation probes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_eval.py"


def _run_eval(out: Path, truth: Path, inp: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), "--output", str(out), "--truth", str(truth)]
    if inp is not None:
        cmd.extend(["--input", str(inp)])
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _synthetic_fixture(tmp_path: Path, *, leak_name: bool = False) -> tuple[Path, Path, Path]:
    """Create a minimal synthetic input/truth/output fixture (with a 1,500-deep JSON trap)."""
    inp = tmp_path / "dev" / "input"
    truth_dir = tmp_path / "dev" / "truth"
    out = tmp_path / "out"
    (inp / "notes").mkdir(parents=True)
    (inp / "misc").mkdir(parents=True)
    truth_dir.mkdir(parents=True)
    (out / "sanitized" / "notes").mkdir(parents=True)

    raw_note = b"Patient: Orvila Tamsen\nMob: 9876543210\nRx: Tab Dolo 650 1-0-1 x 5 days\nBP 120/80\n"
    (inp / "notes" / "Orvila_note.txt").write_bytes(raw_note)

    deep_json = (b'{"a":' * 1500) + b"1" + (b"}" * 1500)
    (inp / "misc" / "deep.json").write_bytes(deep_json)

    san_note = (
        b"Patient: Orvila Tamsen\nMob: [PHONE]\nRx: Tab Dolo 650 1-0-1 x 5 days\nBP 120/80\n"
        if leak_name
        else b"Patient: [NAME]\nMob: [PHONE]\nRx: Tab Dolo 650 1-0-1 x 5 days\nBP 120/80\n"
    )
    (out / "sanitized" / "notes" / "NAME_note.txt").write_bytes(san_note)

    report = {
        "schema": "raksha-report/1",
        "files": [
            {"input_sha256": _sha(raw_note), "output": "sanitized/notes/NAME_note.txt", "status": "sanitized"},
            {"input_sha256": _sha(deep_json), "output": None, "status": "quarantined", "reason": "json_too_deep"},
        ],
    }
    (out / "report.json").write_text(json.dumps(report), encoding="utf-8")

    truth = {
        "files": {
            "notes/Orvila_note.txt": {
                "sha256": _sha(raw_note),
                "format": "text",
                "encoding": "utf-8",
                "units": {
                    "doc": {
                        "entities": [
                            {
                                "type": "PATIENT_NAME",
                                "surface": "Orvila Tamsen",
                                "match": "name",
                                "script": "latin",
                                "channel": "content",
                            },
                            {
                                "type": "PHONE",
                                "surface": "9876543210",
                                "key": "9876543210",
                                "match": "digits",
                                "script": "latin",
                                "channel": "content",
                            },
                        ],
                        "preserve": [
                            {"text": "Tab Dolo 650 1-0-1 x 5 days", "weight": 1.0},
                            {"text": "BP 120/80", "weight": 1.0},
                        ],
                    },
                    "@filename": {
                        "entities": [
                            {
                                "type": "PATIENT_NAME",
                                "surface": "Orvila",
                                "match": "name",
                                "script": "latin",
                                "channel": "filename",
                            }
                        ],
                        "preserve": [],
                    },
                },
            },
            "misc/deep.json": {
                "sha256": _sha(deep_json),
                "format": "json",
                "encoding": "utf-8",
                "units": {},
            },
        }
    }
    truth_path = truth_dir / "truth.json"
    truth_path.write_text(json.dumps(truth), encoding="utf-8")
    return inp, truth_path, out


def test_dev_eval_handles_deep_json_and_clean_synthetic_release(tmp_path):
    """Reproduces the Python 3.10 RecursionError on 1,500-deep JSON and verifies clean metrics."""
    _, truth_path, out = _synthetic_fixture(tmp_path, leak_name=False)
    proc = _run_eval(out, truth_path)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "OFFICIAL-STYLE LEAK (fractional, record-level): 0.0/3 = 0.00%" in proc.stdout
    assert "PRESERVE PROBES (weighted, field-level): 100.0%" in proc.stdout


def test_dev_eval_detects_leaked_patient_name_and_supports_explicit_input(tmp_path):
    inp, truth_path, out = _synthetic_fixture(tmp_path, leak_name=True)
    # Move truth.json outside dev/truth so inferred sibling input/ does not exist: --input must resolve it.
    moved_truth = tmp_path / "custom_truth.json"
    moved_truth.write_text(truth_path.read_text(encoding="utf-8"), encoding="utf-8")
    proc = _run_eval(out, moved_truth, inp=inp)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "OFFICIAL-STYLE LEAK (fractional, record-level): 1.0/3 = 33.33%" in proc.stdout
    assert "PATIENT_NAME" in proc.stdout


def test_dev_eval_missing_truth_file_exits_cleanly(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text('{"files": []}', encoding="utf-8")
    proc = _run_eval(out, tmp_path / "missing_truth.json")
    assert proc.returncode != 0
    assert "truth file not found" in proc.stderr and "Traceback" not in proc.stderr


def test_dev_eval_malformed_truth_json_exits_cleanly(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text('{"files": []}', encoding="utf-8")
    bad = tmp_path / "bad_truth.json"
    bad.write_text("{not valid json", encoding="utf-8")
    proc = _run_eval(out, bad)
    assert proc.returncode != 0
    assert "invalid truth file" in proc.stderr and "Traceback" not in proc.stderr
