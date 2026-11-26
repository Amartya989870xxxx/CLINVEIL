# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Per-format processors (starter-equivalent behaviour, modular form).

Each processor returns the sanitised text plus the record references for that
file. The pipeline only keeps the references if the file is actually exported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from clinveil.detection import baseline_regex
from clinveil.linking.linker import link_record
from clinveil.models.records import RecordRef
from clinveil.parsing import csv_format, json_format
from clinveil.privacy.pseudonym import Pseudonymizer


@dataclass
class RunStats:
    identifiers: int = 0
    generalized: int = 0
    suppressed: int = 0


class Sanitizer:
    def __init__(self, pseudonymizer: Pseudonymizer, stats: RunStats) -> None:
        self._psn = pseudonymizer
        self.stats = stats

    # ------------------------------------------------------------------ primitives
    def clean_text(self, text: str) -> str:
        text, n = baseline_regex.redact(text)
        self.stats.identifiers += n
        return text

    def clean_value(self, v: Any) -> Any:
        if isinstance(v, str):
            return self.clean_text(v)
        if isinstance(v, list):
            return [self.clean_value(x) for x in v]
        if isinstance(v, dict):
            # JSON keys can be PII too (e.g. an index keyed by patient name or UHID)
            return {self.clean_text(k): self.clean_value(x) for k, x in v.items()}
        return v  # numbers, booleans and null keep their type

    def _pid(self, record_text: str) -> str | None:
        key = link_record(record_text)
        return self._psn.pseudonym(key) if key else None

    # ------------------------------------------------------------------ formats
    def process_csv(self, text: str, delimiter: str, out_rel: str) -> tuple[str, list[RecordRef]]:
        rows = csv_format.read_rows(text, delimiter)
        if not rows:
            return "", []
        header, body = rows[0], rows[1:]
        refs: list[RecordRef] = []
        cleaned: list[list[str]] = []
        for i, row in enumerate(body):
            pid = self._pid(delimiter.join(row))
            # TODO(phase3): write pid into the row's patient column so it appears INSIDE the record
            cleaned.append([self.clean_text(c) for c in row])
            refs.append(RecordRef(file=f"sanitized/{out_rel}", loc=f"row:{i}", patient=pid))
        # TODO(phase2): rename a header only if it contains PII
        return csv_format.write_rows(header, cleaned, delimiter), refs

    def process_json(self, text: str, out_rel: str) -> tuple[str, list[RecordRef]]:
        data = json.loads(text)
        refs = [
            RecordRef(file=f"sanitized/{out_rel}", loc=loc, patient=None) for loc in json_format.record_locators(data)
        ]
        # TODO(phase1/5): FHIR must stay a valid R4 Bundle whose references resolve
        return json_format.dumps(self.clean_value(data)), refs

    def process_text(self, text: str, out_rel: str) -> tuple[str, list[RecordRef]]:
        refs = [RecordRef(file=f"sanitized/{out_rel}", loc="doc", patient=None)]
        return self.clean_text(text), refs
