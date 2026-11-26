"""Where a value lives in a source file (mirrors the evaluator's ``channel`` notion)."""

from __future__ import annotations

from enum import Enum


class Channel(str, Enum):
    CONTENT = "content"  # ordinary values: CSV cells, JSON values, note text, FHIR narrative
    FILENAME = "filename"  # components of the input's relative path
    HEADER = "header"  # CSV/TSV header cells
    KEY = "key"  # JSON object keys
    METADATA = "metadata"  # export metadata (``_export_meta``…), FHIR ``meta``
    BASE64 = "base64"  # text decoded from a base64 payload
