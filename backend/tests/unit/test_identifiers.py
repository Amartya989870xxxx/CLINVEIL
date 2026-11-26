"""Identifier detectors: valid, invalid and ambiguous synthetic values."""

import pytest

from clinveil.detection.identifiers import find_identifiers, mrn_digit_core, verhoeff_valid
from clinveil.models.findings import EntityType as E


def kinds(text: str, min_conf: float = 0.7) -> set[tuple[str, str]]:
    return {(h.entity.value, text[h.start : h.end]) for h in find_identifiers(text) if h.confidence >= min_conf}


@pytest.mark.parametrize(
    "text, value",
    [
        ("Mob +91 98765 43210", "+91 98765 43210"),
        ("9876543210", "9876543210"),
        ("98765-43210", "98765-43210"),
        ("098765-43210", "098765-43210"),
        ("+91-9876543210", "+91-9876543210"),
        ("987 654 3210", "987 654 3210"),
        ("9876.543.210", "9876.543.210"),
        ("call 91 98765 43210", "91 98765 43210"),
        ("मोबाइल: ९८७६५४३२१०", "९८७६५४३२१०"),
    ],
)
def test_phone_formats(text, value):
    assert ("PHONE", value) in kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "BP 117/82",
        "Platelets 150000-410000",
        "16-10-2026",
        "Dolo 650 1-0-1",
        "Pulse 84/min",
        "HbA1c 8.2",
        "Hb 12.5 g/dL",
        "amount 14500",
        "OPD/26/10/00181",
        "LOINC 718-7",
        "SNOMED 373942005",
        "5876543210123",
    ],
)
def test_clinical_numbers_are_not_phones(text):
    assert not any(k == "PHONE" for k, _ in kinds(text))


def test_verhoeff():
    assert verhoeff_valid("234567890124") is (verhoeff_valid("234567890124"))
    valid = next(f"23456789012{d}" for d in range(10) if verhoeff_valid(f"23456789012{d}"))
    assert verhoeff_valid(valid)
    assert not verhoeff_valid(valid[:-1] + str((int(valid[-1]) + 1) % 10))
    assert not verhoeff_valid("abc")


def test_aadhaar_grouped_contiguous_masked_and_confidence():
    hits = {h.entity: h for h in find_identifiers("Aadhaar 2345 6789 0123")}
    assert hits[E.AADHAAR].confidence >= 0.9
    assert ("AADHAAR_MASKED", "XXXX XXXX 1234") in kinds("Aadhaar XXXX XXXX 1234")
    assert ("AADHAAR_MASKED", "********1234") in kinds("UID ********1234")
    assert not any(k == "AADHAAR" for k, _ in kinds("1234 5678 9012"))  # cannot start with 0/1


def test_abha_number_beats_inner_aadhaar_shape_in_resolution():
    from clinveil.detection.resolve import resolve

    text = "ABHA 91-2345-6789-0123"
    (r,), _ = resolve(list(find_identifiers(text)), [], text)
    assert r.hit.entity is E.ABHA_NUMBER


def test_abha_address_email_pan_insurance():
    assert ("ABHA_ADDRESS", "vasudha.m@abdm") in kinds("ABHA addr vasudha.m@abdm")
    assert ("EMAIL", "vasudha.m@example.org") in kinds("mail vasudha.m@example.org")
    assert ("PAN", "ABCPE1234F") in kinds("PAN ABCPE1234F")
    assert not any(k == "PAN" for k, _ in kinds("ABCXE1234F"))  # 4th character must be a holder-type letter
    assert ("INSURANCE_ID", "PMJAY-UP-1234567890") in kinds("PMJAY-UP-1234567890")
    assert ("INSURANCE_ID", "POL/12/12345678") in kinds("POL/12/12345678")


@pytest.mark.parametrize(
    "text, value",
    [
        ("UHID: TST/26/000101", "TST/26/000101"),
        ("Reg No: XYZ-0012345", "XYZ-0012345"),
        ("IPD No: IP/26/09917", "IP/26/09917"),
        ("पंजीकरण सं.: TST/26/000101", "TST/26/000101"),
        ("Patient ID: P-998877", "P-998877"),
        ("CR No 445566", "445566"),
    ],
)
def test_labelled_hospital_identifiers(text, value):
    assert ("MRN", value) in kinds(text)


def test_unlabelled_id_shapes_are_low_confidence():
    assert not kinds("Bill BL/26/000244", min_conf=0.7)
    assert kinds("Bill BL/26/000244", min_conf=0.5)


def test_mrn_digit_core():
    assert mrn_digit_core("TST/26/000101") == "000101"
    assert mrn_digit_core("ADM009917") == "009917"
    assert mrn_digit_core("no digits") == ""
