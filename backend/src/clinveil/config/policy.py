# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Privacy policy loading.

The file format is the starter's flat ``key: value`` subset of YAML, parsed without
PyYAML so the runtime keeps zero third-party dependencies. Unknown keys are kept
in ``Policy.extra`` so new settings can be added without changing the parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _parse_flat_yaml(text: str) -> dict[str, int | str]:
    """Starter-compatible reader: ``key: value`` lines, ``#`` comments, ints coerced."""
    out: dict[str, int | str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = (x.strip() for x in line.split(":", 1))
            out[k] = int(v) if v.lstrip("-").isdigit() else v
    return out


@dataclass(frozen=True)
class Policy:
    age_band_years: int = 5
    date_shift_max_days: int = 180
    min_group_size: int = 5
    # Files larger than this are quarantined unread (hash is streamed). 256 MiB keeps
    # one in-memory copy well inside the 4 GB process-tree budget.
    max_file_bytes: int = 256 * 1024 * 1024
    # JSON safety limits: larger, deeper or bigger trees are quarantined with a reason code.
    max_json_bytes: int = 64 * 1024 * 1024
    max_json_depth: int = 64
    max_json_nodes: int = 2_000_000
    # Decoded size cap for one base64 attachment.
    max_attachment_bytes: int = 16 * 1024 * 1024
    extra: dict[str, int | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.age_band_years < 1:
            raise ValueError("policy.age_band_years must be >= 1")
        if self.date_shift_max_days < 1:
            raise ValueError("policy.date_shift_max_days must be >= 1")
        for name in ("max_file_bytes", "max_json_bytes", "max_json_depth", "max_json_nodes", "max_attachment_bytes"):
            if getattr(self, name) < 1:
                raise ValueError(f"policy.{name} must be >= 1")


_KNOWN = (
    "age_band_years",
    "date_shift_max_days",
    "min_group_size",
    "max_file_bytes",
    "max_json_bytes",
    "max_json_depth",
    "max_json_nodes",
    "max_attachment_bytes",
)


def load_policy(path: Path | None) -> Policy:
    """Load the policy; a missing file yields the defaults (starter behaviour)."""
    raw: dict[str, int | str] = {}
    if path is not None and path.is_file():
        raw = _parse_flat_yaml(path.read_text(encoding="utf-8"))
    known = {k: int(raw[k]) for k in _KNOWN if k in raw}
    extra = {k: v for k, v in raw.items() if k not in _KNOWN}
    return Policy(**known, extra=extra)
