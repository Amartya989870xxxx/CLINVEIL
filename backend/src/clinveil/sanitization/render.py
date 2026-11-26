"""Rebuild a file from its IR plus per-field replacements (``address -> new value``).

Renderers preserve structure: CSV keeps delimiter, header width and row count;
JSON keeps key order, value types and nesting; text is replaced whole. A field
absent from ``replacements`` keeps its original value, so an empty mapping
reproduces the parsed input (in normalised CSV/JSON form).
"""

from __future__ import annotations

from typing import Any

from clinveil.models.document import Document, Format
from clinveil.parsing import csv_format, json_format


def render(doc: Document, replacements: dict[str, Any]) -> str:
    fmt = doc.source.format
    if fmt in (Format.CSV, Format.TSV):
        return _render_delimited(doc, replacements)
    if fmt in (Format.JSON, Format.FHIR):
        return json_format.dumps(_rebuild(doc.native, (), replacements))
    if fmt is Format.TEXT:
        return replacements.get("doc", doc.native)
    raise ValueError("unsupported format for rendering")


def _render_delimited(doc: Document, repl: dict[str, Any]) -> str:
    rows: list[list[str]] = doc.native
    if not rows:
        return ""
    header = [repl.get(f"@header/{c}", v) for c, v in enumerate(rows[0])]
    body = [[repl.get(f"row:{i}/{c}", v) for c, v in enumerate(row)] for i, row in enumerate(rows[1:])]
    return csv_format.write_rows(header, body, doc.source.delimiter or ",")


def _unique_key(key: str, taken: dict[str, Any]) -> str:
    """Two keys renamed to the same text must not silently overwrite each other."""
    n = 2
    while f"{key}~{n}" in taken:
        n += 1
    return f"{key}~{n}"


def _rebuild(node: Any, path: tuple[Any, ...], repl: dict[str, Any]) -> Any:
    # Recursion depth is bounded by IngestLimits.max_json_depth (checked before parsing).
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            p = (*path, k)
            nk = repl.get(json_format.pointer(p) + "#key", k)
            if nk in out:
                nk = _unique_key(nk, out)
            out[nk] = _rebuild(v, p, repl)
        return out
    if isinstance(node, list):
        return [_rebuild(v, (*path, i), repl) for i, v in enumerate(node)]
    if isinstance(node, str):
        return repl.get(json_format.pointer(path), node)
    return node
