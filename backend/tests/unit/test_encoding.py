"""Encoding detection and plausibility validation (all fixtures synthetic)."""

import pytest

from clinveil.ingestion.decoding import decode_text, encode_text
from clinveil.ingestion.plausibility import has_binary_controls, legacy_fallback_problems
from clinveil.security.errors import QuarantineError

NOTE = "Pt. reviewed. Temp 101.2°F – BP 130/90. Café visit.\nC/O fever x 3 days\n"


@pytest.mark.parametrize(
    "raw, encoding",
    [
        (NOTE.encode("utf-8"), "utf-8"),
        (b"\xef\xbb\xbf" + NOTE.encode("utf-8"), "utf-8-sig"),
        (b"\xff\xfe" + NOTE.encode("utf-16-le"), "utf-16-le"),
        (b"\xfe\xff" + NOTE.encode("utf-16-be"), "utf-16-be"),
        (NOTE.encode("utf-16-le"), "utf-16-le"),  # BOM-less, detected from the NUL pattern
        (NOTE.encode("utf-16-be"), "utf-16-be"),
        (NOTE.encode("cp1252"), "cp1252"),  # legitimate legacy export: ° – é survive
    ],
)
def test_legitimate_encodings_decode_exactly(raw, encoding):
    d = decode_text(raw)
    assert d.text == NOTE and d.encoding == encoding


def test_devanagari_utf8_and_utf16():
    text = "नाम: वसुधा मेहरोत्रा\tआयु: 38 वर्ष\n"
    assert decode_text(text.encode("utf-8")).text == text
    assert decode_text(text.encode("utf-16")).text == text


def test_invalid_utf8_with_bom_fragment_is_implausible():
    # ASCII note + a stray FF FE pair + a broken UTF-8 lead byte: cp1252 would yield "ÿþÃ("
    raw = b"OPD note for patient. \xff\xfe\xc3( Mobile pending. C/O cough.\n"
    with pytest.raises(QuarantineError) as e:
        decode_text(raw)
    assert e.value.code == "implausible_text"


def test_mixed_valid_utf8_and_corruption_is_implausible():
    raw = "Temp 101°F".encode() + b" \xe9 broken"  # valid UTF-8 "°" plus a lone cp1252-style byte
    with pytest.raises(QuarantineError) as e:
        decode_text(raw)
    assert e.value.code == "implausible_text"
    assert "utf8_fragments" in legacy_fallback_problems(raw, raw.decode("cp1252"))


def test_binary_garbage_through_cp1252_is_implausible():
    raw = bytes(range(0xA0, 0x100)) * 4  # all cp1252-decodable, almost no ASCII
    with pytest.raises(QuarantineError) as e:
        decode_text(raw)
    assert e.value.code == "implausible_text"


def test_bytes_undefined_in_cp1252_are_undecodable():
    with pytest.raises(QuarantineError) as e:
        decode_text(b"note \x81\x8d\x8f\x90\x9d end")
    assert e.value.code == "undecodable_text"


def test_bom_utf8_with_invalid_body_is_undecodable():
    with pytest.raises(QuarantineError) as e:
        decode_text(b"\xef\xbb\xbfok \xff\xfe")
    assert e.value.code == "undecodable_text"


def test_nul_bytes_mean_binary():
    with pytest.raises(QuarantineError) as e:
        decode_text(b"abc\x00def ghi jkl")
    assert e.value.code == "unsupported_binary"


def test_control_character_rules():
    assert not has_binary_controls("a\tb\nc\r\nd\x0c")
    assert not has_binary_controls("legacy text\r\n\x1a")  # DOS EOF at the end is fine
    assert has_binary_controls("a\x1ab")
    assert has_binary_controls("a\x07b")


@pytest.mark.parametrize("enc", ["utf-8", "utf-8-sig", "utf-16-le", "utf-16-be", "cp1252"])
def test_encode_is_inverse_of_decode(enc):
    assert decode_text(encode_text("Referral note, 120/80", enc)).text == "Referral note, 120/80"
