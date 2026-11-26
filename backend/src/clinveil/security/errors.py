# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""PII-free failure reasons.

Quarantine reasons go into ``report.json``, which is part of the release and is
scanned for PII. Only reason codes from the allowlist below, or an exception's
*type name*, may ever be written; exception messages are never used because they
can echo record content (``ValueError("invalid literal ... '<name>'")``).
"""

from __future__ import annotations

REASON_CODES = frozenset(
    {
        # filesystem guards
        "symlink_outside_input",
        "not_a_regular_file",
        "file_too_large",
        # content detection
        "empty_file",
        "unsupported_pdf",
        "unsupported_image",
        "unsupported_archive",
        "unsupported_binary",
        "unsupported_xml",
        # text decoding
        "undecodable_text",
        "implausible_text",
        # JSON safety
        "invalid_json",
        "json_too_deep",
        "json_too_large",
        # base64 attachments
        "invalid_attachment",
        "unsupported_attachment",
        "attachment_too_large",
        # legacy generic code (kept so older reports stay valid; no longer emitted)
        "unsupported_format",
    }
)


class QuarantineError(Exception):
    """Raised to quarantine a file with a fixed, content-free reason code."""

    def __init__(self, code: str) -> None:
        if code not in REASON_CODES:
            raise ValueError("unknown quarantine reason code")
        super().__init__(code)
        self.code = code


def safe_reason(exc: BaseException) -> str:
    if isinstance(exc, QuarantineError):
        return exc.code
    return type(exc).__name__
