"""Phase 4 value transformations for STRUCTURED fields (per-field semantics from detection).

* :func:`shift_date_text`: moves every date in a clinical/admin date value by a fixed number of days,
  keeping the value's own notation (``2024-03-07``, ``07/03/2024``, ``07-Mar-2024``, FHIR ``dateTime``
  with its time and zone). Anything that does not parse as a real calendar date is left as written.
* :func:`band_age_text`: ``"47"`` / ``"47 yrs"`` -> ``"45-49"`` (the band always contains the age).
  Values that are not a plain age in years (``"6 months"``, ``"unknown"``) are left unchanged.
* :func:`pin_prefix`: a 6-digit Indian PIN -> its true 3-digit prefix + ``XXX`` (``110XXX``).

The offset is chosen by the caller: the keyed per-patient shift for a linked record, or a keyed
per-record shift when identity is not established, so uncertain records never share a patient offset.
"""

from __future__ import annotations

import datetime as dt
import re

from clinveil.privacy.generalize import age_band

_MONTHS = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}
_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ISO: 2024-03-07 (optionally followed by T.. time, kept verbatim)
_ISO = re.compile(r"(?<![\d])(\d{4})-(\d{2})-(\d{2})(?![\d])")
# Day-first numeric: 07/03/2024, 7-3-2024, 07.03.2024 (Indian convention: day first)
_DMY = re.compile(r"(?<![\d/.\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})(?![\d])")
# 07-Mar-2024, 7 Mar 2024, 07 March 2024
_DMONY = re.compile(r"(?<![\w])(\d{1,2})([ \-])([A-Za-z]{3,9})\2(\d{4})(?![\d])")


def _mk(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


AMBIGUOUS_DATE = "[DATE]"


def numeric_date_order_evidence(value: str) -> tuple[bool, bool]:
    """``(day_first_seen, month_first_seen)`` from numeric dates whose day is > 12 (unambiguous)."""
    dmy_seen = mdy_seen = False
    for m in _DMY.finditer(value or ""):
        a, b = int(m.group(1)), int(m.group(3))
        if a > 12 and b <= 12:
            dmy_seen = True
        elif b > 12 and a <= 12:
            mdy_seen = True
    return dmy_seen, mdy_seen


def shift_date_text(value: str, days: int, order: str | None = "dmy") -> str | None:
    """Shift every parseable full date in ``value`` by ``days``; ``None`` if nothing changed.

    ``order`` resolves numeric dates whose day and month are both <= 12: ``"dmy"`` (day first), ``"mdy"``
    (month first) or ``None`` (unknown: an ambiguous date becomes ``[DATE]``, never guessed or kept). A numeric date
    with a component > 12 is unambiguous and is always read correctly. ISO and month-name dates are unambiguous.
    """
    if not value or days == 0:
        return None
    delta = dt.timedelta(days=days)
    changed = False

    def iso(m: re.Match[str]) -> str:
        nonlocal changed
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d is None:
            return m.group(0)
        n = d + delta
        changed = True
        return f"{n.year:04d}-{n.month:02d}-{n.day:02d}"

    def dmy(m: re.Match[str]) -> str:
        nonlocal changed
        a, sep, b, y = m.group(1), m.group(2), m.group(3), m.group(4)
        ia, ib = int(a), int(b)
        if ia > 12:
            month_first = False
        elif ib > 12:
            month_first = True
        elif order in ("dmy", "mdy"):
            month_first = order == "mdy"
        else:
            # Unknown order: never guess. Every date whose day and month are both <= 12 (even 05/05) is SUPPRESSED,
            # so no exact clinical date survives and no wrongly-ordered shift is published.
            changed = True
            return AMBIGUOUS_DATE
        d = _mk(int(y), ia, ib) if month_first else _mk(int(y), ib, ia)
        if d is None:
            return m.group(0)
        n = d + delta
        changed = True
        first, second = (n.month, n.day) if month_first else (n.day, n.month)
        f1 = f"{first:02d}" if len(a) == 2 else str(first)
        f2 = f"{second:02d}" if len(b) == 2 else str(second)
        return f"{f1}{sep}{f2}{sep}{n.year:04d}"

    def dmony(m: re.Match[str]) -> str:
        nonlocal changed
        a, sep, mon_s, y = m.group(1), m.group(2), m.group(3), m.group(4)
        mon = _MONTHS.get(mon_s[:3].casefold())
        if mon is None or (len(mon_s) > 3 and not any(mon_s.casefold() == full for full in _FULL)):
            return m.group(0)
        d = _mk(int(y), mon, int(a))
        if d is None:
            return m.group(0)
        n = d + delta
        changed = True
        name = _FULL_NAMES[n.month - 1] if len(mon_s) > 3 else _MONTH_NAMES[n.month - 1]
        if mon_s.isupper():
            name = name.upper()
        elif mon_s.islower():
            name = name.lower()
        day = f"{n.day:02d}" if len(a) == 2 else str(n.day)
        return f"{day}{sep}{name}{sep}{n.year:04d}"

    out = _ISO.sub(iso, value)
    out = _DMY.sub(dmy, out)
    out = _DMONY.sub(dmony, out)
    return out if changed and out != value else None


_FULL_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_FULL = {n.casefold() for n in _FULL_NAMES} | {"sept"}

_AGE_RE = re.compile(r"(?i)^\s*(\d{1,3})\s*(?:y|yr|yrs|year|years|yo|y/o|वर्ष|साल)?\.?\s*$")


_AGE_SEX_RE = re.compile(r"(?i)^\s*(\d{1,3})\s*(?:y|yr|yrs)?\s*/\s*(m|f|male|female|o)\s*$")


def band_age_text(value: str, width: int) -> str | None:
    """``"47"`` -> ``"45-49"``, ``"73/F"`` -> ``"70-74/F"``; ``None`` if not a plain age in years (unchanged)."""
    ms = _AGE_SEX_RE.match(value or "")
    if ms:
        age = int(ms.group(1))
        return None if age > 120 else f"{age_band(age, width)}/{ms.group(2)}"
    m = _AGE_RE.match(value or "")
    if not m:
        return None
    age = int(m.group(1))
    if age > 120:
        return None
    return age_band(age, width)


_PIN_RE = re.compile(r"^([1-9]\d{2})\s?(\d{3})$")


def pin_prefix(span: str) -> str | None:
    """True 3-digit PIN prefix with the rest suppressed (``110XXX``); ``None`` if not a 6-digit PIN."""
    m = _PIN_RE.match(span.strip())
    return f"{m.group(1)}XXX" if m else None
