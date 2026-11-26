# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Byte -> text decoding with encoding detection and plausibility validation.

Order (the first that applies wins):

1. UTF-8 BOM            -> strict UTF-8                 (``utf-8-sig``)
2. UTF-16 BOM           -> strict UTF-16 LE/BE          (``utf-16-le`` / ``utf-16-be``)
3. BOM-less UTF-16      -> NUL-byte pattern, then strict decode
4. strict UTF-8                                         (``utf-8``)
5. cp1252 fallback, accepted only if :func:`legacy_fallback_problems` finds
   nothing; otherwise ``implausible_text``                (``cp1252``)

Any decoded text containing binary control characters is ``unsupported_binary``.
Failures raise :class:`QuarantineError` with a fixed reason code.
"""

from __future__ import annotations

from dataclasses import dataclass

from clinveil.ingestion.plausibility import has_binary_controls, legacy_fallback_problems
from clinveil.security.errors import QuarantineError

UTF8_BOM = b"\xef\xbb\xbf"
UTF16_LE_BOM = b"\xff\xfe"
UTF16_BE_BOM = b"\xfe\xff"


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str
    encoding: str

    def __repr__(self) -> str:
        return f"DecodedText(encoding={self.encoding}, chars={len(self.text)})"


def _bomless_utf16(raw: bytes) -> str | None:
    """Detect UTF-16 without a BOM from the NUL pattern of mostly-ASCII text."""
    sample = raw[:4096]
    if len(sample) < 8 or len(sample) % 2:
        return None
    even = sample[0::2].count(0) / (len(sample) // 2)
    odd = sample[1::2].count(0) / (len(sample) // 2)
    if odd > 0.4 and even < 0.05:
        return "utf-16-le"
    if even > 0.4 and odd < 0.05:
        return "utf-16-be"
    return None


def decode_text(raw: bytes) -> DecodedText:
    try:
        if raw.startswith(UTF8_BOM):
            result = DecodedText(raw[3:].decode("utf-8"), "utf-8-sig")
        elif raw.startswith(UTF16_LE_BOM):
            result = DecodedText(raw[2:].decode("utf-16-le"), "utf-16-le")
        elif raw.startswith(UTF16_BE_BOM):
            result = DecodedText(raw[2:].decode("utf-16-be"), "utf-16-be")
        elif enc := _bomless_utf16(raw):
            result = DecodedText(raw.decode(enc), enc)
        else:
            result = _utf8_or_legacy(raw)
    except UnicodeDecodeError:
        raise QuarantineError("undecodable_text") from None
    if has_binary_controls(result.text):
        raise QuarantineError("unsupported_binary")
    return result


def _utf8_or_legacy(raw: bytes) -> DecodedText:
    try:
        return DecodedText(raw.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        pass
    text = raw.decode("cp1252")  # may raise for the five undefined bytes -> undecodable_text
    if legacy_fallback_problems(raw, text):
        raise QuarantineError("implausible_text")
    return DecodedText(text, "cp1252")


def encode_text(text: str, encoding: str) -> bytes:
    """Inverse of :func:`decode_text` for re-encoding transformed payloads."""
    if encoding == "utf-8-sig":
        return UTF8_BOM + text.encode("utf-8")
    if encoding == "utf-16-le":
        return UTF16_LE_BOM + text.encode("utf-16-le")
    if encoding == "utf-16-be":
        return UTF16_BE_BOM + text.encode("utf-16-be")
    return text.encode(encoding)
