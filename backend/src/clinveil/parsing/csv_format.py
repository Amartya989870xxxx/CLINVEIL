"""CSV/TSV read/write that preserves delimiter and header (starter-equivalent)."""

from __future__ import annotations

import csv
import io


def read_rows(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


def write_rows(header: list[str], body: list[list[str]], delimiter: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(header)
    w.writerows(body)
    return buf.getvalue()


def delimiter_for(ext: str) -> str:
    return "\t" if ext == ".tsv" else ","
