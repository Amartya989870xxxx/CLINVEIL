"""Explicit resource limits for ingestion (all derived from the policy file)."""

from __future__ import annotations

from dataclasses import dataclass

from clinveil.config.policy import Policy


@dataclass(frozen=True, slots=True)
class IngestLimits:
    max_file_bytes: int = 256 * 1024 * 1024
    max_json_bytes: int = 64 * 1024 * 1024  # a parsed JSON tree costs roughly 10x its text in RAM
    max_json_depth: int = 64  # practice data peaks at 11 (FHIR); the trap file is 1,502
    max_json_nodes: int = 2_000_000
    max_attachment_bytes: int = 16 * 1024 * 1024  # decoded size of one base64 payload

    @classmethod
    def from_policy(cls, p: Policy) -> IngestLimits:
        return cls(
            max_file_bytes=p.max_file_bytes,
            max_json_bytes=p.max_json_bytes,
            max_json_depth=p.max_json_depth,
            max_json_nodes=p.max_json_nodes,
            max_attachment_bytes=p.max_attachment_bytes,
        )
