# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Structured-identifier detectors with validation (no single generic digit regex).

All patterns run on ``text.translate(DEVANAGARI_DIGITS)``, a length-preserving
translation, so offsets are valid in the original string and Devanagari digits
(``९८७६५४३२१०``) are matched like ASCII digits.

Confidence semantics:
  0.97  validated structure + explicit label (``Aadhaar: 2345 6789 0123`` with Verhoeff)
  0.95  unambiguous structure (grouped Aadhaar, ABHA 2-4-4-4, PAN, e-mail, masked Aadhaar)
  0.90  Indian mobile number in any common format; labelled hospital identifiers
  0.80  12-digit run that fails Verhoeff (still redacted: not a clinical shape)
  0.60  ID-shaped tokens without a label (reported, not redacted unless confirmed elsewhere)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from clinveil.detection.text import DEVANAGARI_DIGITS
from clinveil.models.findings import EntityType

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 7, 6, 8, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(digits: str) -> bool:
    """Verhoeff checksum (used by UIDAI for the 12th Aadhaar digit)."""
    if not digits.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


@dataclass(frozen=True, slots=True)
class Hit:
    start: int
    end: int
    entity: EntityType
    confidence: float
    detector: str

    def __repr__(self) -> str:
        return f"Hit({self.entity.value}, {self.start}:{self.end}, {self.confidence})"


_B = r"(?<![0-9A-Za-z])"  # left boundary: not inside a longer alphanumeric run
_E = r"(?![0-9A-Za-z])"
_SEP = r"[ .\-‐-―]"

PHONE_RE = re.compile(
    _B + r"(?:(?:\+|00)\s?91" + _SEP + r"?|91" + _SEP + r"|\(?0\)?" + _SEP + r"?)?"
    r"(?:[6-9]\d{9}|[6-9]\d{4}" + _SEP + r"\d{5}|[6-9]\d{2}" + _SEP + r"\d{3}" + _SEP + r"\d{4}|"
    r"[6-9]\d{3}" + _SEP + r"\d{3}" + _SEP + r"\d{3}|\([6-9]\d{2,4}\)\s?\d{5,7}|[6-9]\d{4}\d{5})" + _E
)
AADHAAR_RE = re.compile(_B + r"[2-9]\d{3}(?P<s1>[ \-]?)\d{4}(?P=s1)\d{4}" + _E)
AADHAAR_MASKED_RE = re.compile(r"(?i)" + _B + r"(?:[x*•]{4}[ \-]?[x*•]{4}[ \-]?\d{4}|[x*•]{8}\d{4})" + _E)
ABHA_NUMBER_RE = re.compile(_B + r"\d{2}[ \-]\d{4}[ \-]\d{4}[ \-]\d{4}" + _E)
#: A labelled ABHA number may also be written as 14 contiguous digits.
ABHA_LABEL_RE = re.compile(
    r"(?i)(?:\bABHA(?:\s*(?:No|Number|ID|#))?|\bHealth\s*ID(?:\s*(?:No|Number))?|\bPHR\s*ID|आभा)\.?"
    r"\s*[:#.\-]?\s*(?P<id>\d{14}|\d{2}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4})" + _E
)
#: Landlines with an STD code: ``0522-2234567``, ``(0522) 2234567``, ``011-23456789``.
LANDLINE_RE = re.compile(_B + r"(?:\(0\d{2,4}\)\s?|0\d{2,4}[ \-])\d{6,8}" + _E)
_LANDLINE_LABEL_RE = re.compile(
    r"(?i)\b(?:landline|ph(?:one)?|tel(?:ephone)?|contact|std|office|resi(?:dence)?)\b\.?\s*[:\-#]?\s*$"
)
_AADHAAR_LABEL_RE = re.compile(r"(?i)(?:aadh?aa?r|adhaa?r|\buid\b|uidai|आधार)[^\n]{0,24}$")
_NON_PII_NUMBER_RE = re.compile(
    r"(?i)\b(?:serial|s\.?\s*no|batch|lot|sample|specimen|invoice|bill|order|txn|transaction|barcode|accession|"
    r"ref(?:erence)?|receipt|ticket|token|claim|imei|device|model)\b[^\n]{0,12}$"
)
ABHA_ADDRESS_RE = re.compile(r"(?i)(?<![\w.])[a-z0-9][a-z0-9._]{2,}@(?:abdm|sbx|ndhm)(?![\w.])")
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![\w-])")
PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z](?![A-Za-z0-9])")
INSURANCE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:PMJAY[-/ ]?[A-Z]{2}[-/ ]?\d{6,12}|(?:POL|PLY|POLICY)[-/ ]?\d{2,4}[-/ ]?\d{5,12}|"
    r"(?:ESIC?|CGHS)[-/ ]?\d{6,14})(?![A-Za-z0-9])"
)
#: Hospital admission / registration numbers whose prefix itself says "patient record".
MRN_STRONG_SHAPE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:UHID|MRN|CRN|IPD|IP|ADM)[-/ ]?(?:\d{2,4}[-/])?\d{4,8}(?![A-Za-z0-9])"
)
#: Generic "LETTERS/YY/NNNNNN"-style tokens: reported with low confidence only.
ID_SHAPE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,6}(?:[-/]?\d{2,4})?[-/]\d{4,8}(?![A-Za-z0-9])")
_ID_VALUE = r"[A-Za-z]{0,8}[-/ ]?(?:[A-Za-z0-9]+[-/])*[A-Za-z]*\d[A-Za-z0-9]*"
MRN_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:UHID|MRN|CRN|CR\s*No|Reg(?:istration)?\.?\s*(?:No|Number|#)|IPD\s*(?:No|Number|#)|"
    r"IP\s*No|Patient\s*(?:ID|No)|Hosp(?:ital)?\.?\s*(?:No|ID)|Adm(?:ission)?\.?\s*No|Case\s*No|"
    r"Record\s*No)\b|पंजीकरण\s*सं\.?|आईपीडी\s*सं\.?|यूएचआईडी)\s*[:#.\-]?\s*(?P<id>" + _ID_VALUE + ")"
)
PHONE_LABEL_RE = re.compile(
    r"(?i)\b(?:mob(?:ile)?|ph(?:one)?|tel|contact|call|whatsapp|callback|cell)\b\.?\s*[:\-#]?\s*$"
)


