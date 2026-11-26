"""Sensitive value index (propagation) and finding resolution."""

import pickle

import pytest

from clinveil.detection.clinical import KeepSpan
from clinveil.detection.identifiers import Hit
from clinveil.detection.resolve import resolve
from clinveil.detection.value_index import SensitiveValueIndex
from clinveil.models.channels import Channel
from clinveil.models.findings import EntityType as E


def idx() -> SensitiveValueIndex:
    i = SensitiveValueIndex()
    i.add("Orvila Tamsen", E.PATIENT_NAME)
    i.add("Kelvar Devi", E.RELATIVE_NAME)
    i.add("+91 98765 43210", E.PHONE)
    i.add("TST/26/000101", E.MRN)
    i.add("2345 6789 0123", E.AADHAAR)
    i.add("Rajpura Kalan", E.VILLAGE)
    i.add("ABCPE1234F", E.PAN)
    return i


def spans(text: str, channel: Channel = Channel.CONTENT) -> set[tuple[str, str]]:
    return {(h.entity.value, text[h.start : h.end]) for h in idx().match(text, channel)}


def test_full_names_propagate_across_separators_scripts_and_spellings():
    assert ("PATIENT_NAME", "Orvila_Tamsen") in spans("D:\\exports\\Orvila_Tamsen_000101\\v.json", Channel.METADATA)
    assert ("PATIENT_NAME", "Orvilla Tamssen") in spans("Seen: Orvilla Tamssen today")  # spelling variant
    assert ("PATIENT_NAME", "ओरविला तामसेन") in spans("ओरविला तामसेन को बुखार")  # Devanagari form


def test_identifying_single_tokens_propagate_but_generic_ones_do_not():
    assert ("PATIENT_NAME", "Orvila") in spans("Orvila ka BP theek hai")
    assert not any(v == "Devi" for _, v in spans("Kelvar Devi aur Devi Prasad"))
    assert ("RELATIVE_NAME", "Kelvar") in spans("Kelvar aaye the")


def test_lowercase_common_words_are_not_propagated_in_content():
    i = SensitiveValueIndex()
    i.add("Asha Kiran", E.PATIENT_NAME)
    assert not i.match("asha workers visited; kiran therapy", Channel.CONTENT)
    assert i.match("asha_kiran_report", Channel.FILENAME)  # loose channels match any case


def test_short_tokens_never_propagate():
    i = SensitiveValueIndex()
    i.add("Om Ra", E.PATIENT_NAME)
    assert not [h for h in i.match("Om Sai, Ra ji", Channel.CONTENT) if h.detector == "propagation_token"]


def test_digit_identifiers_match_across_separators():
    assert ("PHONE", "98765-43210") in spans("call 98765-43210")
    assert ("PHONE", "919876543210") in spans("wa 919876543210")
    assert ("AADHAAR", "234567890123") in spans("uid 234567890123")
    assert ("MRN", "TST-26-000101") in spans("file TST-26-000101.txt", Channel.FILENAME)
    assert ("MRN", "000101") in spans("Orvila_Tamsen_000101", Channel.METADATA)
    assert ("PAN", "ABCPE1234F") in spans("pan ABCPE1234F")


def test_mrn_cores_do_not_match_inside_longer_numbers_or_short_unpadded_numbers():
    i = SensitiveValueIndex()
    i.add("REG-12345", E.MRN)  # 5-digit core without zero padding
    assert not i.match("amount 12345 paid", Channel.CONTENT)
    assert not i.match("ref 1234567", Channel.CONTENT)


def test_village_phrases_propagate_district_names_never():
    assert ("VILLAGE", "Rajpura Kalan") in spans("from Rajpura Kalan side")
    i = SensitiveValueIndex()
    i.add("Lucknow", E.VILLAGE)
    assert not i.match("referred to Lucknow", Channel.CONTENT)


def test_index_is_never_serialisable_and_repr_shows_sizes_only():
    i = idx()
    with pytest.raises(TypeError):
        pickle.dumps(i)
    assert "Orvila" not in repr(i) and "98765" not in repr(i)


def test_resolve_prefers_longer_and_stronger_spans_and_merges_adjacent_names():
    text = "PMJAY-UP-9876543210 Orvila Tamsen"
    hits = [
        Hit(0, 19, E.INSURANCE_ID, 0.9, "insurance"),
        Hit(9, 19, E.PHONE, 0.9, "phone"),
        Hit(20, 26, E.PATIENT_NAME, 0.78, "propagation_token"),
        Hit(27, 33, E.PATIENT_NAME, 0.78, "propagation_token"),
    ]
    out, _ = resolve(hits, [], text)
    assert [(r.hit.entity, text[r.hit.start : r.hit.end]) for r in out] == [
        (E.INSURANCE_ID, "PMJAY-UP-9876543210"),
        (E.PATIENT_NAME, "Orvila Tamsen"),
    ]


def test_resolve_doctor_spans_block_every_name_and_clinical_spans_block_weak_names():
    text = "Dr. Orvila Tamsen"
    keeps = [KeepSpan(0, len(text), "doctor")]
    out, protected = resolve([Hit(4, 10, E.PATIENT_NAME, 0.95, "field")], keeps, text)
    assert not out and protected == 1
    keeps = [KeepSpan(0, 6, "medication")]
    out, protected = resolve([Hit(0, 6, E.PATIENT_NAME, 0.78, "propagation_token")], keeps, "Orvila")
    assert not out and protected == 1
    out, _ = resolve([Hit(0, 6, E.PATIENT_NAME, 0.92, "patient_label")], keeps, "Orvila")
    assert out and out[0].clinical_conflict


def test_resolve_drops_low_confidence():
    out, _ = resolve([Hit(0, 5, E.MRN, 0.6, "id_shape")], [], "BL/26")
    assert not out
