"""Living specification for the meaning / language traps (PROBLEM_STATEMENT §2).

Runs the real two-pass engine on synthetic text. ``KEEP`` cases must survive
verbatim (clinical utility, contextual precision); ``REMOVE`` cases must not
survive (recall). The six Phase 0/1 strict xfails (leading-zero phone, S/o,
C/O relative, Devanagari label, Hinglish honorific, UHID) are now ordinary
passing cases because Phase 2 implements them.
"""

import pytest

from conftest import sanitize_text

KEEP = [
    # the mandatory meaning traps from the Phase 2 brief
    pytest.param("Dr. Ramesh reviewed the patient.", "Dr. Ramesh", id="dr-ramesh"),
    pytest.param("Dr. Ramesh Iyer reviewed the patient", "Dr. Ramesh Iyer", id="doctor-full-name"),
    pytest.param("C/O fever x 3 days, body ache", "C/O fever x 3 days", id="c/o-complaint"),
    pytest.param("C/O: fever x 5 days, body ache", "C/O: fever x 5 days", id="c/o-colon-complaint"),
    pytest.param("Tab Dolo 650 1-0-1 x 5 days", "Dolo 650 1-0-1 x 5 days", id="dolo-650-1-0-1"),
    pytest.param("Dr ne bola Dolo 650 BD x 5 days lena hai", "Dolo 650 BD x 5 days", id="bd-x-5-days"),
    pytest.param("Tab Paracetamol 500 mg 1-1-1", "Paracetamol 500 mg 1-1-1", id="paracetamol-500"),
    pytest.param("K/C/O Parkinson's disease", "Parkinson's disease", id="eponym-parkinson"),
    pytest.param("Known case of Addison's disease on steroids", "Addison's disease", id="eponym-addison"),
    pytest.param("BP 117/82, SpO2 98%, Pulse 84/min", "BP 117/82, SpO2 98%, Pulse 84/min", id="vitals"),
    pytest.param("RBS 245 mg/dL, Hb 9.4 g/dL", "RBS 245 mg/dL, Hb 9.4 g/dL", id="labs"),
    pytest.param("H/O TB 8 yrs back, completed ATT", "H/O TB 8 yrs back, completed ATT", id="h/o-history"),
    pytest.param("K/C/O DM2 x 6 yrs, HTN on treatment", "K/C/O DM2 x 6 yrs", id="k/c/o"),
    pytest.param("Ward 9 (Medicine) / Bed 16", "Ward 9 (Medicine) / Bed 16", id="hospital-ward"),
    pytest.param("ICD-10 E11.9, HbA1c 8.2 %", "E11.9, HbA1c 8.2 %", id="icd-and-lab"),
    pytest.param("Referred by ASHA worker for ANC", "ASHA worker", id="asha-worker"),
    pytest.param("Patient ko fever hai, kal se bukhar", "Patient ko fever hai, kal se bukhar", id="hinglish-complaint"),
    pytest.param("दवा BD x 5 days, बुखार है", "दवा BD x 5 days, बुखार है", id="mixed-script-clinical"),
    pytest.param("Jeevan Jyoti Charitable Hospital, OPD", "Jeevan Jyoti Charitable Hospital", id="hospital-name"),
    pytest.param("Consultant: Dr. Vandana Mehrotra (MD Medicine)", "Dr. Vandana Mehrotra", id="consultant-label"),
    pytest.param("डॉ. रमेश ने देखा", "डॉ. रमेश", id="devanagari-doctor"),
]


@pytest.mark.parametrize("text, must_survive", KEEP)
def test_clinical_and_contextual_values_kept(text, must_survive):
    assert must_survive in sanitize_text(text)


REMOVE = [
    pytest.param("Name: Harendra Vexpal, Age 47", ["Harendra", "Vexpal"], id="latin-name-label"),
    pytest.param("Address: C/O Ramesh Vexpal, H.No. 731", ["Ramesh", "Vexpal", "731"], id="c/o-relative"),
    pytest.param("Shahid sahab ka BP 117/82", ["Shahid"], id="shahid-sahab"),
    pytest.param("Attendant S/o Zubair informed", ["Zubair"], id="s/o-zubair"),
    pytest.param("Attendant S/o Harendra Vexpal informed", ["Harendra", "Vexpal"], id="relative-s/o"),
    pytest.param("Mob: +91 98765 43210", ["98765", "43210"], id="phone-plus91"),
    pytest.param("Mob: 098765-43210", ["98765", "43210"], id="phone-leading-zero"),
    pytest.param("मोबाइल: ९८७६५४३२१०", ["९८७६५४३२१०"], id="phone-devanagari-digits"),
    pytest.param("Aadhaar 2345 6789 0123", ["6789"], id="aadhaar-spaced"),
    pytest.param("PAN ABCPE1234F", ["ABCPE1234F"], id="pan"),
    pytest.param("नाम: वसुधा मेहरोत्रा  आयु: 38", ["वसुधा", "मेहरोत्रा"], id="devanagari-name-label"),
    pytest.param("पिता का नाम: हरेंद्र वेक्सपाल", ["हरेंद्र", "वेक्सपाल"], id="devanagari-relative-label"),
    pytest.param("Vasudha ji ka BP 120/80", ["Vasudha"], id="hinglish-honorific"),
    pytest.param("Kirti didi ki condition stable hai", ["Kirti"], id="hinglish-didi"),
    pytest.param("Reg No: TST/26/000101", ["000101"], id="uhid"),
    pytest.param("ABHA 91-2345-6789-0123", ["6789"], id="abha"),
    pytest.param("Consent witnessed by Orvila Tamsen, phone 9876543210.", ["Orvila", "Tamsen"], id="witnessed-by"),
    pytest.param("18:40 - Orvila Tamsen (attendant, bed 12), mob 9876543210", ["Orvila", "Tamsen"], id="visitor-log"),
    pytest.param("called by Orvila Tamsen 98765-43210", ["Orvila", "Tamsen"], id="called-by-phone"),
    pytest.param("[12/03/26, 8:15 pm] Orvil Mama: <attachment>", ["Orvil"], id="whatsapp-kinship"),
]


@pytest.mark.parametrize("text, must_vanish", REMOVE)
def test_identifiers_removed(text, must_vanish):
    out = sanitize_text(text)
    for piece in must_vanish:
        assert piece not in out, piece


def test_shahid_sahab_keeps_the_vital_sign():
    out = sanitize_text("Shahid sahab ka BP 117/82")
    assert "BP 117/82" in out and "sahab ka" in out


def test_dr_ramesh_kept_while_relative_ramesh_removed():
    out = sanitize_text("Attendant: Ramesh Vexpal, Mob. 9876543210\nDr. Ramesh Iyer reviewed the patient.")
    assert "Dr. Ramesh Iyer" in out
    assert "Vexpal" not in out and out.count("Ramesh") == 1
