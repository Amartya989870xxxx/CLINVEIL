"""FHIR R4 enumeration and the common IR (synthetic fixtures only)."""

import base64
import json

import pytest

from clinveil.ingestion.detect import detect
from clinveil.ingestion.limits import IngestLimits
from clinveil.models.channels import Channel
from clinveil.models.document import FieldKind, Format
from clinveil.parsing.builder import build_document
from clinveil.parsing.fhir import build_index
from clinveil.sanitization.render import render

L = IngestLimits()
NOTE = "Referral: Harendra Vexpal (TST/26/000101), mobile 9876543210."
P_URL, E_URL, D_URL = "urn:uuid:p-0001", "urn:uuid:e-0001", "urn:uuid:d-0001"


def bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "id": "b-1",
        "meta": {"source": "#TST/26/000101", "lastUpdated": "2026-02-12T11:00:00+05:30"},
        "type": "document",
        "timestamp": "2026-02-12T11:00:00+05:30",
        "entry": [
            {
                "fullUrl": P_URL,
                "resource": {
                    "resourceType": "Patient",
                    "id": "p-0001",
                    "text": {"status": "generated", "div": '<div xmlns="http://www.w3.org/1999/xhtml">HV</div>'},
                    "identifier": [{"system": "https://hospital.example/uhid", "value": "TST/26/000101"}],
                    "name": [{"text": "Harendra Vexpal"}],
                    "telecom": [{"system": "phone", "value": "9876543210"}],
                    "birthDate": "1979-04-12",
                },
            },
            {
                "fullUrl": E_URL,
                "resource": {
                    "resourceType": "Encounter",
                    "id": "e-0001",
                    "subject": {"reference": P_URL},
                    "period": {"start": "2026-02-01", "end": "2026-02-10"},
                },
            },
            {
                "fullUrl": D_URL,
                "resource": {
                    "resourceType": "DocumentReference",
                    "id": "d-0001",
                    "subject": {"reference": "Patient/p-0001"},
                    "context": {"encounter": [{"reference": "Encounter/e-9999"}], "related": [{"reference": "#c1"}]},
                    "content": [
                        {"attachment": {"contentType": "text/plain", "data": base64.b64encode(NOTE.encode()).decode()}}
                    ],
                },
            },
        ],
    }


def _doc(data, rel="fhir/bundle_x.json", ext=".json"):
    raw = json.dumps(data).encode()
    return build_document(rel, "0" * 64, len(raw), ext, detect(raw, ext, L), L)


def test_fhir_detected_and_single_record():
    doc = _doc(bundle())
    assert doc.source.format is Format.FHIR and doc.records == ["doc"]
    assert doc.fhir is not None and doc.fhir.is_bundle


def test_fhir_entries_and_reference_resolution():
    idx = build_index(bundle())
    assert [(e.index, e.resource_type) for e in idx.entries] == [
        (0, "Patient"),
        (1, "Encounter"),
        (2, "DocumentReference"),
    ]
    by_ptr = {r.pointer: r for r in idx.references}
    assert by_ptr["/entry/1/resource/subject/reference"].target_entry == 0  # urn:uuid fullUrl
    assert by_ptr["/entry/2/resource/subject/reference"].target_entry == 0  # Type/id
    assert by_ptr["/entry/2/resource/context/related/0/reference"].contained
    unresolved = [r.pointer for r in idx.unresolved]
    assert unresolved == ["/entry/2/resource/context/encounter/0/reference"]  # Encounter/e-9999 is absent


def test_fhir_roles_and_element_paths():
    doc = _doc(bundle())
    ctx = {f.address: f.fhir for f in doc.fields if f.kind is FieldKind.JSON_STRING}
    assert ctx["/meta/source"].role == "meta_source" and ctx["/meta/source"].element == "Bundle.meta.source"
    assert ctx["/entry/0/resource/text/div"].role == "narrative"
    assert ctx["/entry/0/resource/identifier/0/value"].role == "identifier"
    assert ctx["/entry/0/resource/identifier/0/value"].element == "Patient.identifier.value"
    assert ctx["/entry/0/resource/name/0/text"].role == "name"
    assert ctx["/entry/0/resource/telecom/0/value"].role == "telecom"
    assert ctx["/entry/0/resource/birthDate"].role == "date"
    assert ctx["/entry/1/resource/period/start"].role == "date"
    assert ctx["/entry/1/resource/subject/reference"].role == "reference"
    assert ctx["/entry/2/resource/content/0/attachment/data"].role == "attachment"
    assert ctx["/entry/0/resource/birthDate"].entry == 0
    key = doc.get_field("/entry/1/resource/subject/reference#key")
    assert key.fhir.element == "Encounter.subject.reference" and key.fhir.role is None


