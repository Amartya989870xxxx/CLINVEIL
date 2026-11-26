"""Living specification for the meaning / language traps (PROBLEM_STATEMENT §2).

Every case is synthetic. ``KEEP`` cases must survive verbatim (clinical utility,
contextual precision). ``REMOVE`` cases must not survive (recall). Cases the
Phase 0 regex baseline gets wrong are ``xfail(strict=True)``: when Phase 2 fixes
one, the XPASS fails the suite and the marker must be removed, so this file
always documents exactly what the engine can and cannot do.
"""

import pytest

from clinveil.privacy.pseudonym import Pseudonymizer
from clinveil.sanitization.processors import RunStats, Sanitizer
from clinveil.security.secrets import ReleaseSecret

GAP = pytest.mark.xfail(strict=True, reason="baseline regex gap: Phase 2 detection")


@pytest.fixture(scope="module")
def clean():
    s = Sanitizer(Pseudonymizer(ReleaseSecret(b"t"), 180), RunStats())
    return s.clean_text


KEEP = [
    pytest.param("Dr. Anirudh Iyer reviewed the patient", "Anirudh Iyer", id="doctor-name-kept"),
    pytest.param("Tab Dolo 650 1-0-1 x 5 days", "Dolo 650 1-0-1 x 5 days", id="dose-and-frequency"),
    pytest.param("Tab Azithromycin 500 mg BD x 5 days", "500 mg BD x 5 days", id="bd-x-days"),
    pytest.param("C/O fever x 3 days, body ache", "C/O fever x 3 days", id="c/o-complaint"),
    pytest.param("K/C/O Parkinson's disease", "Parkinson's disease", id="eponym"),
    pytest.param("RBS 245 mg/dL, BP 150/90", "245 mg/dL, BP 150/90", id="lab-and-vitals"),
    pytest.param("H/O TB 8 yrs back, completed ATT", "H/O TB 8 yrs back", id="h/o-history"),
    pytest.param("Ward B (Surgery), Bed C-3", "Ward B (Surgery), Bed C-3", id="hospital-ward"),
    pytest.param("ICD-10 E11.9, HbA1c 8.2 %", "E11.9, HbA1c 8.2 %", id="icd-and-lab"),
]


@pytest.mark.parametrize("text, must_survive", KEEP)
def test_clinical_and_contextual_values_kept(clean, text, must_survive):
    assert must_survive in clean(text)


REMOVE = [
    pytest.param("Name: Harendra Vexpal, Age 47", "Vexpal", id="latin-name-label"),
    pytest.param("Mob: +91 98765 43210", "98765", id="phone-plus91"),
    pytest.param("Aadhaar 2345 6789 0123", "6789", id="aadhaar-spaced"),
    pytest.param("PAN ABCDE1234F", "ABCDE1234F", id="pan"),
    pytest.param("Mob: 098765-43210", "43210", id="phone-leading-zero", marks=GAP),
    pytest.param("Attendant S/o Harendra Vexpal informed", "Vexpal", id="relative-s/o", marks=GAP),
    pytest.param("C/O Harendra Vexpal, H.No. 731", "Vexpal", id="c/o-relative", marks=GAP),
    pytest.param("नाम: वसुधा मेहरोत्रा  आयु: 38", "वसुधा", id="devanagari-name-label", marks=GAP),
    pytest.param("Vasudha ji ka BP 120/80", "Vasudha", id="hinglish-honorific", marks=GAP),
    pytest.param("Reg No: TST/26/000101", "000101", id="uhid", marks=GAP),
    pytest.param("ABHA 91-2345-6789-0123", "6789", id="abha"),  # caught (as AADHAAR) by the 12-digit rule
]


@pytest.mark.parametrize("text, must_vanish", REMOVE)
def test_identifiers_removed(clean, text, must_vanish):
    assert must_vanish not in clean(text)
