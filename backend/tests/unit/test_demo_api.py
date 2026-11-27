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


# ----------------------------------------------------------------------------------------- uploads (integration)
import base64  # noqa: E402
import http.client  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@pytest.mark.parametrize(
    "name", ["../escape.csv", "a/b.csv", "..\\b.csv", ".hidden.csv", "", "x" * 200 + ".csv", "bad\x00.csv", 7]
)
def test_upload_names_that_are_paths_or_unsafe_are_rejected(name) -> None:
    with pytest.raises(api.UploadRejected) as e:
        api._upload_name(name)
    assert e.value.code == "invalid_upload"


@pytest.mark.parametrize("name", ["scan.pdf", "photo.png", "bundle.zip", "notes.docx", "noext"])
def test_upload_unsupported_extensions_are_rejected(name) -> None:
    with pytest.raises(api.UploadRejected) as e:
        api._upload_name(name)
    assert e.value.code == "unsupported_file"


def test_upload_rejects_duplicates_bad_base64_and_oversize(monkeypatch) -> None:
    with pytest.raises(api.UploadRejected):
        api.create_upload(
            [{"name": "a.csv", "content_base64": _b64("x")}, {"name": "A.csv", "content_base64": _b64("y")}]
        )
    with pytest.raises(api.UploadRejected):
        api.create_upload([{"name": "a.csv", "content_base64": "%%%not-base64"}])
    with pytest.raises(api.UploadRejected):
        api.create_upload([])
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(api.UploadRejected) as e:
        api.create_upload([{"name": "a.csv", "content_base64": _b64("0123456789")}])
    assert e.value.code == "upload_too_large"


def _request(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, bytes, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Host": f"127.0.0.1:{port}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    res = conn.getresponse()
    return res.status, res.read(), dict(res.getheaders())


def test_upload_runs_the_real_engine_end_to_end() -> None:
    """A synthetic upload goes through the real CLI engine; the served release is the engine's own output."""
    srv = api.ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    api.Handler.datasets = {}
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        csv_text = (
            "Patient Name,Phone,Age,Admission Date,Discharge Date,Diagnosis\n"
            "Corvina Ashdale,9876501234,47,13/01/2026,18/01/2026,Type 2 diabetes mellitus\n"
        )
        status, body, _ = _request(
            port,
            "POST",
            "/api/v1/jobs",
            {"upload": {"files": [{"name": "ward_register.csv", "content_base64": _b64(csv_text)}]}},
        )
        assert status == 202, body
        jid = json.loads(body)["job_id"]
        state = "queued"
        for _ in range(240):
            status, body, _ = _request(port, "GET", f"/api/v1/jobs/{jid}")
            state = json.loads(body)["state"]
            if state not in ("queued", "running"):
                break
            time.sleep(0.25)
        assert state == "complete", state
        status, body, _ = _request(port, "GET", f"/api/v1/jobs/{jid}/summary")
        assert status == 200
        status, zbody, headers = _request(port, "GET", f"/api/v1/jobs/{jid}/download")
        assert status == 200 and headers["Content-Type"] == "application/zip"
        z = zipfile.ZipFile(BytesIO(zbody))
        sanitized = [n for n in z.namelist() if n.startswith("sanitized/")]
        assert len(sanitized) == 1
        out = z.read(sanitized[0]).decode("utf-8")
        assert "Corvina" not in out and "9876501234" not in out and "13/01/2026" not in out
        assert "Type 2 diabetes mellitus" in out and "45-49" in out
        status, rbody, _ = _request(port, "GET", f"/api/v1/jobs/{jid}/report.json")
        assert status == 200 and json.loads(rbody)["counts"]["files_sanitized"] == 1
        status, _, _ = _request(port, "GET", f"/api/v1/jobs/{jid}/records.jsonl")
        assert status == 200
        # a rejected upload: fixed error, no echo of the name
        status, body, _ = _request(
            port, "POST", "/api/v1/jobs", {"upload": {"files": [{"name": "../x.csv", "content_base64": _b64("a")}]}}
        )
        assert status == 400 and b"x.csv" not in body
        # another job's id cannot be guessed into a path
        status, _, _ = _request(port, "GET", "/api/v1/jobs/..%2F..%2Fetc/download")
        assert status == 404
    finally:
        srv.shutdown()
