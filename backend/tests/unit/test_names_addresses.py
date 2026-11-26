"""Contextual name and address detectors (synthetic, invented names not in any gazetteer)."""

import pytest

from clinveil.detection.addresses import address_components, detect_addresses
from clinveil.detection.names import detect_names, looks_like_person_name


def found(text: str) -> set[tuple[str, str]]:
    hits, _ = detect_names(text)
    return {(h.entity.value, text[h.start : h.end]) for h in hits if h.confidence >= 0.7}


@pytest.mark.parametrize(
    "text, entity, name",
    [
        ("Patient Name: Orvila Tamsen   Age: 40", "PATIENT_NAME", "Orvila Tamsen"),
        ("Name: ORVILA TAMSEN   Age: 91/M", "PATIENT_NAME", "ORVILA TAMSEN"),
        ("Pt. Orvila Tamsen admitted", "PATIENT_NAME", "Orvila Tamsen"),
        ("Report of Orvila ji  48 Y / F", "PATIENT_NAME", "Orvila"),
        ("नाम: ओरविला तामसेन   आयु: 39 वर्ष", "PATIENT_NAME", "ओरविला तामसेन"),
        ("मरीज़ का नाम: ओरविला तामसेन    आयु: 45", "PATIENT_NAME", "ओरविला तामसेन"),
        ("Smt. Orvila Tamsen", "PATIENT_NAME", "Orvila Tamsen"),
        ("Mohd. Tamsen admitted", "PATIENT_NAME", "Mohd. Tamsen"),
        ("Tamsen sahab ka BP 117/82", "PATIENT_NAME", "Tamsen"),
        ("Orvila didi ki condition stable", "PATIENT_NAME", "Orvila"),
        ("Sample received from Orvila's attendant", "PATIENT_NAME", "Orvila"),
        ("14:00 - Orvila Tamsen - K/C/O typhoid", "PATIENT_NAME", "Orvila Tamsen"),
        ("S/o Kelvar Dunmore", "RELATIVE_NAME", "Kelvar Dunmore"),
        ("W/o Kelvar", "RELATIVE_NAME", "Kelvar"),
        ("C/O Kelvar Dunmore, H.No. B-12", "RELATIVE_NAME", "Kelvar Dunmore"),
        ("Father's name: Kelvar Dunmore", "RELATIVE_NAME", "Kelvar Dunmore"),
        ("Attendant: Kelvar Dunmore, Mob. 9876543210", "RELATIVE_NAME", "Kelvar Dunmore"),
        ("पिता का नाम: केल्वर डनमोर", "RELATIVE_NAME", "केल्वर डनमोर"),
        ("D/o केल्वर डनमोर", "RELATIVE_NAME", "केल्वर डनमोर"),
        ("[11/09/26, 8:13 pm] Kelvar Bhaiya: <attachment>", "RELATIVE_NAME", "Kelvar"),
        ("Consent witnessed by Kelvar Dunmore, phone", "RELATIVE_NAME", "Kelvar Dunmore"),
        ("18:40 - Kelvar Dunmore (attendant, bed 12)", "RELATIVE_NAME", "Kelvar Dunmore"),
    ],
)
def test_contextual_names(text, entity, name):
    assert (entity, name) in found(text)


@pytest.mark.parametrize(
    "text",
    [
        "C/O fever x 3 days",
        "C/O: fever x 5 days, body ache",
        "C/O burning micturition x 3 days",
        "C/O pain abdomen",
        "K/C/O Parkinson's disease",
        "06:00 - Patient ne raat theek se neend li.",
        "Doctor sahab ne dekha",
        "Dr ne bola Dolo 650 BD",
        "Patient ko fever hai",
        "Sister ji ne injection diya",
        "H/O TB 8 yrs back",
    ],
)
def test_no_names_in_clinical_phrases(text):
    assert not found(text)


def test_patient_label_inside_relative_label_is_not_a_patient():
    assert found("पति का नाम: केल्वर डनमोर") == {("RELATIVE_NAME", "केल्वर डनमोर")}
    assert ("PATIENT_NAME", "Kelvar Dunmore") not in found("Father's name: Kelvar Dunmore")


def test_doctor_label_yields_keep_span():
    _, keeps = detect_names("Consultant: Dr. Kelvar Dunmore (MD Medicine)")
    assert any(k.kind == "doctor" for k in keeps)


def test_person_name_shape():
    assert looks_like_person_name("S/o Kelvar Dunmore")
    assert looks_like_person_name("ओरविला तामसेन")
    assert not looks_like_person_name("TST/26/000101")
    assert not looks_like_person_name("Patient")


def test_address_components_latin():
    text = (
        "C/O Kelvar, H.No. B-12, Ward 20, Mohalla Teen Batti, near Old Water Tank, Rajpura Kalan, Tehsil Purwa, "
        "Distt. Unnao - 209801"
    )
    got = {(h.entity.value, text[h.start : h.end]) for h in address_components(text)}
    assert {
        ("HOUSE", "H.No. B-12"),
        ("LOCALITY", "Ward 20"),
        ("LOCALITY", "Mohalla Teen Batti"),
        ("LANDMARK", "near Old Water Tank"),
        ("VILLAGE", "Rajpura Kalan"),
        ("PIN", "209801"),
    } <= got
    assert not any("Tehsil" in v or "Unnao" in v for _, v in got)  # tehsil/district preserved (Phase 4)


def test_address_components_devanagari():
    text = "मकान नं. 731, पुराने कुएँ के पास, ग्राम रामपुरा खुर्द, तहसील पुरवा, जिला उन्नाव - २०९८०१"
    got = {(h.entity.value, text[h.start : h.end]) for h in address_components(text)}
    assert ("HOUSE", "मकान नं. 731") in got and ("LANDMARK", "पुराने कुएँ के पास") in got
    assert ("VILLAGE", "रामपुरा खुर्द") in got and ("PIN", "२०९८०१") in got
    assert not any("तहसील" in v or "जिला" in v for _, v in got)


def test_hospital_ward_is_not_an_address():
    assert not detect_addresses("Ward/Bed: Ward 9 (Medicine) / Bed 16")
    assert detect_addresses("Address (attendant): C/O Kelvar, Ward 8")


def test_inline_village_and_pin_labels():
    text = "ग्राम: रामपुरा खुर्द\nPIN: 209801"
    got = {(h.entity.value, text[h.start : h.end]) for h in detect_addresses(text)}
    assert ("VILLAGE", "रामपुरा खुर्द") in got and ("PIN", "209801") in got
