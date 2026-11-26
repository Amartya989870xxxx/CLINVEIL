"""Base64 payload discovery and decoding.

Two ways a string value can carry a base64 payload:

* **Declared**: the value sits under a data-like key (``data``, ``payload``…) of an
  object that also has a content-type key (FHIR ``Attachment``, scanned forms)
  and the value is shaped like base64. It *must* then decode. Otherwise the file
  is quarantined (``invalid_attachment``). A declared key holding ordinary prose
  is not a payload and is treated like any other string.
* **Undeclared**: any run of 24+ base64 characters (or a whole value that is
  base64 with line breaks). Such a run is only treated as a payload when it
  decodes to clean, printable UTF-8 text. URL fragments, hashes and random tokens
  decode to non-text bytes and are ignored, so ordinary identifiers are not
  misclassified.

Payloads that decode to a binary signature (PDF, JPEG…), or declared payloads
that are not plausible text, cannot be sanitised and quarantine the whole file
(``unsupported_attachment``). Oversized payloads raise ``attachment_too_large``.
Decoded text is not scanned for a second level of base64.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

from clinveil.ingestion.decoding import decode_text
from clinveil.ingestion.limits import IngestLimits
from clinveil.ingestion.plausibility import has_binary_controls
from clinveil.ingestion.signatures import binary_signature
from clinveil.security.errors import QuarantineError

TYPE_KEYS = frozenset({"contenttype", "content_type", "mimetype", "mime_type", "mediatype", "media_type"})
DATA_KEYS = frozenset({"data", "payload", "base64", "blob", "file", "attachment"})
MIN_RUN = 24  # undeclared runs shorter than this are never treated as payloads
MIN_DECLARED = 16  # declared values shorter than this must decode to clean text to count

_RUN = re.compile(rf"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{{{MIN_RUN},}}={{0,2}}(?![A-Za-z0-9+/=])")
_WHOLE = re.compile(r"\s*[A-Za-z0-9+/][A-Za-z0-9+/\s]*={0,2}\s*")
_WS = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Payload:
    start: int
    end: int
    text: str
    encoding: str
    padded: bool
    declared_type: str | None

    def __repr__(self) -> str:
        return f"Payload(span={self.start}:{self.end}, encoding={self.encoding})"


def declared_type(obj: dict) -> str | None:
    for k, v in obj.items():
        if isinstance(k, str) and k.lower() in TYPE_KEYS and isinstance(v, str):
            return v
    return None


def is_declared_data_key(key: str) -> bool:
    return key.lower() in DATA_KEYS


def _b64bytes(s: str, limits: IngestLimits) -> tuple[bytes, bool] | None:
    compact = _WS.sub("", s)
    if not compact:
        return None
    if len(compact) * 3 // 4 > limits.max_attachment_bytes:
        raise QuarantineError("attachment_too_large")
    padded = compact.endswith("=")
    rem = len(compact) % 4
    if rem == 1:
        return None
    try:
        return base64.b64decode(compact + "=" * ((4 - rem) % 4), validate=True), padded
    except (binascii.Error, ValueError):
        return None


def _clean_utf8_text(data: bytes) -> str | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if has_binary_controls(text) or not all(c.isprintable() or c in "\t\n\r" for c in text):
        return None
    if sum(c.isalpha() for c in text) < 4:
        return None
    return text


def looks_base64(value: str) -> bool:
    return bool(_WHOLE.fullmatch(value))


def decode_declared(value: str, ctype: str | None, limits: IngestLimits) -> Payload | None:
    """Decode a declared payload; ``None`` if the value is empty or not a payload.

    Values shorter than ``MIN_DECLARED`` base64 characters that fail to decode as
    text are treated as ordinary strings (a short word such as ``pending`` is
    base64-shaped by accident). Longer base64-shaped values must decode.
    """
    if not looks_base64(value):
        return None
    compact_len = len(_WS.sub("", value))
    if compact_len == 0:
        return None
    short = compact_len < MIN_DECLARED
    decoded = _b64bytes(value, limits)
    if decoded is None:
        if short:
            return None
        raise QuarantineError("invalid_attachment")
    data, padded = decoded
    if not data:
        return None
    if binary_signature(data) is not None:
        raise QuarantineError("unsupported_attachment")
    try:
        dec = decode_text(data)
    except QuarantineError:
        if short:
            return None
        raise QuarantineError("unsupported_attachment") from None
    if short and _clean_utf8_text(data) is None:
        return None
    return Payload(0, len(value), dec.text, dec.encoding, padded, ctype)


def find_undeclared(value: str, limits: IngestLimits) -> list[Payload]:
    if len(value) < MIN_RUN:
        return []
    if _WHOLE.fullmatch(value) and len(_WS.sub("", value)) >= MIN_RUN:
        whole = _try_undeclared(value, 0, len(value), limits)
        if whole is not None:
            return [whole]
    out = []
    for m in _RUN.finditer(value):
        p = _try_undeclared(m.group(), m.start(), m.end(), limits)
        if p is not None:
            out.append(p)
    return out


def _try_undeclared(s: str, start: int, end: int, limits: IngestLimits) -> Payload | None:
    decoded = _b64bytes(s, limits)
    if decoded is None:
        return None
    data, padded = decoded
    if binary_signature(data) is not None:
        raise QuarantineError("unsupported_attachment")
    text = _clean_utf8_text(data)
    if text is None:
        return None
    return Payload(start, end, text, "utf-8", padded, None)
