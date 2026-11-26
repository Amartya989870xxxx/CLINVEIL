"""Phase 2.1 verification: what may enter the run-wide Sensitive Value Index.

Only confirmed PII may seed it (field semantics, explicit person labels, validated
identifiers at >= 0.88). These tests pin three properties on synthetic data:

1. clinical text, labels and columns never seed false PII (P1, D1);
2. clinician names never enter the index, so they cannot be propagated as patients (C3);
3. ambiguous evidence (weak field semantics, care-of, timelines, possessives, gazetteer,
   honorifics) never seeds, so it cannot propagate across files (P2, D2).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from conftest import sanitize_documents


def _index(files: dict[str, str]):
    from clinveil.detection.engine import DetectionEngine
    from clinveil.detection.value_index import SensitiveValueIndex
    from clinveil.ingestion.detect import detect
    from clinveil.ingestion.limits import IngestLimits
    from clinveil.parsing.builder import build_document

    limits, idx = IngestLimits(), SensitiveValueIndex()
    for rel, text in files.items():
        raw = text.encode()
        ext = "." + rel.rsplit(".", 1)[-1]
        doc = build_document(rel, hashlib.sha256(raw).hexdigest(), len(raw), ext, detect(raw, ext, limits), limits)
        DetectionEngine(None).seed(doc, idx)
    return idx


CLINICAL_NOTES = {
    "n/labels.txt": "Test Name: Hemoglobin 9.4 g/dL\nDrug Name: Paracetamol 500 mg\nDisease Name: Typhoid fever\n"
    "Procedure Name: Appendectomy\nHospital Name: Arogya Sadan\nOrganism Name: Klebsiella pneumoniae\n"
    "File Name: scan_report.pdf\nदवा का नाम: पेरासिटामोल",
    "lab/x.csv": "Test Name,Result,Drug Name,Diagnosis,Ward Name,Specimen,Care Notes\n"
    "Hemoglobin,9.4,Paracetamol,Typhoid fever,Medical Ward,Blood,Intensive Care started\n",
    "n/ambiguous.txt": "C/O Left knee pain. Crohn's condition. 14:00 - Blood Transfusion started. "
    "Kelvan sahab ji seen. Pt. Mild fever. Severe Anaemia.",
    "j/weak.json": json.dumps(
        {
            "first": "Positive",
            "family": "Diabetes mellitus",
            "member": "Yes",
            "holder": "Self",
            "client": "Walk-in",
            "given": "Insulin",
            "display": "Normal sinus rhythm",
            "caller": "Ward sister",
        }
    ),
}


@pytest.mark.parametrize("rel", sorted(CLINICAL_NOTES))
def test_clinical_and_ambiguous_inputs_seed_nothing(rel):
    idx = _index({rel: CLINICAL_NOTES[rel]})
    assert len(idx) == 0, repr(idx)


def test_clinician_names_never_enter_the_index():
    files = {
        "a/d.csv": "Consultant,Doctor Name,Referred By,Nurse\nDr. Kelvan Iyer,Arvel Mathur,Dr. Tavin Rao,Sr. Lunika\n",
        "n/d.txt": "Consultant: Dr. Kelvan Iyer\nName: Dr. Arvel Mathur reviewed\nDoctor: Arvel Mathur",
        "f/p.json": json.dumps(
            {
                "resourceType": "Bundle",
                "id": "b",
                "type": "collection",
                "entry": [
                    {
                        "fullUrl": "urn:uuid:pr",
                        "resource": {
                            "resourceType": "Practitioner",
                            "id": "pr",
                            "name": [{"text": "Dr. Kelvan Iyer", "family": "Iyer", "given": ["Kelvan"]}],
                        },
                    },
                    {
                        "fullUrl": "urn:uuid:e",
                        "resource": {
                            "resourceType": "Encounter",
                            "id": "e",
                            "status": "finished",
                            "participant": [{"individual": {"reference": "urn:uuid:pr", "display": "Dr. Kelvan Iyer"}}],
                        },
                    },
                ],
            }
        ),
    }
    idx = _index(files)
    assert not ({"kelvan", "iyer", "arvel", "mathur", "tavin", "lunika"} & set(idx.name_tokens)), repr(idx)


def test_ambiguous_findings_do_not_propagate_across_files():
    files = {k: v.encode() for k, v in CLINICAL_NOTES.items()}
    later = "Paracetamol given at night. Hemoglobin repeated. Insulin started. Typhoid ruled out. Left side weak."
    files["z/later.txt"] = later.encode()
    files["z/doctor.txt"] = b"Dr. Kelvan Iyer reviewed. Arvel Mathur on call."
    files["a/d.csv"] = b"Consultant,Doctor Name\nDr. Kelvan Iyer,Arvel Mathur\n"
    out = sanitize_documents(files)
    assert out["z/later.txt"] == later
    assert out["z/doctor.txt"] == "Dr. Kelvan Iyer reviewed. Arvel Mathur on call."


def test_real_patients_still_seed_and_propagate():
    """The guards must not cost recall: confirmed names still propagate across files."""
    files = {
        "reg/r.csv": b"MRN,Patient Name,Mobile\nTST/26/000951,Orvila Tamsen,9876543210\n",
        "n/a.txt": b"Name: Kelvar Dunmore, Age 52",
        "n/b.txt": b"Orvila Tamsen and Kelvar Dunmore reviewed; call 98765 43210 re TST/26/000951.",
    }
    out = sanitize_documents(files)["n/b.txt"]
    for leaked in ("Orvila", "Tamsen", "Kelvar", "Dunmore", "43210", "000951"):
        assert leaked not in out, leaked
