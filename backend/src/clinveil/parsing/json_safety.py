"""Bounded JSON parsing.

Limits are enforced *before* and *after* ``json.loads`` so nothing recurses or
allocates without bound:

1. text size ``<= max_json_bytes``          else ``json_too_large``
2. nesting depth ``<= max_json_depth``, measured by a linear token scan that
   skips string literals (no recursion; stops at the limit) else ``json_too_deep``.
   With depth capped well below the interpreter's recursion limit, ``json.loads``
   and every recursive walker downstream are safe.
3. strict syntax (no ``NaN``/``Infinity``, which are not JSON and would be
   re-emitted as invalid JSON)                 else ``invalid_json``
4. total containers + values ``<= max_json_nodes`` else ``json_too_large``
"""

from __future__ import annotations

import json
import re
from typing import Any

from clinveil.ingestion.limits import IngestLimits
from clinveil.security.errors import QuarantineError

_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[\[\]{}]')


def nesting_depth(text: str, stop_at: int | None = None) -> int:
    """Maximum ``{``/``[`` nesting depth, ignoring brackets inside strings."""
    depth = deepest = 0
    for m in _TOKEN.finditer(text):
        ch = m.group()
        if ch in "[{":
            depth += 1
            if depth > deepest:
                deepest = depth
                if stop_at is not None and deepest > stop_at:
                    return deepest
        elif ch in "]}":
            depth -= 1
    return deepest


def count_nodes(data: Any, stop_at: int | None = None) -> int:
    n, stack = 0, [data]
    while stack:
        x = stack.pop()
        n += 1
        if stop_at is not None and n > stop_at:
            return n
        if isinstance(x, dict):
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return n


def _reject_constant(_name: str) -> Any:
    raise ValueError("non-standard JSON constant")


def looks_like_json(text: str) -> bool:
    return text.lstrip()[:1] in ("{", "[")


def load_json(text: str, limits: IngestLimits) -> Any:
    if len(text.encode("utf-8", errors="ignore")) > limits.max_json_bytes:
        raise QuarantineError("json_too_large")
    if nesting_depth(text, stop_at=limits.max_json_depth) > limits.max_json_depth:
        raise QuarantineError("json_too_deep")
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise QuarantineError("invalid_json") from None
    if count_nodes(data, stop_at=limits.max_json_nodes) > limits.max_json_nodes:
        raise QuarantineError("json_too_large")
    return data