def test_fhir_meta_is_metadata_channel_and_attachment_is_decoded():
    doc = _doc(bundle())
    meta = {f.address for f in doc.iter_fields(channel=Channel.METADATA)}
    assert "/meta/source" in meta and "/meta/lastUpdated" in meta
    (child,) = list(doc.iter_fields(kind=FieldKind.BASE64_TEXT))
    assert child.value == NOTE and child.channel is Channel.BASE64
    assert child.parent == "/entry/2/resource/content/0/attachment/data" and child.record == "doc"
    assert child.fhir.role == "attachment"


def test_fhir_structure_survives_rendering_and_references_still_resolve():
    original = bundle()
    doc = _doc(original)
    out = json.loads(render(doc, {}))
    assert out == original
    assert [r.target_entry for r in build_index(out).references] == [r.target_entry for r in doc.fhir.references]


def test_sanitised_attachment_is_reencoded_not_raw():
    from conftest import sanitize_documents

    (text,) = sanitize_documents({"fhir/bundle_x.json": json.dumps(bundle()).encode()}).values()
    data = json.loads(text)["entry"][2]["resource"]["content"][0]["attachment"]["data"]
    decoded = base64.b64decode(data).decode()
    assert "9876543210" not in decoded and "[PHONE]" in decoded
    # the name and UHID are known from the Patient resource and propagated into the payload
    assert "Harendra" not in decoded and "000101" not in decoded


# --------------------------------------------------------------------------- generic IR
def test_csv_ir_addresses_records_channels_labels():
    raw = b"UHID,Patient Name,Mobile\nTST-1,Harendra Vexpal,9876543210\nTST-2,Kiran Moltey,9123456780\n"
    doc = build_document("registration/reg.csv", "0" * 64, len(raw), ".csv", detect(raw, ".csv", L), L)
    assert doc.records == ["row:0", "row:1"]
    headers = list(doc.iter_fields(kind=FieldKind.HEADER))
    assert [h.value for h in headers] == ["UHID", "Patient Name", "Mobile"]
    assert all(h.channel is Channel.HEADER and h.record == "@header" for h in headers)
    cell = doc.get_field("row:1/1")
    assert cell.value == "Kiran Moltey" and cell.label == "Patient Name" and cell.record == "row:1"
    names = [f.value for f in doc.iter_fields(channel=Channel.FILENAME)]
    assert names == ["registration", "reg.csv"]


def test_json_ir_records_keys_and_metadata():
    data = {
        "_export_meta": {"source_path": "D:\\exports\\x"},
        "visits": [{"visit_id": "V1", "vitals": {"pulse": 88}}, {"visit_id": "V2", "ok": True, "n": None}],
        "by_uhid": {"TST-1": {"visits": 3}},
    }
    doc = _doc(data, rel="opd/x.json")
    assert doc.records == ["/visits/0", "/visits/1"]
    assert doc.get_field("/_export_meta/source_path").channel is Channel.METADATA
    assert doc.get_field("/_export_meta/source_path").record == "@file"
    assert doc.get_field("/visits/0/vitals/pulse").kind is FieldKind.JSON_NUMBER
    assert doc.get_field("/visits/0/vitals/pulse").record == "/visits/0"
    assert doc.get_field("/visits/1/n").kind is FieldKind.JSON_NULL
    key = doc.get_field("/by_uhid/TST-1#key")
    assert key.channel is Channel.KEY and key.value == "TST-1" and key.record == "@file"


def test_pointer_escaping_in_addresses():
    doc = _doc({"a/b": {"c~d": "x"}})
    assert doc.get_field("/a~1b/c~0d").value == "x"


def test_text_ir_with_embedded_payload():
    payload = base64.b64encode(NOTE.encode()).decode()
    raw = f"Nursing note. Attachment {payload} end.".encode()
    doc = build_document("notes/n.txt", "0" * 64, len(raw), ".txt", detect(raw, ".txt", L), L)
    (text_field,) = list(doc.iter_fields(kind=FieldKind.TEXT))
    assert len(text_field.segments) == 1
    assert doc.get_field("doc#b64/0").value == NOTE


def test_renamed_keys_never_collide():
    doc = _doc({"k1": 1, "k2": 2})
    out = json.loads(render(doc, {"/k1#key": "[X]", "/k2#key": "[X]"}))
    assert out == {"[X]": 1, "[X]~2": 2}


def test_ir_reprs_hide_values():
    doc = _doc(bundle())
    blob = repr(doc.fields) + repr(doc.source) + repr(doc.fhir)
    assert "Harendra" not in blob and "9876543210" not in blob and "bundle_x" not in blob


def test_ir_build_is_deterministic():
    a, b = _doc(bundle()), _doc(bundle())
    assert [(f.address, f.value, f.channel, f.kind, f.record) for f in a.fields] == [
        (f.address, f.value, f.channel, f.kind, f.record) for f in b.fields
    ]


@pytest.mark.parametrize("bad", [[1, 2, 3], {"resourceType": "Bundle", "entry": "notalist"}])
def test_fhir_index_tolerates_malformed_bundles(bad):
    if isinstance(bad, dict):
        assert build_index(bad).entries == []
