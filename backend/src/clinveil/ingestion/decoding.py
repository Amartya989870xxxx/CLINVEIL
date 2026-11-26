# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Byte -> text decoding (starter-equivalent).

Order: UTF-8 BOM (strict), UTF-16 BOM, plain UTF-8, cp1252. cp1252 leaves only
five bytes undefined, so it accepts almost anything; Phase 1 adds a plausibility
check so binary/corrupt content is quarantined instead of decoded as mojibake.
"""

from __future__ import annotations

UTF8_BOM = b"\xef\xbb\xbf"
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def decode(raw: bytes) -> str | None:
    if raw.startswith(UTF8_BOM):
        return raw[3:].decode("utf-8", errors="strict")
    if raw.startswith(UTF16_BOMS):
        return raw.decode("utf-16")
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None
