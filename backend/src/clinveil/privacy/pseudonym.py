# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Keyed pseudonyms and per-patient date shifts (derivations identical to the starter).

* ``pseudonym``: HMAC-SHA256(secret, patient_key), first 30 bits rendered as 6
  Crockford base32 characters -> ``PSN-XXXXXX``. Non-reversible without the secret,
  changes completely when the secret changes (scoring attacks A6 and A7).
* ``date_shift_days``: HMAC-SHA256(secret, "shift|" + patient_key) mapped to
  ``[-max, +max)``, never 0. One patient gets one shift, so intervals and lengths
  of stay are preserved exactly while each patient moves differently (defeats the
  A5 global-shift recovery).

``patient_key`` must be an internal canonical cluster key. It must never be a
raw identifier that is also written to output.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac

from clinveil.security.secrets import ReleaseSecret

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
PREFIX = "PSN-"


class Pseudonymizer:
    __slots__ = ("_secret", "_shift_max")

    def __init__(self, secret: ReleaseSecret, date_shift_max_days: int) -> None:
        self._secret = secret
        self._shift_max = int(date_shift_max_days)

    def __repr__(self) -> str:
        return "Pseudonymizer(<redacted>)"

    def pseudonym(self, patient_key: str) -> str:
        digest = hmac.new(self._secret.key, patient_key.encode("utf-8"), hashlib.sha256).digest()
        n = int.from_bytes(digest[:5], "big")
        code = "".join(ALPHABET[(n >> (5 * i)) & 31] for i in range(6))
        return f"{PREFIX}{code}"

    def date_shift_days(self, patient_key: str) -> int:
        m = self._shift_max
        d = hmac.new(self._secret.key, b"shift|" + patient_key.encode("utf-8"), hashlib.sha256).digest()
        v = int.from_bytes(d[:4], "big") % (2 * m) - m
        return v if v != 0 else 1

    def shift_date(self, value: dt.date, patient_key: str) -> dt.date:
        return value + dt.timedelta(days=self.date_shift_days(patient_key))
