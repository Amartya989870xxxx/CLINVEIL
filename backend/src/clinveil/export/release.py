"""Write the three release artefacts.

Byte-level formatting matches the starter exactly (``sort_keys`` records,
``indent=2`` ASCII-escaped report) so determinism and parity tests can compare
outputs byte for byte.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from clinveil.models.records import RecordRef
from clinveil.security.paths import safe_join

REPORT_SCHEMA = "raksha-report/1"


@dataclass
class FileEntry:
    input_sha256: str
    output: str | None = None
    status: str = "quarantined"
    reason: str | None = None

    def to_json_obj(self) -> dict:
        obj: dict = {"input_sha256": self.input_sha256}
        # key order mirrors the starter: input_sha256, output, status[, reason]
        obj["output"] = self.output
        obj["status"] = self.status
        if self.reason is not None:
            obj["reason"] = self.reason
        return obj


@dataclass
class ReleaseCounts:
    identifiers_detected: int = 0
    records_generalized: int = 0
    records_suppressed: int = 0
    records_quarantined: int = 0


def write_sanitized(sanitized_root: Path, out_rel: str, text: str) -> None:
    dest = safe_join(sanitized_root, out_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8", newline="")


def write_records(out_dir: Path, records: list[RecordRef]) -> None:
    with open(out_dir / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_json_obj(), ensure_ascii=False, sort_keys=True) + "\n")


def build_report(
    files: list[FileEntry], records: list[RecordRef], counts: ReleaseCounts, seconds: float, peak_rss_mb: float
) -> dict:
    n_san = sum(e.status == "sanitized" for e in files)
    return {
        "schema": REPORT_SCHEMA,
        "files": [e.to_json_obj() for e in files],
        "counts": {
            "files_total": len(files),
            "files_sanitized": n_san,
            "files_quarantined": len(files) - n_san,
            "records_processed": len(records),
            "identifiers_detected": counts.identifiers_detected,
            "records_linked": sum(r.patient is not None for r in records),
            "records_generalized": counts.records_generalized,
            "records_suppressed": counts.records_suppressed,
            "records_quarantined": counts.records_quarantined,
        },
        "timing": {"seconds": round(seconds, 2)},
        "resources": {"peak_rss_mb": peak_rss_mb},
    }


def write_report(out_dir: Path, report: dict) -> None:
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
