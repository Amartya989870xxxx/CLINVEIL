"""Clinical-context protection: spans that must survive sanitisation.

Each pattern yields a ``KeepSpan``. Weak and contextual person-name findings that
overlap a keep span are discarded (``Dr. Ramesh``, ``Parkinson's disease``,
``Jeevan Jyoti Hospital``, ``ASHA worker``). Validated identifiers (phones,
Aadhaar…) are not blocked by clinical spans, because they cannot be confused
with a dose or a vital sign. Doctor spans block *every* name finding, including
propagated ones.

The patterns are deliberately structural (titles, units, dose grammar,
eponym grammar) rather than an unbounded whitelist, so they cannot be used to
smuggle a patient identifier through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from clinveil.detection.lexicon import COMPLAINT_WORDS, DISEASE_WORDS, DRUG_WORDS, EPONYM_HEADS


@dataclass(frozen=True, slots=True)
class KeepSpan:
    start: int
    end: int
    kind: str  # doctor | organization | medication | dose | frequency | vital | lab | diagnosis | complaint | ...

    def __repr__(self) -> str:
        return f"KeepSpan({self.kind}, {self.start}:{self.end})"


_CAP = r"[A-Z][A-Za-z'.\-]*"
_NAMEPART = r"(?:[A-Z][a-z'\-]+|[A-Z]{2,}|[A-Z]\.)"
_DEVA_WORD = r"[ऀ-ॣॱ-ॿ‌‍]+"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # clinicians: "Dr. Ramesh", "Dr Kelvar Dunmore (MD Medicine)", "डॉ. रमेश"
    ("doctor", re.compile(r"\b(?:Dr|DR|Doctor|Prof)\.?\s*" + _NAMEPART + r"(?:\s+" + _NAMEPART + r"){0,3}")),
    ("doctor", re.compile(r"(?:डॉ|डा)\.?\s*" + _DEVA_WORD + r"(?:\s+" + _DEVA_WORD + r")?")),
    # organisations: "... Hospital", "... Pathology", "*Lifeline Pathology*", "Arogya Seva Sadan"
    (
        "organization",
        re.compile(
            r"\b(?:[A-Z][\w'&.-]*\s+){1,5}(?i:hospital|clinic|nursing\s+home|medical\s+college|multispeciality|"
            r"multi-speciality|labs?|laboratory|pathology|diagnostics?|sadan|charitable|health\s+cent(?:re|er)|"
            r"dispensary|trust|foundation|imaging|scans?)\b"
        ),
    ),
    ("organization", re.compile(r"\b(?:PHC|CHC|AIIMS|ESIC|CGHS)\b(?:\s+[A-Z][a-z]+)?")),
    # community health workers (the "asha" meaning trap): upper-case ASHA, not the name Asha
    ("asha", re.compile(r"\bASHA\b(?:\s+(?:workers?|didi|sahyogini|sahyogi))?")),
    # hospital wards and beds (the "hospital-ward" trap), not address wards
    ("ward", re.compile(r"(?i)\bWard\s+(?:No\.?\s*)?\d+\s*\([A-Za-z &/-]+\)|\bWard/Bed\b|\bBed\s*(?:No\.?\s*)?\d+\b")),
    (
        "ward",
        re.compile(
            r"(?i)\b(?:Medical|Surgical|Maternity|Paediatric|Pediatric|General|Emergency|Isolation|"
            r"Ortho(?:paedic)?|Burns?)\s+Ward\b"
        ),
    ),
    # medication: route word + drug + optional strength
    (
        "medication",
        re.compile(
            r"(?i)\b(?:Tab|Tablet|Cap|Capsule|Inj|Injection|Syp|Syr|Syrup|Inh|Oint|Drops?|Susp|Sachet|Neb)\b\.?\s+"
            r"[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?(?:\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu|units?|%)\b)?"
        ),
    ),
    (
        "medication",
        re.compile(
            r"(?i)\b(?:" + "|".join(sorted(DRUG_WORDS, key=len, reverse=True)) + r")\b"
            r"(?:\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu|units?)?)?"
        ),
    ),
    ("dose", re.compile(r"(?i)\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|g|gm|ml|iu|units?|puffs?|tabs?)\b")),
    ("frequency", re.compile(r"(?<![\d/-])[0-2½](?:\s?-\s?[0-2½]){2,3}(?![\d/-])")),
    ("frequency", re.compile(r"\b(?:OD|BD|BID|TDS|TID|QID|HS|SOS|STAT|PRN|AC|PC)\b")),
    ("duration", re.compile(r"(?i)\bx\s?\d+\s?(?:days?|d|wks?|weeks?|months?|mths?|yrs?|years?)\b")),
    # vitals and labs
    ("vital", re.compile(r"(?i)\b(?:BP|B\.P\.?)\s*[:\-]?\s*\d{2,3}\s*/\s*\d{2,3}(?:\s*mm\s*Hg)?")),
    (
        "vital",
        re.compile(
            r"(?i)\b(?:pulse|PR|HR|RR|SpO2|SPO2|spo₂|temp(?:erature)?|weight|wt|height|ht|BMI|GCS)"
            r"\s*[:\-]?\s*\d+(?:\.\d+)?\s*(?:/min|bpm|%|°?\s?[FC]|kg|cm)?"
        ),
    ),
    (
        "lab",
        re.compile(
            r"(?i)\b\d+(?:\.\d+)?\s?(?:mg/dl|g/dl|mmol/l|meq/l|miu/l|µiu/ml|uiu/ml|iu/l|u/l|ng/ml|"
            r"pg/ml|fl|pg|cells/cumm|/cumm|lakh/cumm|x10\^\d+/l|%)"
        ),
    ),
    ("range", re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s?-\s?\d+(?:\.\d+)?(?![\d.])")),
    # diagnoses
    ("diagnosis", re.compile(r"\b[A-Z][a-z]+(?:'s|’s|s')\s+(?:" + "|".join(sorted(EPONYM_HEADS)) + r")\b")),
    ("diagnosis", re.compile(r"(?i)\b(?:" + "|".join(sorted(DISEASE_WORDS, key=len, reverse=True)) + r")\b")),
    ("icd", re.compile(r"(?<![A-Za-z0-9])[A-TV-Z]\d{2}(?:\.\d{1,2})?(?![A-Za-z0-9])")),
    ("loinc", re.compile(r"(?<![\d-])\d{3,5}-\d(?![\d-])")),
    # history / known-case-of / complaint phrases: K/C/O, H/O, and C/O + complaint (not "care of")
    ("history", re.compile(r"(?i)\b(?:K/C/O|H/O|No\s+H/O)\b[^.\n;]{0,80}")),
    (
        "complaint",
        re.compile(
            r"(?i)(?<![/\w])C/O\b\s*:?\s*(?:"
            + "|".join(sorted(COMPLAINT_WORDS, key=len, reverse=True))
            + r")\b[^.\n;]{0,80}"
        ),
    ),
]


def keep_spans(text: str) -> list[KeepSpan]:
    out: list[KeepSpan] = []
    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            if m.end() > m.start():
                out.append(KeepSpan(m.start(), m.end(), kind))
    return out


def doctor_spans(spans: list[KeepSpan]) -> list[KeepSpan]:
    return [s for s in spans if s.kind == "doctor"]
