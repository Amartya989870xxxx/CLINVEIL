"""File-signature (magic byte) detection for formats CLINVEIL does not parse."""

from __future__ import annotations

from clinveil.models.document import Format

# (signature, format). Checked at the very start of the file (after a UTF-8 BOM, if any).
_SIGNATURES: tuple[tuple[bytes, Format], ...] = (
    (b"%PDF-", Format.PDF),
    (b"\xff\xd8\xff", Format.JPEG),
    (b"\x89PNG\r\n\x1a\n", Format.PNG),
    (b"GIF87a", Format.GIF),
    (b"GIF89a", Format.GIF),
    (b"PK\x03\x04", Format.ZIP),  # also docx/xlsx/odt
    (b"PK\x05\x06", Format.ZIP),
    (b"\x1f\x8b", Format.GZIP),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", Format.BINARY),  # OLE2: legacy .doc/.xls
    (b"\x7fELF", Format.BINARY),
    (b"MZ\x90\x00", Format.BINARY),  # Windows PE
    (b"7z\xbc\xaf\x27\x1c", Format.ZIP),
    (b"Rar!\x1a\x07", Format.ZIP),
)

REASON_FOR_FORMAT = {
    Format.PDF: "unsupported_pdf",
    Format.JPEG: "unsupported_image",
    Format.PNG: "unsupported_image",
    Format.GIF: "unsupported_image",
    Format.ZIP: "unsupported_archive",
    Format.GZIP: "unsupported_archive",
    Format.BINARY: "unsupported_binary",
    Format.XML: "unsupported_xml",
}


def binary_signature(raw: bytes) -> Format | None:
    head = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    for sig, fmt in _SIGNATURES:
        if head.startswith(sig):
            return fmt
    return None
