import pytest

from clinveil.config.policy import Policy, load_policy
from clinveil.ingestion.decoding import decode
from clinveil.parsing import csv_format, json_format


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("नाम: test".encode(), "नाम: test"),
        (b"\xef\xbb\xbfa,b\n", "a,b\n"),
        ("a\tb\n".encode("utf-16"), "a\tb\n"),
        ("a\tb\n".encode("utf-16-be").join([b"\xfe\xff", b""]), "a\tb\n"),
        ("Café".encode("cp1252"), "Café"),
    ],
)
def test_decode_supported_encodings(raw, expected):
    assert decode(raw) == expected


def test_decode_rejects_bytes_invalid_in_utf8_and_cp1252():
    assert decode(b"x \x81\x8d y") is None


def test_bom_with_invalid_utf8_raises():
    with pytest.raises(UnicodeDecodeError):
        decode(b"\xef\xbb\xbf\xff\xfe")


def test_csv_roundtrip_keeps_delimiter_header_and_quoting():
    text = 'a\tb\n1\t"x\ty"\n'
    rows = csv_format.read_rows(text, "\t")
    assert rows == [["a", "b"], ["1", "x\ty"]]
    assert csv_format.read_rows(csv_format.write_rows(rows[0], rows[1:], "\t"), "\t") == rows


def test_json_locators():
    assert json_format.record_locators({"resourceType": "Bundle", "entry": [{}]}) == ["doc"]
    assert json_format.record_locators({"meta": {}, "x": 1}) == ["doc"]
    assert json_format.record_locators([{"a": 1}]) == ["doc"]
    assert json_format.record_locators({"visits": [{"a": 1}, {"a": 2}], "a/b": [{"c": 1}]}) == [
        "/visits/0",
        "/visits/1",
        "/a~1b/0",
    ]
    assert json_format.pointer_escape("~/") == "~0~1"


def test_policy_defaults_and_overrides(tmp_path):
    assert load_policy(None) == Policy()
    f = tmp_path / "p.yaml"
    f.write_text("age_band_years: 10  # comment\nnew_knob: abc\n", encoding="utf-8")
    p = load_policy(f)
    assert p.age_band_years == 10 and p.date_shift_max_days == 180
    assert p.extra == {"new_knob": "abc"}


def test_policy_rejects_invalid_values(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("age_band_years: 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(f)
