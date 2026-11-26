import datetime as dt
import hashlib
import re

import pytest

from clinveil.privacy.generalize import age_band
from clinveil.privacy.pseudonym import ALPHABET, Pseudonymizer
from clinveil.security.secrets import ReleaseSecret

PSN = re.compile(rf"^PSN-[{ALPHABET}]{{6}}$")


def _p(secret: str = "s1", m: int = 180) -> Pseudonymizer:
    return Pseudonymizer(ReleaseSecret(secret.encode()), m)


def test_pseudonym_format_and_stability():
    p = _p()
    a = p.pseudonym("cluster-0001")
    assert PSN.match(a)
    assert a == p.pseudonym("cluster-0001")
    assert a != p.pseudonym("cluster-0002")


def test_pseudonym_depends_on_secret():
    keys = [f"cluster-{i}" for i in range(200)]
    a = {_p("s1").pseudonym(k) for k in keys}
    b = {_p("s2").pseudonym(k) for k in keys}
    assert not a & b  # A7: no pseudonym survives a secret change (30-bit space: collisions ~never)


def test_pseudonym_is_not_an_unkeyed_hash():
    # A6 pseudonym inversion: the code must not be a prefix/transform of plain hashes of the key.
    key = "TST/26/000101"
    code = _p().pseudonym(key)[4:].lower()
    for algo in ("md5", "sha1", "sha256", "sha512"):
        assert code not in hashlib.new(algo, key.encode()).hexdigest()
    assert "000101" not in code


def test_date_shift_range_nonzero_and_interval_preserving():
    p = _p(m=30)
    shifts = {p.date_shift_days(f"k{i}") for i in range(500)}
    assert 0 not in shifts
    assert min(shifts) >= -30 and max(shifts) < 30
    adm, dis = dt.date(2026, 3, 1), dt.date(2026, 3, 10)
    assert (p.shift_date(dis, "k1") - p.shift_date(adm, "k1")).days == 9  # length of stay kept


def test_date_shift_differs_between_patients_and_secrets():
    assert len({_p().date_shift_days(f"k{i}") for i in range(50)}) > 10  # not a global shift (A5)
    diffs = sum(_p("s1").date_shift_days(f"k{i}") != _p("s2").date_shift_days(f"k{i}") for i in range(100))
    assert diffs > 90


@pytest.mark.parametrize("age", [0, 4, 5, 47, 49, 97, 120])
def test_age_band_contains_true_age(age):
    lo, hi = map(int, age_band(age).split("-"))
    assert lo <= age <= hi and hi - lo == 4


def test_age_band_rejects_negative():
    with pytest.raises(ValueError):
        age_band(-1)
