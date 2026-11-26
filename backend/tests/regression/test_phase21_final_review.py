"""Phase 2.1 final review (four findings, F1-F4): reproduction and regression tests.

Written and run against ``e6021fa`` before any fix (all F-tests failed there, see
PHASE2_REMEDIATION.md §8). All identities are invented.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from conftest import TEST_SECRET, sanitize_documents, sanitize_text

PAT = "Orvila Tamsen"
PHONE = "9876543210"


# =========================================================================== F1: never an empty input_sha256
def _run(inp: Path, out: Path, max_bytes: int | None = None) -> dict:
    from clinveil.config.policy import Policy
    from clinveil.pipeline import run
    from clinveil.security.secrets import ReleaseSecret

    policy = Policy() if max_bytes is None else Policy(max_file_bytes=max_bytes)
    run(inp, out, ReleaseSecret(TEST_SECRET.encode()), policy)
    return json.loads((out / "report.json").read_text())


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_F1_every_discovered_entry_has_an_identifier(tmp_path):
    inp, ext = tmp_path / "in", tmp_path / "ext"
    inp.mkdir()
    ext.mkdir()
    (inp / "ok.txt").write_text("BP 120/80")
    (inp / "real.txt").write_text("Name: Kelvar Dunmore")
    (inp / "big.txt").write_text("x" * 5000)
    os.mkfifo(inp / "fifo_inside")
    (inp / "link_internal_fifo.txt").symlink_to("fifo_inside")
    os.mkfifo(ext / "pipe")
    (inp / "link_external_fifo.txt").symlink_to(ext / "pipe")
    (inp / "dangling.txt").symlink_to(ext / "missing.txt")
    (inp / "link_internal.txt").symlink_to("real.txt")
    rep = _run(inp, tmp_path / "out", max_bytes=1024)
    assert len(rep["files"]) == 8 == rep["counts"]["files_total"]
    for e in rep["files"]:
        assert len(e["input_sha256"]) == 64 and int(e["input_sha256"], 16) >= 0, e
    reasons = sorted(e.get("reason") or e["status"] for e in rep["files"])
    assert reasons == sorted(
        [
            "sanitized",
            "sanitized",
            "sanitized",
            "file_too_large",
            "not_a_regular_file",
            "not_a_regular_file",
            "symlink_outside_input",
            "broken_symlink",
        ]
    )
    # the internal link to a real file is still read and exported normally
    real_sha = hashlib.sha256(b"Name: Kelvar Dunmore").hexdigest()
    assert sum(e["input_sha256"] == real_sha and e["status"] == "sanitized" for e in rep["files"]) == 2


def test_F1_file_vanishing_between_discovery_and_read_gets_an_identifier(tmp_path, monkeypatch):
    from clinveil import pipeline

    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "a.txt").write_text("BP 120/80")
    (inp / "gone.txt").write_text(f"Name: {PAT}")
    real_read = pipeline.read_input
    calls = {"gone.txt": 0}

    def flaky(path, root, max_bytes):
        if path.name == "gone.txt":
            calls["gone.txt"] += 1
            if calls["gone.txt"] == 2:  # pass 2: discovered, then gone before the read
                path.unlink()
        return real_read(path, root, max_bytes)

    monkeypatch.setattr(pipeline, "read_input", flaky)
    rep = _run(inp, tmp_path / "out")
    assert all(len(e["input_sha256"]) == 64 for e in rep["files"])
    assert sorted(e["status"] for e in rep["files"]) == ["quarantined", "sanitized"]
    assert PAT not in json.dumps(rep)


def test_F1_file_changing_during_read_never_yields_an_empty_identifier(tmp_path, monkeypatch):
    from clinveil import pipeline

    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "a.txt").write_text("BP 120/80")

    def boom(path, root, max_bytes):
        raise OSError("changed while reading")

    monkeypatch.setattr(pipeline, "read_input", boom)
    rep = _run(inp, tmp_path / "out")
    assert [len(e["input_sha256"]) for e in rep["files"]] == [64]
    assert rep["files"][0]["status"] == "quarantined"


# =========================================================================== F2: attachment metadata and short binaries
TXT = base64.b64encode(f"Name: {PAT}, Mob {PHONE}".encode()).decode()
JPG = base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(40)).decode()


def _sanitize_json(obj) -> dict:
    return json.loads(sanitize_documents({"x/a.json": json.dumps(obj).encode()})["x/a.json"])


def test_F2_rewritten_text_attachment_drops_original_hash_and_size():
    out = _sanitize_json({"att": {"contentType": "text/plain", "data": TXT, "hash": "ORIGHASH=", "size": 35}})
    att = out["att"]
    assert att["contentType"] == "text/plain" and "hash" not in att and "size" not in att
    decoded = base64.b64decode(att["data"]).decode()
    assert PAT not in decoded and PHONE not in decoded


def test_F2_unchanged_text_attachment_keeps_its_metadata():
    clean = base64.b64encode(b"Haemoglobin 9.4 g/dL, review in 2 weeks").decode()
    att = {"contentType": "text/plain", "data": clean, "hash": "H=", "size": 39}
    assert _sanitize_json({"att": att}) == {"att": att}


@pytest.mark.parametrize("ctype", ["image/jpeg", None])
def test_F2_withheld_binary_drops_hash_and_size_with_or_without_content_type(ctype):
    att = {"data": JPG, "hash": "ORIGHASH=", "size": 50, "title": "scan"}
    if ctype:
        att["contentType"] = ctype
    out = _sanitize_json({"att": att})["att"]
    expected = {"title": "scan", **({"contentType": ctype} if ctype else {})}
    assert out == expected


@pytest.mark.parametrize(
    "ctype, payload",
    [
        ("application/octet-stream", base64.b64encode(bytes(range(6))).decode()),  # 8 chars, no signature
        ("image/png", "iVBORw0K"),  # 8 chars: start of a PNG signature
        ("application/pdf", base64.b64encode(b"%PDF-").decode()),
        ("image/jpeg", base64.b64encode(b"\xff\xd8\xff").decode()),
    ],
)
def test_F2_short_declared_binary_payload_is_withheld(ctype, payload):
    out = _sanitize_json({"att": {"contentType": ctype, "data": payload, "hash": "H=", "size": 6}})
    assert out == {"att": {"contentType": ctype}}


def test_F2_short_strings_without_binary_declaration_are_left_alone():
    # "pending" under a text type, and short strings under no attachment at all, are ordinary strings
    obj = {"att": {"contentType": "text/plain", "data": "pending"}, "code": "AAECAwQF", "status": "final"}
    assert _sanitize_json(obj) == obj


def test_F2_empty_and_invalid_payloads():
    from clinveil.security.errors import QuarantineError

    empty = {"att": {"contentType": "image/png", "data": ""}}
    assert _sanitize_json(empty) == empty
    with pytest.raises(QuarantineError) as exc:  # long, impossible base64 under a declaration: unsafe -> quarantine
        _sanitize_json({"att": {"contentType": "image/png", "data": "A" * 33}})
    assert exc.value.code == "invalid_attachment"


def test_F2_multiple_attachments_in_one_fhir_resource_and_bundle():
    from clinveil.parsing.fhir import build_index

    bundle = {
        "resourceType": "Bundle",
        "id": "b",
        "type": "collection",
        "entry": [
            {"fullUrl": "urn:uuid:p", "resource": {"resourceType": "Patient", "id": "p", "name": [{"text": PAT}]}},
            {
                "fullUrl": "urn:uuid:d",
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "d",
                    "status": "current",
                    "subject": {"reference": "urn:uuid:p"},
                    "content": [
                        {"attachment": {"contentType": "image/jpeg", "data": JPG, "hash": "A=", "size": 50}},
                        {"attachment": {"contentType": "text/plain", "data": TXT, "hash": "B=", "size": 35}},
                        {"attachment": {"contentType": "application/octet-stream", "data": "AAECAwQF", "size": 6}},
                    ],
                },
            },
        ],
    }
    out = json.loads(sanitize_documents({"fhir/b.json": json.dumps(bundle).encode()})["fhir/b.json"])
    content = out["entry"][1]["resource"]["content"]
    assert len(content) == 3
    assert content[0]["attachment"] == {"contentType": "image/jpeg"}
    assert set(content[1]["attachment"]) == {"contentType", "data"}
    assert PAT not in base64.b64decode(content[1]["attachment"]["data"]).decode()
    assert content[2]["attachment"] == {"contentType": "application/octet-stream"}
    assert not build_index(out).unresolved


def test_F2_json_arrays_of_attachment_values_keep_positions():
    out = _sanitize_json({"scans": [JPG, "keep", TXT], "n": 3})
    assert out["scans"][0] == "[ATTACHMENT-WITHHELD]" and out["scans"][1] == "keep" and len(out["scans"]) == 3
    assert PAT not in base64.b64decode(out["scans"][2]).decode()


# ================================================================== F3: percent-encoding and \uXXXX in spaced text
REG = {"reg/r.csv": f"MRN,Patient Name,Mobile\nTST/26/000901,{PAT},{PHONE}\n".encode()}


def _note(text: str) -> str:
    return sanitize_documents({**REG, "n/a.txt": text.encode()})["n/a.txt"]


@pytest.mark.parametrize(
    "text, gone",
    [
        ("Exported from /exports/Orvila%20Tamsen/report.json", ["Orvila", "Tamsen"]),  # the reproduced leak
        ("see file:///exp/Orvila%20Tamsen.pdf now", ["Orvila", "Tamsen"]),
        ("Path: C:\\exports\\Orvila%20Tamsen\\a.txt here", ["Orvila", "Tamsen"]),
        ("ref /x/TST%2F26%2F000901/a.json and more", ["000901"]),  # encoded slashes
        ("call /cb?ph=%39%38%37%36%35%34%33%32%31%30 today", ["9876543210"]),  # encoded digits
        ("Uploaded by Orvila%20Tamsen today", ["Orvila", "Tamsen"]),  # encoded space between words
    ],
)
def test_F3_percent_encoded_values_in_spaced_text(text, gone):
    import urllib.parse

    out = _note(text)
    plain = urllib.parse.unquote(out)
    for piece in gone:
        assert piece not in plain, (piece, out)


@pytest.mark.parametrize(
    "text",
    [
        "SpO2 98% on room air, 50% dextrose, 100%ABx",  # unrelated percent signs (no decoding)
        "Discount 20%off, invalid %ZZ and %4 sequences",  # invalid escapes untouched
        "Exported from /exports/clean%20folder/report.json",  # decoded, nothing personal: unchanged
    ],
)
def test_F3_unrelated_percent_text_is_unchanged(text):
    assert _note(text) == text


def test_F3_exact_original_span_is_replaced():
    out = _note("Exported from /exports/Orvila%20Tamsen/report.json")
    assert out == "Exported from /exports/[NAME]/report.json"


def test_F3_url_and_metadata_fields():
    meta = {"_meta": {"source": "https://h.example/exp/Orvila%20Tamsen/r.json?x=1 (nightly)"}, "rows": [{"a": 1}]}
    out = sanitize_documents({**REG, "x/m.json": json.dumps(meta).encode()})["x/m.json"]
    src = json.loads(out)["_meta"]["source"]
    assert "Orvila" not in src and "Tamsen" not in src and src.startswith("https://h.example/exp/")


def test_F3_unicode_escapes_in_plain_text():
    out = _note("ref \\u004frvila Tamsen, mob \\u0039876543210 end")
    assert "rvila" not in out and "876543210" not in out and out.startswith("ref ") and out.endswith(" end")
    assert (
        sanitize_text("path C:\\users\\docs and \\u00e9t\\u00e9 notes")
        == "path C:\\users\\docs and \\u00e9t\\u00e9 notes"
    )


# =========================================================================== F4: zero-valued numbers
def _report_for(tmp_path: Path, obj) -> tuple[dict, dict]:
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "z.json").write_text(json.dumps(obj))
    rep = _run(inp, tmp_path / "out")
    return rep, json.loads((tmp_path / "out/sanitized/z.json").read_text())


def test_F4_zero_valued_numeric_pii_is_not_counted(tmp_path):
    rep, out = _report_for(tmp_path, {"pin": 0, "uhid": 0, "note": "ok"})
    assert out == {"pin": 0, "uhid": 0, "note": "ok"}
    assert rep["counts"]["identifiers_detected"] == 0 and rep.get("entities", {}) == {}


def test_F4_nonzero_numbers_and_strings_are_replaced_and_counted(tmp_path):
    rep, out = _report_for(tmp_path, {"pin": 226001, "uhid": 400417, "mobile": PHONE, "zero": 0.0, "pin2": 0})
    assert out["pin"] == 0 and out["uhid"] == 0 and out["mobile"] == "[PHONE]" and isinstance(out["pin"], int)
    assert rep["counts"]["identifiers_detected"] == 3
    assert rep["entities"] == {"MRN": 1, "PHONE": 1, "PIN": 1}


def test_F4_unchanged_generalisation_is_not_counted(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "id": "b",
        "type": "collection",
        "entry": [
            {"fullUrl": "urn:uuid:p", "resource": {"resourceType": "Patient", "id": "p", "birthDate": "1980"}},
            {"fullUrl": "urn:uuid:q", "resource": {"resourceType": "Patient", "id": "q", "birthDate": "1962-01-30"}},
        ],
    }
    rep, out = _report_for(tmp_path, bundle)
    assert [e["resource"]["birthDate"] for e in out["entry"]] == ["1980", "1962"]
    assert rep["counts"]["identifiers_detected"] == 1 and rep["counts"]["records_generalized"] == 1
