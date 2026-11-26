"""Phase 2.1 verification: binary attachments are withheld without breaking FHIR or JSON structure.

Exact behaviour (also documented in PHASE2_REMEDIATION.md, D4):
* a declared binary attachment (``contentType`` + ``data``), a FHIR ``Binary.data`` and an
  undeclared binary ``valueBase64Binary`` lose that member only; a declared attachment also
  loses ``hash`` and ``size`` (they describe the removed bytes); everything else stays;
* a text attachment is decoded, cleaned and re-encoded (never withheld);
* a binary payload that is a JSON array element becomes ``"[ATTACHMENT-WITHHELD]"``, so the
  array keeps its length and positions; inside free text the span is replaced the same way.
"""

from __future__ import annotations

import base64
import json
import re

from conftest import sanitize_documents, sanitize_text

JPG = base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(80)).decode()
PDF = base64.b64encode(b"%PDF-1.4\n" + b"x" * 80).decode()
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(80)).decode()
TXT = base64.b64encode(b"Consent signed by Name: Orvila Tamsen, Mob 9876543210").decode()
P = {"reference": "urn:uuid:p"}
_FHIR_ID = re.compile(r"[A-Za-z0-9\-.]{1,64}")


def _bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "id": "b",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:p",
                "resource": {
                    "resourceType": "Patient",
                    "id": "p",
                    "name": [{"text": "Orvila Tamsen"}],
                    "photo": [{"contentType": "image/jpeg", "data": JPG, "size": 90, "hash": "abc="}],
                },
            },
            {
                "fullUrl": "urn:uuid:d",
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "d",
                    "status": "current",
                    "subject": P,
                    "content": [
                        {"attachment": {"contentType": "application/pdf", "data": PDF, "title": "scan"}},
                        {"attachment": {"contentType": "text/plain", "data": TXT}},
                    ],
                },
            },
            {
                "fullUrl": "urn:uuid:bin",
                "resource": {"resourceType": "Binary", "id": "bin", "contentType": "image/png", "data": PNG},
            },
            {
                "fullUrl": "urn:uuid:o",
                "resource": {
                    "resourceType": "Observation",
                    "id": "o",
                    "status": "final",
                    "subject": P,
                    "code": {"text": "ECG strip"},
                    "valueBase64Binary": JPG,
                },
            },
        ],
    }


def _walk(node, path=()):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, (*path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, (*path, i))


def test_fhir_binary_attachments_withheld_structure_and_references_intact():
    from clinveil.parsing.fhir import build_index

    src = _bundle()
    out = json.loads(sanitize_documents({"fhir/b.json": json.dumps(src).encode()})["fhir/b.json"])
    res = [e["resource"] for e in out["entry"]]
    # same entries, same types, same ids, references resolve
    assert [r["resourceType"] for r in res] == [e["resource"]["resourceType"] for e in src["entry"]]
    assert all(_FHIR_ID.fullmatch(r["id"]) for r in res)
    idx = build_index(out)
    assert not idx.unresolved and len(idx.references) == 2
    # exactly the binary members are gone
    assert res[0]["photo"] == [{"contentType": "image/jpeg"}]
    assert res[1]["content"][0]["attachment"] == {"contentType": "application/pdf", "title": "scan"}
    assert res[2] == {"resourceType": "Binary", "id": "bin", "contentType": "image/png"}  # Binary.data is 0..1
    assert "valueBase64Binary" not in res[3] and res[3]["code"] == {"text": "ECG strip"}
    # the text attachment is cleaned and re-encoded, still valid base64 with its contentType
    txt = res[1]["content"][1]["attachment"]
    decoded = base64.b64decode(txt["data"], validate=True).decode()
    assert txt["contentType"] == "text/plain" and "Orvila" not in decoded and "9876543210" not in decoded
    # every remaining Attachment-like object with data still has a contentType (att-1), and data is valid base64
    for _, obj in _walk(out):
        if "data" in obj:
            assert "contentType" in obj
            base64.b64decode(obj["data"], validate=True)
    for payload in (JPG, PDF, PNG):
        assert payload not in json.dumps(out)


def test_array_elements_keep_their_slot():
    doc = {"scans": [JPG, "keep me", PDF], "meta": {"n": 3}}
    out = json.loads(sanitize_documents({"x/scans.json": json.dumps(doc).encode()})["x/scans.json"])
    assert out == {"scans": ["[ATTACHMENT-WITHHELD]", "keep me", "[ATTACHMENT-WITHHELD]"], "meta": {"n": 3}}


def test_binary_payload_in_text_is_replaced_in_place():
    out = sanitize_text(f"photo: {JPG} end")
    assert out == "photo: [ATTACHMENT-WITHHELD] end"


def test_invalid_declared_payload_still_quarantines():
    import pytest

    from clinveil.security.errors import QuarantineError

    bad = {"attachment": {"contentType": "text/plain", "data": "A" * 33}}
    with pytest.raises(QuarantineError) as exc:
        sanitize_documents({"f/f.json": json.dumps(bad).encode()})
    assert exc.value.code == "invalid_attachment"