def _scan(text: str) -> str:
    """Length-preserving: any-script digits -> ASCII (offsets stay valid on ``text``)."""
    return text.translate(DEVANAGARI_DIGITS)


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def find_identifiers(text: str) -> Iterator[Hit]:
    """All validated identifier hits in ``text`` (overlaps are resolved later)."""
    s = _scan(text)
    for m in ABHA_ADDRESS_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.ABHA_ADDRESS, 0.95, "abha_address")
    for m in EMAIL_RE.finditer(s):
        if not ABHA_ADDRESS_RE.fullmatch(m.group()):
            yield Hit(m.start(), m.end(), EntityType.EMAIL, 0.95, "email")
    for m in ABHA_NUMBER_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.ABHA_NUMBER, 0.95, "abha_number")
    for m in ABHA_LABEL_RE.finditer(s):
        yield Hit(m.start("id"), m.end("id"), EntityType.ABHA_NUMBER, 0.96, "abha_number")
    for m in AADHAAR_MASKED_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.AADHAAR_MASKED, 0.95, "aadhaar_masked")
    for m in AADHAAR_RE.finditer(s):
        d = _digits(m.group())
        grouped = bool(m.group("s1"))
        before = s[max(0, m.start() - 40) : m.start()]
        labelled = bool(_AADHAAR_LABEL_RE.search(before))
        if verhoeff_valid(d):
            if not labelled and not grouped and _NON_PII_NUMBER_RE.search(before):
                continue  # "Serial 2938…": a checksum-valid run that is explicitly another number
            conf = 0.97
        elif grouped or labelled:
            conf = 0.92
        else:
            continue  # 12 contiguous digits, no checksum, no label: not evidence of an Aadhaar
        yield Hit(m.start(), m.end(), EntityType.AADHAAR, conf, "aadhaar")
    for m in PHONE_RE.finditer(s):
        d = _digits(m.group())
        if len(d) == 12 and d.startswith("91") and AADHAAR_RE.fullmatch(m.group()) and verhoeff_valid(d):
            continue  # a checksum-valid 12-digit run starting 91 is more likely an Aadhaar
        conf = 0.95 if PHONE_LABEL_RE.search(s[max(0, m.start() - 16) : m.start()]) else 0.9
        yield Hit(m.start(), m.end(), EntityType.PHONE, conf, "phone")
    for m in LANDLINE_RE.finditer(s):
        labelled = _LANDLINE_LABEL_RE.search(s[max(0, m.start() - 16) : m.start()])
        yield Hit(m.start(), m.end(), EntityType.PHONE, 0.92 if labelled else 0.75, "landline")
    for m in PAN_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.PAN, 0.95, "pan")
    for m in INSURANCE_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.INSURANCE_ID, 0.9, "insurance")
    for m in MRN_LABEL_RE.finditer(s):
        yield Hit(m.start("id"), m.end("id"), EntityType.MRN, 0.92, "mrn_label")
    for m in MRN_STRONG_SHAPE_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.MRN, 0.85, "mrn_shape")
    for m in ID_SHAPE_RE.finditer(s):
        yield Hit(m.start(), m.end(), EntityType.MRN, 0.6, "id_shape")


def mrn_digit_core(value: str) -> str:
    """The last maximal digit run of an identifier (``TST/26/000101`` -> ``000101``)."""
    runs = re.findall(r"\d+", _scan(value))
    return runs[-1] if runs else ""
