"""Common internal representation (IR) of one parsed input file.

Every supported format is parsed into a :class:`Document`:

* ``source``: file identity (relative path, SHA-256, size, extension, detected
  format, encoding, delimiter, extension mismatch);
* ``records``: the record locators reported in ``records.jsonl`` (``row:N``,
  RFC 6901 pointers, ``doc``);
* ``fields``: one :class:`Field` per addressable value (CSV header and cell, JSON
  key and leaf, note text, filename component, decoded base64 payload) with
  its structural path, owning record, channel, kind, label and FHIR context;
* ``native``: the parsed structure that renderers rebuild output from;
* ``fhir``: an index of Bundle entries and references (FHIR documents only).

Detectors (Phase 2) read ``fields`` and never need to know the file format.
The sanitiser maps field addresses to new values; a format-specific renderer
then rebuilds the file, preserving structure.

Raw values are excluded from every ``repr`` so an IR object can never leak PII
into a log line or traceback.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from clinveil.models.channels import Channel


class Format(str, Enum):
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    FHIR = "fhir"
    TEXT = "text"
    XML = "xml"
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    GIF = "gif"
    ZIP = "zip"
    GZIP = "gzip"
    BINARY = "binary"

    @property
    def is_supported(self) -> bool:
        return self in SUPPORTED_FORMATS


SUPPORTED_FORMATS = frozenset({Format.CSV, Format.TSV, Format.JSON, Format.FHIR, Format.TEXT})


class FieldKind(str, Enum):
    HEADER = "header"  # CSV/TSV header cell
    CELL = "cell"  # CSV/TSV data cell
    JSON_KEY = "json_key"  # an object member's key
    JSON_STRING = "json_string"
    JSON_NUMBER = "json_number"
    JSON_BOOL = "json_bool"
    JSON_NULL = "json_null"
    TEXT = "text"  # a whole plain-text document
    FILENAME = "filename"  # one component of the relative input path
    BASE64_TEXT = "base64_text"  # text decoded from a base64 segment of a parent field


#: Field kinds whose value is text and can be transformed in place.
TEXT_KINDS = frozenset(
    {
        FieldKind.HEADER,
        FieldKind.CELL,
        FieldKind.JSON_KEY,
        FieldKind.JSON_STRING,
        FieldKind.TEXT,
        FieldKind.FILENAME,
        FieldKind.BASE64_TEXT,
    }
)


@dataclass(frozen=True, slots=True)
class SourceFile:
    rel: str  # POSIX path relative to the input root; may itself be PII
    sha256: str
    size: int
    ext: str  # lower-cased suffix, e.g. ".csv" (may disagree with ``format``)
    format: Format
    encoding: str | None  # utf-8 | utf-8-sig | utf-16-le | utf-16-be | cp1252
    delimiter: str | None = None  # CSV/TSV only
    extension_mismatch: bool = False

    def __repr__(self) -> str:
        return (
            f"SourceFile(format={self.format.value}, encoding={self.encoding}, size={self.size}, "
            f"mismatch={self.extension_mismatch})"
        )


@dataclass(frozen=True, slots=True)
class Base64Segment:
    """A base64 payload inside a parent string field: ``value[start:end]``."""

    start: int
    end: int
    child: str  # address of the BASE64_TEXT field holding the decoded text
    encoding: str  # text encoding of the decoded bytes (needed to re-encode)
    padded: bool  # whether the original carried ``=`` padding
    declared_type: str | None  # e.g. Attachment.contentType, when declared
    withheld: bool = False  # binary payload: removed from the release (no child field)
    urlsafe: bool = False  # URL-safe alphabet: re-encoded with ``-``/``_``

    def __repr__(self) -> str:
        return f"Base64Segment(span={self.start}:{self.end}, declared={self.declared_type}, withheld={self.withheld})"


@dataclass(frozen=True, slots=True)
class FhirContext:
    resource_type: str | None  # e.g. "Patient"; None for Bundle-level elements
    entry: int | None  # Bundle entry index
    element: str  # resource-relative element path, e.g. "Patient.identifier.value"
    role: str | None  # reference | identifier | meta_source | narrative | attachment | date | name | telecom | address


@dataclass(slots=True)
class Field:
    address: str  # unique within the document: "row:3/2", "/entry/0/resource/id", "doc", "@header/1"…
    path: tuple[Any, ...]  # structural path into ``Document.native``
    record: str  # owning record locator: row:N | JSON pointer | doc | @file | @header | @filename
    channel: Channel
    kind: FieldKind
    value: Any = field(repr=False)  # ORIGINAL VALUE: never log
    label: str | None = field(default=None, repr=False)  # column header / member key naming this value
    parent: str | None = None  # BASE64_TEXT: address of the field the payload sits in
    fhir: FhirContext | None = None
    segments: tuple[Base64Segment, ...] = ()


@dataclass(frozen=True, slots=True)
class FhirEntry:
    index: int
    pointer: str
    full_url: str | None = field(repr=False)
    resource_type: str | None
    resource_id: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class FhirReference:
    pointer: str  # JSON pointer of the ``reference`` string
    value: str = field(repr=False)
    source_entry: int | None
    target_entry: int | None  # None: unresolved inside the Bundle (or contained/absolute)
    contained: bool = False


@dataclass(slots=True)
class FhirIndex:
    is_bundle: bool
    entries: list[FhirEntry]
    references: list[FhirReference]

    @property
    def unresolved(self) -> list[FhirReference]:
        return [r for r in self.references if r.target_entry is None and not r.contained]


@dataclass(slots=True)
class Document:
    source: SourceFile
    records: list[str]
    fields: list[Field]
    native: Any = field(repr=False)
    fhir: FhirIndex | None = None

    def iter_fields(self, *, channel: Channel | None = None, kind: FieldKind | None = None) -> Iterator[Field]:
        for f in self.fields:
            if (channel is None or f.channel is channel) and (kind is None or f.kind is kind):
                yield f

    def get_field(self, address: str) -> Field:
        for f in self.fields:
            if f.address == address:
                return f
        raise KeyError("no such field address")
