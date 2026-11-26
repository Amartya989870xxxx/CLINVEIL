"""Base64 payload discovery: declared attachments, embedded runs, safety."""

import base64

import pytest

from clinveil.ingestion.limits import IngestLimits
from clinveil.parsing.attachments import declared_type, decode_declared, find_undeclared
from clinveil.security.errors import QuarantineError

L = IngestLimits()
SECRET_TEXT = "Consent witnessed by Harendra Vexpal, phone 9876543210."
B64 = base64.b64encode(SECRET_TEXT.encode()).decode()


def test_declared_text_attachment_decodes():
    p = decode_declared(B64, "text/plain", L)
    assert p.text == SECRET_TEXT and p.encoding == "utf-8" and p.padded == B64.endswith("=")
    assert (p.start, p.end) == (0, len(B64))


def test_declared_attachment_with_mime_line_breaks():
    wrapped = "\n".join(B64[i : i + 16] for i in range(0, len(B64), 16))
    assert decode_declared(wrapped, "text/plain", L).text == SECRET_TEXT


def test_declared_binary_attachment_is_unsupported():
    pdf = base64.b64encode(b"%PDF-1.4\n" + b"x" * 40).decode()
    with pytest.raises(QuarantineError) as e:
        decode_declared(pdf, "application/pdf", L)
    assert e.value.code == "unsupported_attachment"


def test_declared_attachment_that_is_not_text_is_unsupported():
    blob = base64.b64encode(bytes(range(256)) * 2).decode()
    with pytest.raises(QuarantineError) as e:
        decode_declared(blob, "application/octet-stream", L)
    assert e.value.code in ("unsupported_attachment", "invalid_attachment")


def test_declared_long_invalid_base64_is_invalid():
    with pytest.raises(QuarantineError) as e:
        decode_declared("A" * 33, "text/plain", L)  # 33 chars: impossible base64 length
    assert e.value.code == "invalid_attachment"


def test_declared_prose_or_short_word_is_not_a_payload():
    assert decode_declared("Patient complained of fever.", "text/plain", L) is None
    assert decode_declared("pending", "text/plain", L) is None
    assert decode_declared("", "text/plain", L) is None


def test_attachment_size_limit():
    with pytest.raises(QuarantineError) as e:
        decode_declared(B64, "text/plain", IngestLimits(max_attachment_bytes=10))
    assert e.value.code == "attachment_too_large"


def test_declared_type_lookup_is_case_insensitive():
    assert declared_type({"contentType": "text/plain", "data": "x"}) == "text/plain"
    assert declared_type({"Content_Type": "text/csv"}) == "text/csv"
    assert declared_type({"data": "x"}) is None


def test_embedded_run_in_note_is_found():
    note = f"Scanned form attached: {B64} -- end"
    (p,) = find_undeclared(note, L)
    assert note[p.start : p.end] == B64 and p.text == SECRET_TEXT


def test_whole_value_with_line_breaks():
    wrapped = "\n".join(B64[i : i + 20] for i in range(0, len(B64), 20))
    (p,) = find_undeclared(wrapped, L)
    assert p.text == SECRET_TEXT and (p.start, p.end) == (0, len(wrapped))


@pytest.mark.parametrize(
    "value",
    [
        "https://nrces.in/ndhm/fhir/r4/StructureDefinition/DocumentBundle",
        "http://terminology.hl7.org/CodeSystem/condition-clinical",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # a SHA-256
        "TelmisartanHydrochlorothiazideCombination",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh",
        "urn:uuid:0f4d2a9c-6b1e-4c3a-8d7f-2e9b5a1c7d40",
    ],
)
def test_non_payloads_are_not_misdetected(value):
    assert find_undeclared(value, L) == []


def test_embedded_binary_payload_is_unsupported():
    jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00JFIF" + bytes(40)).decode()
    with pytest.raises(QuarantineError) as e:
        find_undeclared(f"photo: {jpeg}", L)
    assert e.value.code == "unsupported_attachment"


def test_unpadded_run_is_supported():
    unpadded = B64.rstrip("=")
    (p,) = find_undeclared(unpadded, L)
    assert p.text == SECRET_TEXT and not p.padded
