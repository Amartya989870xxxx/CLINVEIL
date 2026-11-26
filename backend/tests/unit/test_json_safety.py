"""Bounded JSON parsing: depth, size, node count, strict syntax."""

import pytest

from clinveil.ingestion.limits import IngestLimits
from clinveil.parsing.json_safety import count_nodes, load_json, nesting_depth
from clinveil.security.errors import QuarantineError


def _code(text: str, **limits) -> str:
    with pytest.raises(QuarantineError) as e:
        load_json(text, IngestLimits(**limits))
    return e.value.code


def test_depth_scan_ignores_brackets_inside_strings():
    assert nesting_depth('{"a": "[[[{{{", "b": [1, [2]]}') == 3
    assert nesting_depth('{"a": "esc \\" [[["}') == 1
    assert nesting_depth("{}") == 1


def test_depth_scan_stops_early():
    assert nesting_depth("[" * 100_000, stop_at=10) == 11


def test_deep_json_quarantined_without_recursion():
    for depth in (65, 1_500, 200_000):
        assert _code("[" * depth + "]" * depth) == "json_too_deep"
    assert load_json("[" * 64 + "]" * 64, IngestLimits()) is not None  # at the limit is fine


@pytest.mark.parametrize("text", ['{"a": 1', '{"a": }', "[1, 2", '{"a": "unterminated}', "{'a': 1}"])
def test_invalid_and_truncated_json(text):
    assert _code(text) == "invalid_json"


@pytest.mark.parametrize("text", ['{"x": NaN}', '{"x": Infinity}', "[-Infinity]"])
def test_non_standard_constants_rejected(text):
    assert _code(text) == "invalid_json"


def test_size_and_node_limits():
    assert _code('{"a": "' + "x" * 200 + '"}', max_json_bytes=100) == "json_too_large"
    assert _code("[" + ",".join(["1"] * 50) + "]", max_json_nodes=10) == "json_too_large"


def test_empty_containers_are_valid():
    assert load_json("{}", IngestLimits()) == {}
    assert load_json("[]", IngestLimits()) == []


def test_count_nodes():
    assert count_nodes({"a": [1, 2, {"b": None}]}) == 6
    assert count_nodes(list(range(100)), stop_at=5) == 6
