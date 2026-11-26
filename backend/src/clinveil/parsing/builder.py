"""Build the common IR (:class:`clinveil.models.document.Document`) from a detection.

Field addresses (unique per document):

=================  ==========================  =====================================
kind               address                     record
=================  ==========================  =====================================
CSV header cell    ``@header/<col>``           ``@header``
CSV data cell      ``row:<i>/<col>``           ``row:<i>``
JSON value         RFC 6901 pointer            enclosing ``/<key>/<i>`` record, or
                                               ``doc`` (single-document JSON/FHIR),
                                               or ``@file`` (outside any record)
JSON key           ``<pointer>#key``           ``@file``
text document      ``doc``                     ``doc``
filename part      ``@filename/<i>``           ``@filename``
base64 payload     ``<parent address>#b64/<n>`` the parent's record
=================  ==========================  =====================================

Channels: CSV headers -> ``header``; JSON keys -> ``key``; values inside a
``_``-prefixed member (export metadata) or a FHIR ``meta`` element ->
``metadata``; decoded payloads -> ``base64``; path parts -> ``filename``;
everything else -> ``content``. Metadata values belong to ``@file`` unless the
document is a single ``doc`` record.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from clinveil.ingestion.detect import Detection
from clinveil.ingestion.limits import IngestLimits
from clinveil.models.channels import Channel
from clinveil.models.document import (
    Base64Segment,
    Document,
    Field,
    FieldKind,
    Format,
    SourceFile,
)
from clinveil.parsing import attachments, csv_format, fhir, json_format


def build_document(rel: str, sha256: str, size: int, ext: str, det: Detection, limits: IngestLimits) -> Document:
    source = SourceFile(
        rel=rel,
        sha256=sha256,
        size=size,
        ext=ext,
        format=det.format,
        encoding=det.encoding,
        delimiter=det.delimiter,
        extension_mismatch=det.extension_mismatch,
    )
    if det.format in (Format.CSV, Format.TSV):
        doc = _build_delimited(source, det.text, det.delimiter or ",", limits)
    elif det.format in (Format.JSON, Format.FHIR):
        doc = _build_json(source, det.data, limits)
    elif det.format is Format.TEXT:
        doc = _build_text(source, det.text, limits)
    else:  # detect() never returns unsupported formats; guard anyway
        raise ValueError("unsupported format for IR")
    doc.fields.extend(_filename_fields(rel))
    return doc


# --------------------------------------------------------------------------- helpers
def _with_payloads(f: Field, payloads: list[attachments.Payload]) -> list[Field]:
    """Attach decoded base64 payloads to ``f`` as segments + BASE64_TEXT child fields."""
    if not payloads:
        return [f]
    segs, children = [], []
    for n, p in enumerate(payloads):
        child_addr = f"{f.address}#b64/{n}"
        segs.append(Base64Segment(p.start, p.end, child_addr, p.encoding, p.padded, p.declared_type))
        children.append(
            Field(
                address=child_addr,
                path=(*f.path, "#b64", n),
                record=f.record,
                channel=Channel.BASE64,
                kind=FieldKind.BASE64_TEXT,
                value=p.text,
                label=f.label,
                parent=f.address,
                fhir=f.fhir,
            )
        )
    f.segments = tuple(segs)
    return [f, *children]


def _filename_fields(rel: str) -> list[Field]:
    return [
        Field(
            address=f"@filename/{i}",
            path=("@filename", i),
            record="@filename",
            channel=Channel.FILENAME,
            kind=FieldKind.FILENAME,
            value=part,
        )
        for i, part in enumerate(rel.split("/"))
    ]


# --------------------------------------------------------------------------- formats
def _build_delimited(source: SourceFile, text: str, delimiter: str, limits: IngestLimits) -> Document:
    rows = csv_format.read_rows(text, delimiter)
    fields: list[Field] = []
    records: list[str] = []
    if rows:
        header = rows[0]
        for c, name in enumerate(header):
            fields.append(
                Field(
                    address=f"@header/{c}",
                    path=("header", c),
                    record="@header",
                    channel=Channel.HEADER,
                    kind=FieldKind.HEADER,
                    value=name,
                )
            )
        for i, row in enumerate(rows[1:]):
            loc = f"row:{i}"
            records.append(loc)
            for c, cell in enumerate(row):
                f = Field(
                    address=f"{loc}/{c}",
                    path=("row", i, c),
                    record=loc,
                    channel=Channel.CONTENT,
                    kind=FieldKind.CELL,
                    value=cell,
                    label=header[c] if c < len(header) else None,
                )
                fields.extend(_with_payloads(f, attachments.find_undeclared(cell, limits)))
    return Document(source=source, records=records, fields=fields, native=rows)


def _build_text(source: SourceFile, text: str, limits: IngestLimits) -> Document:
    f = Field(address="doc", path=(), record="doc", channel=Channel.CONTENT, kind=FieldKind.TEXT, value=text)
    return Document(
        source=source, records=["doc"], fields=_with_payloads(f, attachments.find_undeclared(text, limits)), native=text
    )


_SCALAR_KIND = {
    str: FieldKind.JSON_STRING,
    bool: FieldKind.JSON_BOOL,
    int: FieldKind.JSON_NUMBER,
    float: FieldKind.JSON_NUMBER,
    type(None): FieldKind.JSON_NULL,
}


def _build_json(source: SourceFile, data: Any, limits: IngestLimits) -> Document:
    records = json_format.record_locators(data)
    single = records == ["doc"]
    record_set = set(records)
    is_fhir = source.format is Format.FHIR
    root = data if isinstance(data, dict) else {}
    fields: list[Field] = []

    def record_of(path: tuple[Any, ...]) -> str:
        if single:
            return "doc"
        if len(path) >= 2:
            ptr = json_format.pointer(path[:2])
            if ptr in record_set:
                return ptr
        return "@file"

    # Iterative pre-order walk; depth is already bounded by json_safety.
    # Stack items: (node, path, in_metadata, label, declared_ctype_of_parent_object)
    stack: list[tuple[Any, tuple[Any, ...], bool, str | None, str | None]] = [(data, (), False, None, None)]
    while stack:
        node, path, meta, label, ctype = stack.pop()
        if isinstance(node, dict):
            obj_ctype = attachments.declared_type(node)
            children = []
            for k, v in node.items():
                p = (*path, k)
                child_meta = meta or k.startswith("_") or (is_fhir and k == "meta")
                # keys get the element context but no role: the key text is not the element's value
                ctx = replace(fhir.context_for(p, v, root), role=None) if is_fhir else None
                fields.append(
                    Field(
                        address=json_format.pointer(p) + "#key",
                        path=p,
                        record="@file",
                        channel=Channel.KEY,
                        kind=FieldKind.JSON_KEY,
                        value=k,
                        fhir=ctx,
                    )
                )
                children.append((v, p, child_meta, k, obj_ctype))
            stack.extend(reversed(children))
        elif isinstance(node, list):
            stack.extend(reversed([(v, (*path, i), meta, label, None) for i, v in enumerate(node)]))
        else:
            channel = Channel.METADATA if meta else Channel.CONTENT
            record = record_of(path)
            if meta and not single:
                record = "@file"
            f = Field(
                address=json_format.pointer(path),
                path=path,
                record=record,
                channel=channel,
                kind=_SCALAR_KIND[type(node)],
                value=node,
                label=label,
                fhir=fhir.context_for(path, node, root) if is_fhir else None,
            )
            if isinstance(node, str):
                payloads: list[attachments.Payload] = []
                if ctype is not None and label is not None and attachments.is_declared_data_key(label):
                    declared = attachments.decode_declared(node, ctype, limits)
                    payloads = [declared] if declared else attachments.find_undeclared(node, limits)
                else:
                    payloads = attachments.find_undeclared(node, limits)
                fields.extend(_with_payloads(f, payloads))
            else:
                fields.append(f)
    return Document(
        source=source, records=records, fields=fields, native=data, fhir=fhir.build_index(root) if is_fhir else None
    )
