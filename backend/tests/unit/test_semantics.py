"""Semantic field classification, including renamed / misspelled / Hindi headers never seen in practice data."""

import pytest

from clinveil.detection.semantics import Sem, classify_label, classify_path

CASES = [
    # patient names (English, Hindi, Hinglish, abbreviated, misspelled, renamed)
    ("patient_name", Sem.PERSON_NAME),
    ("Patient Name", Sem.PERSON_NAME),
    ("patient's name", Sem.PERSON_NAME),
    ("full_name", Sem.PERSON_NAME),
    ("pt_name", Sem.PERSON_NAME),
    ("name_of_patient", Sem.PERSON_NAME),
    ("नाम", Sem.PERSON_NAME),
    ("रोगी का नाम", Sem.PERSON_NAME),
    ("मरीज_का_नाम", Sem.PERSON_NAME),
    ("Pateint Nmae", Sem.PERSON_NAME),
    ("FirstName", Sem.PERSON_NAME),
    ("Naam", Sem.PERSON_NAME),
    ("Beneficiary Name", Sem.PERSON_NAME),
    # phones
    ("mobile", Sem.PHONE),
    ("mobile_no", Sem.PHONE),
    ("contact_number", Sem.PHONE),
    ("Contact#", Sem.PHONE),
    ("telephone", Sem.PHONE),
    ("संपर्क", Sem.PHONE),
    ("मोबाइल नंबर", Sem.PHONE),
    ("WhatsApp No", Sem.PHONE),
    # relatives
    ("father_name", Sem.RELATIVE_NAME),
    ("husband's name", Sem.RELATIVE_NAME),
    ("spouse", Sem.RELATIVE_NAME),
    ("guardian", Sem.RELATIVE_NAME),
    ("pita", Sem.RELATIVE_NAME),
    ("पिता का नाम", Sem.RELATIVE_NAME),
    ("पति का नाम", Sem.RELATIVE_NAME),
    ("Pita/Pati ka Naam", Sem.RELATIVE_NAME),
    ("Next of Kin", Sem.RELATIVE_NAME),
    ("Contact Person", Sem.RELATIVE_NAME),
    # hospital identifiers
    ("uhid", Sem.MRN),
    ("mrn", Sem.MRN),
    ("registration_no", Sem.MRN),
    ("hospital_id", Sem.MRN),
    ("ipd_no", Sem.MRN),
    ("patient_id", Sem.MRN),
    ("Reg No", Sem.MRN),
    ("patient_ref", Sem.MRN),
    ("CR No", Sem.MRN),
    ("health_id", Sem.ABHA_NUMBER),
    # other identifiers
    ("Aadhaar No", Sem.AADHAAR),
    ("adhaar_number", Sem.AADHAAR),
    ("UID", Sem.AADHAAR),
    ("ABHA No", Sem.ABHA_NUMBER),
    ("abha_address", Sem.ABHA_ADDRESS),
    ("payer_pan", Sem.PAN),
    ("pmjay_id", Sem.INSURANCE_ID),
    ("policy_no", Sem.INSURANCE_ID),
    ("email_id", Sem.EMAIL),
    # locations
    ("village", Sem.VILLAGE),
    ("gaon", Sem.VILLAGE),
    ("Gram/Mohalla", Sem.VILLAGE),
    ("mohalla", Sem.LOCALITY),
    ("locality", Sem.LOCALITY),
    ("address", Sem.ADDRESS),
    ("पता", Sem.ADDRESS),
    ("house_no", Sem.HOUSE),
    ("pin_code", Sem.PIN),
    ("postal_code", Sem.PIN),
    ("Zip", Sem.PIN),
    ("district", Sem.DISTRICT),
    ("tehsil", Sem.TEHSIL),
    ("landmark", Sem.LANDMARK),
    # dates and quasi-identifiers
    ("DOB", Sem.DOB),
    ("Date of Birth", Sem.DOB),
    ("Janm Tithi", Sem.DOB),
    ("Reg Date", Sem.DATE),
    ("admission_date", Sem.DATE),
    ("Age", Sem.AGE),
    ("age_sex", Sem.AGE),
    ("Gender", Sem.GENDER),
    # preserved semantics
    ("doctor", Sem.DOCTOR_NAME),
    ("ref_doctor", Sem.DOCTOR_NAME),
    ("Referring Clinician", Sem.DOCTOR_NAME),
    ("referred_by", Sem.DOCTOR_NAME),
    ("exported_by", Sem.STAFF),
    ("visit_id", Sem.NON_PII_ID),
    ("bill_no", Sem.NON_PII_ID),
    ("sample_id", Sem.NON_PII_ID),
    ("Relation", Sem.RELATION),
    ("notes", Sem.FREE_TEXT),
    ("remarks", Sem.FREE_TEXT),
    ("Heart Rate", Sem.CLINICAL),
]


@pytest.mark.parametrize("label, sem", CASES)
def test_label_classification(label, sem):
    assert classify_label(label).sem is sem


@pytest.mark.parametrize(
    "path, sem",
    [
        (("patients", "name", "first"), Sem.PERSON_NAME),
        (("patients", "guardian", "name"), Sem.RELATIVE_NAME),
        (("tickets", "meta", "raised_by", "name"), Sem.PERSON_NAME),
        (("facility", "name"), Sem.ORGANIZATION),
        (("panels", "name"), Sem.ORGANIZATION),
        (("hospital", "name"), Sem.ORGANIZATION),
        (("visits", "diagnosis", "display"), Sem.ORGANIZATION),
        (("patient", "name"), Sem.PERSON_NAME),
        (("patients", "address", "line"), Sem.ADDRESS),
        (("doctor", "name"), Sem.DOCTOR_NAME),
    ],
)
def test_path_refines_generic_labels(path, sem):
    assert classify_path(path).sem is sem


def test_unknown_labels_stay_unknown():
    assert classify_label("frobnicate").sem is Sem.UNKNOWN
    assert classify_label("").sem is Sem.UNKNOWN


def test_semantic_evidence_never_contains_values():
    s = classify_label("Patient Name")
    assert s.evidence.isascii() and " " not in s.evidence


@pytest.mark.parametrize("label", ["address_note", "Address Details", "address_line", "village_remarks"])
def test_location_label_with_free_text_qualifier_is_still_location(label):
    """Phase 2.1 regression: purity must not demote "address_note" to free text."""
    from clinveil.detection.semantics import STRUCTURED_PII

    assert classify_label(label).sem in STRUCTURED_PII
