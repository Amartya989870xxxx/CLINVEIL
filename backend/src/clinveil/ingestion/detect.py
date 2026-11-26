"""Content-based format detection. The extension is supporting evidence only.

Decision procedure for one file's bytes:

1. empty / whitespace-only                      -> quarantine ``empty_file``
2. binary signature (PDF, JPEG, PNG, GIF, ZIP, GZIP, OLE2, ELF, PE…)
                                                 -> quarantine ``unsupported_*``
3. decode (:mod:`clinveil.ingestion.decoding`)  -> ``undecodable_text`` /
   ``implausible_text`` / ``unsupported_binary`` on failure
4. content starts with ``{`` or ``[``            -> bounded JSON parse
   (:mod:`clinveil.parsing.json_safety`). Success: JSON, or FHIR when the root
   object has a string ``resourceType``. Failure: a ``.txt`` (or unknown
   extension) falls through to text; a ``.csv``/``.tsv`` falls through only if it
   sniffs as a real multi-column table; anything else is quarantined with the
   JSON reason code.
5. markup (``<?xml`` or a leading element tag)   -> quarantine ``unsupported_xml``
6. ``.csv`` / ``.tsv``                           -> delimited, delimiter sniffed
7. otherwise                                     -> plain text

``extension_mismatch`` records when the content disagrees with the extension
(for example JSON in ``mislabeled_export.csv``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from clinveil.ingestion.decoding import decode_text
from clinveil.ingestion.limits import IngestLimits
from clinveil.ingestion.signatures import REASON_FOR_FORMAT, binary_signature
from clinveil.models.document import Format
from clinveil.parsing.csv_format import CANDIDATE_DELIMITERS, delimiter_for, sniff_delimiter, table_shape
from clinveil.parsing.json_format import is_fhir
from clinveil.parsing.json_safety import load_json, looks_like_json
from clinveil.security.errors import QuarantineError

DELIMITED_EXTS = (".csv", ".tsv")
TEXT_EXTS = (".txt", ".text", ".log", ".md", ".note")

_EXT_FORMATS: dict[str, frozenset[Format]] = {
    ".csv": frozenset({Format.CSV, Format.TSV}),
    ".tsv": frozenset({Format.CSV, Format.TSV}),
    ".json": frozenset({Format.JSON, Format.FHIR}),
    ".txt": frozenset({Format.TEXT}),
    ".xml": frozenset({Format.XML}),
    ".pdf": frozenset({Format.PDF}),
    ".jpg": frozenset({Format.JPEG}),
    ".jpeg": frozenset({Format.JPEG}),
    ".png": frozenset({Format.PNG}),
    ".gif": frozenset({Format.GIF}),
    ".zip": frozenset({Format.ZIP}),
    ".gz": frozenset({Format.GZIP}),
}

_MARKUP = re.compile(r"<(\?xml|!DOCTYPE|[A-Za-z][\w:.-]*)[\s>/]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Detection:
    format: Format
    encoding: str
    text: str
    data: Any = None  # parsed JSON for JSON/FHIR
    delimiter: str | None = None
    extension_mismatch: bool = False

    def __repr__(self) -> str:
        return f"Detection(format={self.format.value}, encoding={self.encoding}, mismatch={self.extension_mismatch})"


def mismatch(ext: str, fmt: Format) -> bool:
    expected = _EXT_FORMATS.get(ext)
    return expected is not None and fmt not in expected


def _is_markup(text: str) -> bool:
    head = text.lstrip()
    return bool(_MARKUP.match(head)) and head.rstrip().endswith(">")


def _is_table(text: str) -> bool:
    """Real tabular evidence: >= 2 columns, >= 2 rows, and >= 80% of rows that wide."""
    for d in CANDIDATE_DELIMITERS:
        width, consistency, rows = table_shape(text, d)
        if width >= 2 and rows >= 2 and consistency >= 0.8:
            return True
    return False


def detect(raw: bytes, ext: str, limits: IngestLimits) -> Detection:
    if not raw.strip():
        raise QuarantineError("empty_file")
    sig = binary_signature(raw)
    if sig is not None:
        raise QuarantineError(REASON_FOR_FORMAT[sig])
    decoded = decode_text(raw)
    text, enc = decoded.text, decoded.encoding
    if not text.strip():
        raise QuarantineError("empty_file")

    if looks_like_json(text):
        try:
            data = load_json(text, limits)
        except QuarantineError:
            if ext in DELIMITED_EXTS and _is_table(text):
                pass  # e.g. a CSV whose first header cell starts with "["
            elif ext in TEXT_EXTS or (ext not in _EXT_FORMATS and ext not in DELIMITED_EXTS):
                return Detection(Format.TEXT, enc, text, extension_mismatch=mismatch(ext, Format.TEXT))
            else:
                raise
        else:
            fmt = Format.FHIR if is_fhir(data) else Format.JSON
            return Detection(fmt, enc, text, data=data, extension_mismatch=mismatch(ext, fmt))

    if _is_markup(text):
        raise QuarantineError("unsupported_xml")

    if ext in DELIMITED_EXTS:
        delim = sniff_delimiter(text, delimiter_for(ext))
        fmt = Format.TSV if delim == "\t" else Format.CSV
        return Detection(fmt, enc, text, delimiter=delim, extension_mismatch=mismatch(ext, fmt))

    return Detection(Format.TEXT, enc, text, extension_mismatch=mismatch(ext, Format.TEXT))
