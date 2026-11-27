"""Unit tests for ``backend/scripts/demo_api.py`` (the optional local demo API for the frontend).

Synthetic, invented values only. Covers the pieces that keep the server safe and honest: content sniffing (same
rules as the frontend), the token-level before/after diff, the checker-output parser (numbers only), the
local-only request guard and the release zip contents.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo_api.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("demo_api", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["demo_api"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


api = _load()


def test_sniff_matches_frontend_rules() -> None:
    assert api.sniff(b"") == "empty"
    assert api.sniff(b"%PDF-1.7") == "pdf"
    assert api.sniff(b"\x89PNG\r\n") == "image"
    assert api.sniff(b"PK\x03\x04") == "archive"
    assert api.sniff(b"A\x00BC") == "binary"
    assert api.sniff(b'<?xml version="1.0"?>') == "xml"
    assert api.sniff(b'{"resourceType": "Bundle"}') == "fhir"
    assert api.sniff(b'[{"a": 1}]') == "json"
    assert api.sniff(b"uhid\tname\tage\n") == "tsv"
    assert api.sniff(b"uhid,name,age\n") == "csv"
    assert api.sniff(b"DISCHARGE SUMMARY\n") == "text"


def test_removed_spans_are_whole_tokens() -> None:
    before = "Patient Name: Asha Verma  Age: 41\nTab Dolo 650 BD"
    after = "Patient Name: [NAME]  Age: 41\nTab Dolo 650 BD"
    spans = api._removed_spans(before, after)
    assert [before[s["start"] : s["end"]] for s in spans] == ["Asha Verma"]
    assert all(s["kind"] == "removed" for s in spans)


def test_checker_parser_keeps_numbers_only() -> None:
    stdout = (
        "1) PERSONAL DATA: 2 of 100 pieces still visible\n"
        "Example leaks (type, language, place, file, text):\n    PATIENT_NAME | latin | content | x.txt | Asha Verma\n"
        "2) CANARIES: 0 of 4 planted canaries\n3) MEDICAL DATA KEPT: 99 of 100 medical values\n"
        "4) PATIENT LINKING: precision 0.00, recall 0.00, F0.5 0.00\n   you linked nothing yet\n"
        "5) RAW COPIES: 0 broken/unsupported files\n"
    )
    parsed = api._parse_practice(stdout)
    assert parsed["pii"] == [2, 100]
    assert parsed["canaries"] == [0, 4]
    assert parsed["medical"] == [99, 100]
    assert parsed["raw"] == [0]
    assert parsed["linked_nothing"] is True
    assert "Asha" not in json.dumps(parsed)


def _handler(host: str, origin: str | None = None) -> SimpleNamespace:
    headers = {"Host": host}
    if origin:
        headers["Origin"] = origin
    return SimpleNamespace(headers=headers)


def test_only_local_requests_are_accepted() -> None:
    local = api.Handler._local
    assert local(_handler("127.0.0.1:8765"))
    assert local(_handler("localhost:5173", "http://127.0.0.1:5173"))
    assert not local(_handler("evil.example"))  # DNS rebinding
    assert not local(_handler("127.0.0.1:8765", "https://evil.example"))  # cross-site request


def test_release_zip_contains_only_release_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    (out / "sanitized" / "notes").mkdir(parents=True)
    (out / "sanitized" / "notes" / "a.txt").write_text("[NAME] seen in OPD", encoding="utf-8")
    (out / "report.json").write_text("{}", encoding="utf-8")
    (out / "records.jsonl").write_text("", encoding="utf-8")
    (out / "logs").mkdir()
    (out / "logs" / "detection_summary.json").write_text("{}", encoding="utf-8")
    job = SimpleNamespace(out=out)
    names = set(zipfile.ZipFile(BytesIO(api.release_zip(job))).namelist())
    assert names == {"report.json", "records.jsonl", "sanitized/notes/a.txt"}


def test_secret_is_random_and_not_served() -> None:
    assert len(api.SECRET) == 64
    assert api.SECRET not in json.dumps(api.CAPABILITIES)
