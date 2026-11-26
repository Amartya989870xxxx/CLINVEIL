"""Decoded-text plausibility: tell legitimate legacy text from corruption.

cp1252 maps all but five byte values to a character, so "it decoded" proves
nothing. When a file is *not* valid UTF-8 and we fall back to cp1252, the raw
bytes are checked for signs that it is really damaged UTF-8 or binary:

* ``utf8_fragments``: valid multi-byte UTF-8 sequences inside a file that is
  not valid UTF-8 overall. That is UTF-8 with corruption (or mixed encodings);
  cp1252 would turn it into mojibake such as ``Ã©``.
* ``bom_fragments``: byte-order marks in the middle of the file (``FF FE``,
  ``FE FF``, ``EF BB BF``), typical of concatenated or truncated exports.
* ``high_ratio``: more than 30% of non-whitespace characters are non-ASCII.
  Legitimate legacy English/Indian exports are overwhelmingly ASCII with
  occasional ``°``, ``–``, ``é``; binary rendered through cp1252 is not.

For every decoded text (any encoding) control characters other than tab, LF,
CR, FF, VT and a trailing DOS EOF (``0x1A``) mean binary content.
"""

from __future__ import annotations

import re

_UTF8_MULTIBYTE = re.compile(rb"[\xc2-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf4][\x80-\xbf]{3}")
_BOM_FRAGMENT = re.compile(rb"\xff\xfe|\xfe\xff|\xef\xbb\xbf")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x19\x1b-\x1f\x7f]")
NON_ASCII_MAX_RATIO = 0.30


def has_binary_controls(text: str) -> bool:
    if _CONTROL.search(text):
        return True
    i = text.find("\x1a")
    return i != -1 and text[i:].strip("\x1a\r\n") != ""  # DOS EOF only allowed at the end


def legacy_fallback_problems(raw: bytes, text: str) -> list[str]:
    """Reasons a cp1252-fallback decoding looks corrupted (empty list = plausible)."""
    problems: list[str] = []
    if _UTF8_MULTIBYTE.search(raw):
        problems.append("utf8_fragments")
    if _BOM_FRAGMENT.search(raw):
        problems.append("bom_fragments")
    visible = [c for c in text if not c.isspace()]
    if visible and sum(ord(c) > 127 for c in visible) / len(visible) > NON_ASCII_MAX_RATIO:
        problems.append("high_ratio")
    return problems
