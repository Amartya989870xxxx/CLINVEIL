"""Shared fixtures.

All fixture data is SYNTHETIC and authored for these tests (invented names, numbers
from reserved/placeholder ranges). Tests that need the organiser's practice data
read it from the toolkit checkout (never copied into this repo) and are skipped
when it is absent.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
MAIN = REPO / "main.py"
TEST_SECRET = "clinveil-test-secret-7f3a9c"


def toolkit_dir() -> Path:
    return Path(os.environ.get("CLINVEIL_TOOLKIT", REPO / "organiser-toolkit"))


@pytest.fixture(scope="session")
def toolkit() -> Path:
    tk = toolkit_dir()
    if not (tk / "validate_output.py").is_file() or not (tk / "dev" / "input").is_dir():
        pytest.skip("organiser toolkit not available (set CLINVEIL_TOOLKIT or clone to ./organiser-toolkit)")
    return tk


@dataclass
class CliResult:
    code: int
    stdout: str
    stderr: str
    out: Path


def run_cli(
    inp: Path,
    out: Path,
    secret: str | None = TEST_SECRET,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> CliResult:
    env = {k: v for k, v in os.environ.items() if k != "RAKSHA_SECRET"}
    if secret is not None:
        env["RAKSHA_SECRET"] = secret
    env.update(extra_env or {})
    p = subprocess.run(
        [sys.executable, str(MAIN), "--input", str(inp), "--output", str(out), *(extra_args or [])],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return CliResult(p.returncode, p.stdout, p.stderr, out)


# ----------------------------------------------------------------------------- synthetic input tree
SYNTH_NAME = "Harendra Vexpal"  # invented; must never survive in any output channel
SYNTH_PHONE = "+91 98765 43210"
SYNTH_AADHAAR = "2345 6789 0123"


def _w(root: Path, rel: str, data: bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def build_synthetic_input(root: Path) -> dict[str, str]:
    """Create a small heterogeneous input tree. Returns rel -> expected status."""
    expected: dict[str, str] = {}

    csv_text = (
        "UHID,Patient Name,Age,Mobile,Diagnosis\n"
        f"TST/26/000101,{SYNTH_NAME},47,{SYNTH_PHONE},Dengue fever\n"
        "TST/26/000102,Kiran Moltey,62,9123456780,Type 2 diabetes mellitus\n"
    )
    _w(root, "registration/reg_bom.csv", b"\xef\xbb\xbf" + csv_text.encode("utf-8"))
    expected["registration/reg_bom.csv"] = "sanitized"

    tsv_text = "Reg No\tNaam\tUmar\nTST-0001\tवसुधा मेहरोत्रा\t38 वर्ष\n"
    _w(root, "registration/reg_utf16.tsv", tsv_text.encode("utf-16"))  # BOM + UTF-16
    expected["registration/reg_utf16.tsv"] = "sanitized"

    _w(root, "registration/legacy_cp1252.csv", "id,note\n1,Café visit — follow-up\n".encode("cp1252"))
    expected["registration/legacy_cp1252.csv"] = "sanitized"

    _w(
        root,
        "opd/visits.json",
        (
            b'{"_export_meta": {"system": "test"}, "visits": ['
            b'{"visit_id": "V1", "complaints": "C/O fever x 3 days", "rx": "Tab Dolo 650 1-0-1 x 5 days"},'
            b'{"visit_id": "V2", "complaints": "cough", "vitals": {"bp": "120/80", "pulse": 88}}]}'
        ),
    )
    expected["opd/visits.json"] = "sanitized"

    _w(root, "fhir/bundle.json", b'{"resourceType": "Bundle", "type": "document", "entry": []}')
    expected["fhir/bundle.json"] = "sanitized"

    _w(root, "notes/note.txt", f"Name: {SYNTH_NAME}\nBP 130/90. Dr. Anirudh Iyer reviewed.\n".encode())
    expected["notes/note.txt"] = "sanitized"

    _w(root, "misc/scan.pdf", b"%PDF-1.4\n% synthetic\n")
    expected["misc/scan.pdf"] = "quarantined"
    _w(root, "misc/photo.jpg", b"\xff\xd8\xff\xe0synthetic")
    expected["misc/photo.jpg"] = "quarantined"
    _w(root, "misc/empty.csv", b"")
    expected["misc/empty.csv"] = "quarantined"
    _w(root, "misc/truncated.json", b'{"visits": [{"patient": "x", "mob')
    expected["misc/truncated.json"] = "quarantined"
    _w(root, "misc/bad_bytes.txt", b"note \x81\x8d\x8f\x90\x9d end")  # invalid UTF-8 and undefined in cp1252
    expected["misc/bad_bytes.txt"] = "quarantined"

    # ---- Phase 1 ingestion traps
    _w(root, "misc/mislabeled.csv", f'{{"patient": "{SYNTH_NAME}", "aadhaar": "{SYNTH_AADHAAR}"}}'.encode())
    expected["misc/mislabeled.csv"] = "sanitized"  # JSON content, parsed as JSON
    _w(root, "misc/corrupt_note.txt", b"OPD note. \xff\xfe\xc3( Mobile pending. C/O cough.\n")
    expected["misc/corrupt_note.txt"] = "quarantined"  # implausible_text
    _w(root, "misc/deep.json", b'{"l":' * 100 + b'"x"' + b"}" * 100)
    expected["misc/deep.json"] = "quarantined"  # json_too_deep
    _w(root, "misc/cda.xml", b'<?xml version="1.0"?><ClinicalDocument><name>x</name></ClinicalDocument>')
    expected["misc/cda.xml"] = "quarantined"  # unsupported_xml
    payload = base64.b64encode(f"Consent witnessed, phone {SYNTH_PHONE}.".encode()).decode()
    _w(
        root,
        "forms/consent.json",
        f'{{"form": "consent", "attachment": {{"contentType": "text/plain", "data": "{payload}"}}}}'.encode(),
    )
    expected["forms/consent.json"] = "sanitized"  # payload decoded, cleaned, re-encoded
    _w(root, "notes/handover.log", f"Handover: callback {SYNTH_PHONE}\n".encode())
    expected["notes/handover.log"] = "sanitized"  # unknown extension, plain text content
    return expected


@pytest.fixture
def synthetic_input(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "input"
    expected = build_synthetic_input(root)
    return root, expected
