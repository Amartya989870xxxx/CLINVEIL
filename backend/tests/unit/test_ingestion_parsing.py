import pytest

from clinveil.config.policy import Policy, load_policy
from clinveil.parsing import csv_format, json_format


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
