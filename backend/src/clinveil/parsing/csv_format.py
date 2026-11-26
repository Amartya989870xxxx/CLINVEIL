# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""CSV/TSV read/write that preserves delimiter and header, plus delimiter sniffing.

Sniffing is deliberately conservative: the extension's delimiter is kept whenever
it yields a multi-column header; only a single-column result triggers a search
for another delimiter that gives a consistent table (for example tab-separated
content in a ``.csv`` file).
"""

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


CANDIDATE_DELIMITERS = (",", "\t", ";", "|")
_SNIFF_ROWS = 50


def table_shape(text: str, delimiter: str) -> tuple[int, float, int]:
    """(header width, share of the first rows with exactly that width, rows sampled)."""
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)):
        if i >= _SNIFF_ROWS:
            break
        rows.append(len(row))
    if not rows:
        return 0, 0.0, 0
    width = rows[0]
    return width, sum(n == width for n in rows) / len(rows), len(rows)


def sniff_delimiter(text: str, default: str) -> str:
    try:
        width, _, _ = table_shape(text, default)
        if width >= 2:
            return default
        best, best_score = default, 0.0
        for d in CANDIDATE_DELIMITERS:
            if d == default:
                continue
            w, consistency, n = table_shape(text, d)
            if w >= 2 and n >= 2 and consistency > best_score:
                best, best_score = d, consistency
        return best if best_score >= 0.8 else default
    except csv.Error:
        return default
