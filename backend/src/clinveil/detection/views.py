"""Decoded *views* of encoded field values, with an exact offset map back to the original.

Detectors must see what a reader (or the scorer, which decodes before counting)
sees. Three encodings hide identifiers from pattern detectors:

* **XHTML markup** (FHIR ``text.div``, HTML notes): tags become a line break, so a
  detector never runs across ``</p>`` and an address never swallows markup;
* **HTML character references** (``&#79;rvila``, ``&#x39;&#x38;…``, ``&amp;``);
* **percent-encoding** (``Orvila%20Tamsen``, ``TST%2F26%2F004417``) in paths and URLs.

:func:`decoded_view` returns ``None`` when a value has none of these (the common
case, zero cost). Otherwise each view character records the original span it came
from; :meth:`View.spans` maps a view span back to one or more original spans and
never lets a span cross a tag, so replacing those spans keeps the markup and the
escaping of everything else intact (a placeholder such as ``[NAME]`` needs no
escaping in XHTML, JSON or a URL path).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TAG = re.compile(
    r"</?(?:div|p|br|span|td|th|tr|table|tbody|thead|b|i|u|ul|ol|li|h[1-6]|pre|code|a|em|strong|sub|sup|img|"
    r"hr|blockquote|caption|col|colgroup|dl|dt|dd|font|small|big|section|article|header|footer)\b[^<>]*/?>",
    re.I,
)
_ENTITY = re.compile(r"&(?:#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_PCT_RUN = re.compile(r"(?:%[0-9A-Fa-f]{2})+")


@dataclass(frozen=True, slots=True)
class View:
    text: str
    starts: tuple[int, ...]  # original start of each view character
    ends: tuple[int, ...]  # original end of each view character
    tag: tuple[bool, ...]  # the view character stands for a markup tag

    def __repr__(self) -> str:
        return f"View(len={len(self.text)})"

    def span(self, s: int, e: int) -> tuple[int, int]:
        """Covering original span of view ``[s, e)`` (used for keep spans)."""
        e = max(e, s + 1)
        return self.starts[s], self.ends[min(e, len(self.ends)) - 1]

    def spans(self, s: int, e: int) -> list[tuple[int, int]]:
        """Original spans for view ``[s, e)``, split so that none contains a tag."""
        out: list[tuple[int, int]] = []
        run_start: int | None = None
        for i in range(s, min(e, len(self.text))):
            if self.tag[i] or self.text[i] in "<>":
                if run_start is not None:
                    out.append((self.starts[run_start], self.ends[i - 1]))
                    run_start = None
            elif run_start is None:
                run_start = i
        if run_start is not None:
            out.append((self.starts[run_start], self.ends[min(e, len(self.text)) - 1]))
        return [(a, b) for a, b in out if b > a]


def _utf8_chunks(data: bytes) -> list[tuple[int, int]]:
    """(byte offset, byte length) of each UTF-8 sequence in ``data`` (invalid bytes count alone)."""
    out, i = [], 0
    while i < len(data):
        b = data[i]
        n = 1 if b < 0x80 else 2 if b >> 5 == 0b110 else 3 if b >> 4 == 0b1110 else 4 if b >> 3 == 0b11110 else 1
        if i + n > len(data):
            n = 1
        out.append((i, n))
        i += n
    return out


def decoded_view(text: str) -> View | None:
    markup = bool(_TAG.search(text))
    entity = bool(_ENTITY.search(text))
    pct = bool(_PCT_RUN.search(text)) and ("://" in text or not any(c.isspace() for c in text.strip()))
    if not (markup or entity or pct):
        return None
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    tags: list[bool] = []

    def emit(ch: str, a: int, b: int, is_tag: bool = False) -> None:
        chars.append(ch)
        starts.append(a)
        ends.append(b)
        tags.append(is_tag)

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if markup and c == "<" and (m := _TAG.match(text, i)):
            emit("\n", m.start(), m.end(), True)
            i = m.end()
            continue
        if entity and c == "&" and (m := _ENTITY.match(text, i)):
            dec = html.unescape(m.group())
            if dec != m.group():
                for ch in dec:
                    emit(ch, m.start(), m.end())
                i = m.end()
                continue
        if pct and c == "%" and (m := _PCT_RUN.match(text, i)):
            data = bytes.fromhex(m.group().replace("%", ""))
            for off, length in _utf8_chunks(data):
                a = m.start() + 3 * off
                b = a + 3 * length
                for ch in data[off : off + length].decode("utf-8", errors="replace"):
                    emit(ch, a, b)
            i = m.end()
            continue
        emit(c, i, i + 1)
        i += 1
    return View("".join(chars), tuple(starts), tuple(ends), tuple(tags))


def decode_slice(s: str) -> str:
    """Plain text of an original slice (for adding a decoded value to an index)."""
    v = decoded_view(s)
    return v.text if v is not None else s
