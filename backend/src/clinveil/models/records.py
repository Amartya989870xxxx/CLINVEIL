"""``records.jsonl`` line model (SPEC §6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecordRef:
    file: str  # output path relative to {output}, e.g. "sanitized/opd/x.json"
    loc: str  # INPUT locator: "row:N", RFC 6901 pointer, or "doc"
    patient: str | None  # pseudonym, or None when deliberately unlinked
    out: str | None = None  # output locator, only if it differs from loc
    status: str | None = None  # optional: sanitized | generalized | suppressed

    def to_json_obj(self) -> dict:
        obj: dict = {"file": self.file, "loc": self.loc, "patient": self.patient}
        if self.out is not None:
            obj["out"] = self.out
        if self.status is not None:
            obj["status"] = self.status
        return obj
