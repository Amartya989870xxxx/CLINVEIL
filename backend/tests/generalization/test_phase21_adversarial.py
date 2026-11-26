"""Phase 2.1 adversarial generalisation: every audit attack class, on unseen generated data.

Values are checked on the *decoded* output (HTML entities, %-escapes and base64
payloads are decoded before looking), as the official scorer does. Each category
must leak nothing and keep its clinical values, for every seed.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import re
import urllib.parse

import pytest
from adversarial import cases, html_unescape

from conftest import sanitize_documents

SEEDS = tuple(range(25))
_B64 = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")


def _decoded(text: str) -> str:
    parts = [text, html_unescape(text), urllib.parse.unquote(text)]
    for m in _B64.finditer(text):
        tok = m.group().replace("-", "+").replace("_", "/")
        with contextlib.suppress(binascii.Error, ValueError, UnicodeDecodeError):
            parts.append(base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True).decode("utf-8"))
    return "\n".join(parts)


def _all_cases() -> list:
    return [pytest.param(c, id=f"{c.category}-{seed}") for seed in SEEDS for c in cases(seed)]


@pytest.mark.parametrize("case", _all_cases())
def test_adversarial_case(case):
    out = sanitize_documents(case.files)
    released = "\n".join([*out, *out.values()])  # output paths are a channel too
    seen = _decoded(released)
    for value in case.vanish:
        assert value not in seen, (case.category, "leaked")
    plain = "\n".join(out.values())
    for value in case.keep:
        assert value in plain, (case.category, "lost", value)
    if case.fhir:
        from clinveil.parsing.fhir import build_index

        for rel, text in out.items():
            if rel.startswith("fhir/"):
                assert not build_index(json.loads(text)).unresolved
