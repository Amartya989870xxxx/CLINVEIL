"""Content-based format detection: extensions are evidence, not truth."""

import json

import pytest

from clinveil.ingestion.detect import detect
from clinveil.ingestion.limits import IngestLimits
from clinveil.models.document import Format
from clinveil.security.errors import QuarantineError

L = IngestLimits()


def _q(raw: bytes, ext: str) -> str:
    with pytest.raises(QuarantineError) as e:
        detect(raw, ext, L)
    return e.value.code


@pytest.mark.parametrize(
    "raw, ext, fmt, delim",
    [
        (b"a,b\n1,2\n", ".csv", Format.CSV, ","),
        (b"a\tb\n1\t2\n", ".tsv", Format.TSV, "\t"),
        (b"a\tb\tc\n1\t2\t3\n4\t5\t6\n", ".csv", Format.TSV, "\t"),  # tab content in a .csv
        (b"a;b;c\n1;2;3\n", ".csv", Format.CSV, ";"),
        (b'{"visits": []}', ".json", Format.JSON, None),
        (b'[{"a": 1}]', ".json", Format.JSON, None),
        (b'{"resourceType": "Bundle", "type": "document", "entry": []}', ".json", Format.FHIR, None),
        (b'{"resourceType": "Patient", "id": "p1"}', ".json", Format.FHIR, None),
        (b"Discharge summary.\nBP 120/80\n", ".txt", Format.TEXT, None),
        (b"plain note with an odd extension", ".log", Format.TEXT, None),
    ],
)
def test_supported_formats(raw, ext, fmt, delim):
    d = detect(raw, ext, L)
    assert d.format is fmt and d.delimiter == delim


def test_json_behind_csv_extension_is_json():
    d = detect(b'{"patient": "x", "id": "1"}', ".csv", L)
    assert d.format is Format.JSON and d.extension_mismatch
    assert d.data == {"patient": "x", "id": "1"}


def test_csv_whose_header_starts_with_bracket_stays_csv():
    d = detect(b"[Name],[Age]\nA,1\nB,2\n", ".csv", L)
    assert d.format is Format.CSV and not d.extension_mismatch


def test_text_note_starting_with_bracket_stays_text():
    d = detect(b"[Nursing] patient comfortable, BP 118/76", ".txt", L)
    assert d.format is Format.TEXT


def test_json_content_in_txt_is_parsed_as_json():
    d = detect(json.dumps({"note": "x"}).encode(), ".txt", L)
    assert d.format is Format.JSON and d.extension_mismatch


@pytest.mark.parametrize(
    "raw, ext, code",
    [
        (b"", ".csv", "empty_file"),
        (b"  \n\t\n", ".txt", "empty_file"),
        (b"\xff\xfe", ".tsv", "empty_file"),  # BOM only
        (b"%PDF-1.4\n1 0 obj", ".pdf", "unsupported_pdf"),
        (b"%PDF-1.4\n1 0 obj", ".txt", "unsupported_pdf"),  # signature beats extension
        (b"\xff\xd8\xff\xe0JFIF", ".jpg", "unsupported_image"),
        (b"\x89PNG\r\n\x1a\nxxxx", ".csv", "unsupported_image"),
        (b"PK\x03\x04xxxx", ".json", "unsupported_archive"),
        (b"\x1f\x8bxxxx", ".csv", "unsupported_archive"),
        (b"\x7fELF\x02\x01", ".txt", "unsupported_binary"),
        (b'<?xml version="1.0"?><doc><name>x</name></doc>', ".xml", "unsupported_xml"),
        (b"<ClinicalDocument><id/></ClinicalDocument>\n", ".txt", "unsupported_xml"),
        (b'{"visits": [{"patient": "x", "mob', ".json", "invalid_json"),
        (b'{"visits": [{"patient": "x", "mob', ".csv", "invalid_json"),
        (b'{"x": NaN}', ".json", "invalid_json"),
    ],
)
def test_quarantine_reasons(raw, ext, code):
    assert _q(raw, ext) == code


def test_truncated_json_with_txt_extension_degrades_to_text():
    d = detect(b'{"visits": [{"note": "x"', ".txt", L)
    assert d.format is Format.TEXT


def test_detection_is_deterministic():
    raw = b'{"a": [1, 2, {"b": "c"}]}'
    assert detect(raw, ".json", L) == detect(raw, ".json", L)
