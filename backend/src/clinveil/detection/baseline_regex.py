# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""The starter's regex redactor, kept verbatim as the Phase 0 baseline.

Known weaknesses (measured, see docs/evaluation/BASELINE.md): no names beyond
``name:`` labels, no Devanagari, no relatives, no MRN/UHID, no hidden channels.
Patterns are applied sequentially, so later patterns see earlier placeholders.
Phase 2 replaces this with the layered detector + sanitiser split.
"""

from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("NAME", re.compile(r"(?i)(?<=name:)\s*[^\n,;|]+")),
]


def redact(text: str) -> tuple[str, int]:
    """Return ``(redacted_text, n_identifiers_replaced)``."""
    total = 0
    for kind, rx in PATTERNS:
        text, n = rx.subn(f"[{kind}]" if kind != "NAME" else " [NAME]", text)
        total += n
    return text, total
