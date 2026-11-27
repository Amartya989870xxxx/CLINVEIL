"""Phase 4 privacy transformations: per-patient date shift, 5-year age bands, PIN prefix, rare-cell PIN suppression.

All names, identifiers, PINs and dates are newly invented for these tests.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from pathlib import Path

import pytest

from clinveil.config.policy import Policy
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.pipeline import run
from clinveil.privacy.transform import band_age_text, pin_prefix, shift_date_text
from clinveil.security.secrets import ReleaseSecret
from conftest import TEST_SECRET


def _aadhaar(prefix11: str) -> str:
    return next(prefix11 + d for d in "0123456789" if verhoeff_valid(prefix11 + d))


AAD_A = _aadhaar("73618294051")
AAD_B = _aadhaar("84729305162")


# ----------------------------------------------------------------------------- unit: dates
@pytest.mark.parametrize(
    ("value", "days", "expected"),
    [
        ("2024-03-07", 10, "2024-03-17"),
        ("2024-02-28", 1, "2024-02-29"),  # leap year
        ("2023-02-28", 1, "2023-03-01"),  # non-leap year
        ("2024-12-25", 10, "2025-01-04"),  # year boundary
        ("07/03/2024", -7, "29/02/2024"),  # day-first, month boundary, leap day
        ("7-3-2024", 1, "8-3-2024"),
        ("07.03.2024", 30, "06.04.2024"),
        ("07-Mar-2024", 30, "06-Apr-2024"),
        ("2026-07-19T18:15:00+05:30", 3, "2026-07-22T18:15:00+05:30"),  # FHIR dateTime: time and zone kept
    ],
)
def test_phase4_shift_date_text_formats(value, days, expected):
    assert shift_date_text(value, days) == expected


@pytest.mark.parametrize("value", ["31/02/2024", "2024-13-01", "2024-03", "March 2024", "unknown", "", "120/80"])
def test_phase4_shift_date_text_invalid_or_partial_left_unchanged(value):
    assert shift_date_text(value, 25) is None


def test_phase4_shift_preserves_interval():
    a, b = shift_date_text("13/01/2026", 47), shift_date_text("18/01/2026", 47)
    da = dt.datetime.strptime(a, "%d/%m/%Y")
    db = dt.datetime.strptime(b, "%d/%m/%Y")
    assert (db - da).days == 5


# ----------------------------------------------------------------------------- unit: ages
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "0-4"),
        ("4", "0-4"),
        ("5", "5-9"),
        ("44", "40-44"),
        ("45", "45-49"),
        ("49", "45-49"),
        ("47 yrs", "45-49"),
        ("47Y", "45-49"),
        ("120", "120-124"),
    ],
)
def test_phase4_age_band_boundaries(value, expected):
    assert band_age_text(value, 5) == expected


@pytest.mark.parametrize("value", ["6 months", "121", "unknown", "", "47/X", "4.5"])
def test_phase4_age_band_abstains_on_non_year_ages(value):
    assert band_age_text(value, 5) is None


# ----------------------------------------------------------------------------- unit: PIN
@pytest.mark.parametrize(
    ("value", "expected"),
    [("110001", "110XXX"), ("560 034", "560XXX"), ("012345", None), ("1100012", None), ("11000", None)],
)
def test_phase4_pin_prefix(value, expected):
    assert pin_prefix(value) == expected


# ----------------------------------------------------------------------------- pipeline
def _run(tmp_path: Path, files: dict[str, str], secret: str = TEST_SECRET) -> Path:
    inp, out = tmp_path / "in", tmp_path / "out"
    for rel, content in files.items():
        p = inp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    summary = run(inp, out, ReleaseSecret(secret.encode()), Policy())
    assert summary.ok, summary.problems
    return out


def _rows(out: Path, rel: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO((out / "sanitized" / rel).read_text(encoding="utf-8"))))


_ADM = (
    "Patient Name,Aadhaar,Age,Gender,Admission Date,Discharge Date\n"
    f"Corvina Ashdale,{AAD_A},47,F,13/01/2026,18/01/2026\n"
    f"Thessaly Brandwick,{AAD_B},62,M,02/03/2026,09/03/2026\n"
)
_LAB = f"Patient Name,Aadhaar,Sample Date\nCorvina Ashdale,{AAD_A},15/01/2026\n"


def _d(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


def test_phase4_pipeline_dates_shifted_interval_and_cross_file_offset_kept(tmp_path):
    out = _run(tmp_path, {"ward/admissions.csv": _ADM, "lab/samples.csv": _LAB})
    adm, lab = _rows(out, "ward/admissions.csv"), _rows(out, "lab/samples.csv")
    a, b = adm[0], adm[1]
    assert a["Admission Date"] != "13/01/2026" and b["Admission Date"] != "02/03/2026"
    # length of stay preserved
    assert (_d(a["Discharge Date"]) - _d(a["Admission Date"])).days == 5
    assert (_d(b["Discharge Date"]) - _d(b["Admission Date"])).days == 7
    # same linked patient, same offset across files: admission -> sample interval kept (2 days)
    assert (_d(lab[0]["Sample Date"]) - _d(a["Admission Date"])).days == 2
    # two different patients: independent offsets
    off_a = (_d(a["Admission Date"]) - dt.date(2026, 1, 13)).days
    off_b = (_d(b["Admission Date"]) - dt.date(2026, 3, 2)).days
    assert off_a != 0 and off_b != 0 and abs(off_a) <= 180 and abs(off_b) <= 180


def test_phase4_pipeline_offsets_depend_on_secret(tmp_path):
    o1 = _run(tmp_path / "s1", {"ward/admissions.csv": _ADM})
    o2 = _run(tmp_path / "s2", {"ward/admissions.csv": _ADM}, secret="another-test-secret-0123456789abcdef")
    assert (
        _rows(o1, "ward/admissions.csv")[0]["Admission Date"] != _rows(o2, "ward/admissions.csv")[0]["Admission Date"]
    )


def test_phase4_pipeline_unlinked_record_shifted_without_patient_offset(tmp_path):
    # No identifier: the record is not linked, but its dates are still shifted (record-level key) and its own
    # chronology is preserved.
    files = {"ward/walkin.csv": "Bed,Admission Date,Discharge Date\n4,15/05/2026,18/05/2026\n"}
    row = _rows(_run(tmp_path, files), "ward/walkin.csv")[0]
    assert row["Admission Date"] != "15/05/2026"
    assert (_d(row["Discharge Date"]) - _d(row["Admission Date"])).days == 3


def test_phase4_pipeline_age_banded(tmp_path):
    adm = _rows(_run(tmp_path, {"ward/admissions.csv": _ADM}), "ward/admissions.csv")
    assert [r["Age"] for r in adm] == ["45-49", "60-64"]


def _pin_csv(rows: list[tuple[str, int, str, str]]) -> str:
    lines = ["Patient Name,Age,Gender,PIN"]
    lines += [f"{n},{a},{g},{p}" for n, a, g, p in rows]
    return "\n".join(lines) + "\n"


_PEOPLE = ["Ilsabet Morrow", "Quenby Halstrom", "Odessa Varnell", "Pellam Ardent", "Rosalind Cathay", "Tamsin Ellery"]


def test_phase4_rare_cell_common_pin_prefix_kept_rare_suppressed(tmp_path):
    rows = [(n, 32, "F", f"2260{10 + i:02d}") for i, n in enumerate(_PEOPLE[:5])]
    rows.append((_PEOPLE[5], 71, "M", "560034"))  # unique combination
    out = _run(tmp_path, {"reg/patients.csv": _pin_csv(rows)})
    got = _rows(out, "reg/patients.csv")
    assert [r["PIN"] for r in got[:5]] == ["226XXX"] * 5
    assert got[5]["PIN"] == "[PIN]"
    text = (out / "sanitized" / "reg" / "patients.csv").read_text(encoding="utf-8")
    for _, _, _, pin in rows:
        assert pin not in text  # no full PIN remains anywhere


def test_phase4_rare_cell_small_dataset_suppresses_all_pins(tmp_path):
    rows = [(n, 32, "F", "226010") for n in _PEOPLE[:3]]  # 3 < min_group_size 5
    got = _rows(_run(tmp_path, {"reg/patients.csv": _pin_csv(rows)}), "reg/patients.csv")
    assert [r["PIN"] for r in got] == ["[PIN]"] * 3


def test_phase4_clinical_values_not_touched(tmp_path):
    files = {
        "lab/results.csv": "Patient Name,Aadhaar,Test,Result,Reference,Report Date\n"
        f"Corvina Ashdale,{AAD_A},Glucose,112,70-140,15/01/2026\n"
    }
    row = _rows(_run(tmp_path, files), "lab/results.csv")[0]
    assert (row["Test"], row["Result"], row["Reference"]) == ("Glucose", "112", "70-140")
    assert row["Report Date"] != "15/01/2026"


def test_phase4_fhir_dates_shift_consistently_within_bundle(tmp_path):
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p1",
                    "name": [{"given": ["Corvina"], "family": "Ashdale"}],
                    "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AAD_A}],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "e1",
                    "status": "finished",
                    "subject": {"reference": "Patient/p1"},
                    "period": {"start": "2026-01-13T09:00:00+05:30", "end": "2026-01-18T11:00:00+05:30"},
                }
            },
        ],
    }
    out = _run(tmp_path, {"fhir/b.json": json.dumps(bundle)})
    res = json.loads((out / "sanitized" / "fhir" / "b.json").read_text(encoding="utf-8"))
    period = next(e["resource"]["period"] for e in res["entry"] if e["resource"]["resourceType"] == "Encounter")
    s = dt.datetime.fromisoformat(period["start"])
    e = dt.datetime.fromisoformat(period["end"])
    assert period["start"] != "2026-01-13T09:00:00+05:30"
    assert (e.date() - s.date()).days == 5
    assert period["start"].endswith("T09:00:00+05:30")


# ----------------------------------------------------------------------------- ambiguous day/month order
def test_phase4_ambiguous_numeric_date_suppressed_without_order_evidence():
    assert shift_date_text("05/03/2026", 10, None) == "[DATE]"
    assert shift_date_text("05/05/2026", 10, None) == "[DATE]"  # same either way, still not guessed
    assert shift_date_text("Seen 05/03/2026, BP 120/80, Hb 11.2", 10, None) == "Seen [DATE], BP 120/80, Hb 11.2"


def test_phase4_ambiguous_numeric_date_uses_document_order():
    assert shift_date_text("05/03/2026", 10, "dmy") == "15/03/2026"
    assert shift_date_text("05/03/2026", 10, "mdy") == "05/13/2026"


@pytest.mark.parametrize(("value", "expected"), [("13/05/2026", "23/05/2026"), ("05/13/2026", "05/23/2026")])
def test_phase4_unambiguous_numeric_date_read_correctly_without_evidence(value, expected):
    assert shift_date_text(value, 10, None) == expected


def test_phase4_pipeline_month_first_document_shifted_consistently(tmp_path):
    files = {"legacy/visits.csv": "Bed,Admission Date,Discharge Date\n7,05/03/2026,05/13/2026\n"}
    row = _rows(_run(tmp_path, files), "legacy/visits.csv")[0]
    adm = dt.datetime.strptime(row["Admission Date"], "%m/%d/%Y").date()
    dis = dt.datetime.strptime(row["Discharge Date"], "%m/%d/%Y").date()
    assert row["Admission Date"] != "05/03/2026"
    assert (dis - adm).days == 10


@pytest.mark.parametrize(("adm", "dis"), [("05/03/2026", "06/03/2026"), ("05/05/2026", "08/05/2026")])
def test_phase4_pipeline_ambiguous_dates_without_evidence_suppressed(tmp_path, adm, dis):
    files = {"legacy/visits.csv": f"Bed,Admission Date,Discharge Date\n7,{adm},{dis}\n"}
    out = _run(tmp_path, files)
    row = _rows(out, "legacy/visits.csv")[0]
    assert (row["Admission Date"], row["Discharge Date"]) == ("[DATE]", "[DATE]")
    text = (out / "sanitized" / "legacy" / "visits.csv").read_text(encoding="utf-8")
    assert adm not in text and dis not in text


def test_phase4_pipeline_day_first_document_shifted(tmp_path):
    files = {"ward/a.csv": "Bed,Admission Date,Discharge Date\n7,05/03/2026,14/03/2026\n"}
    row = _rows(_run(tmp_path, files), "ward/a.csv")[0]
    assert "[DATE]" not in row.values()
    assert (_d(row["Discharge Date"]) - _d(row["Admission Date"])).days == 9


def test_phase4_pipeline_mixed_format_document(tmp_path):
    # ISO, month-name and unambiguous day-first dates plus clinical measurements in one document.
    files = {
        "ward/mixed.csv": "Bed,Admission Date,Sample Date,Discharge Date,BP,Hb,Range\n"
        "7,2026-03-05,07-Mar-2026,14/03/2026,120/80,11.2,12-16\n"
    }
    row = _rows(_run(tmp_path, files), "ward/mixed.csv")[0]
    adm = dt.date.fromisoformat(row["Admission Date"])
    smp = dt.datetime.strptime(row["Sample Date"], "%d-%b-%Y").date()
    dis = _d(row["Discharge Date"])
    assert row["Admission Date"] != "2026-03-05"
    assert ((smp - adm).days, (dis - adm).days) == (2, 9)
    assert (row["BP"], row["Hb"], row["Range"]) == ("120/80", "11.2", "12-16")


# ----------------------------------------------------------------------------- ages: combined and JSON numbers
@pytest.mark.parametrize(
    ("value", "expected"), [("73/F", "70-74/F"), ("5/M", "5-9/M"), ("47 yrs / male", "45-49/male")]
)
def test_phase4_age_sex_combined_banded(value, expected):
    assert band_age_text(value, 5) == expected


def test_phase4_pipeline_json_numeric_age_type_preserved_not_banded(tmp_path):
    doc = {"patient": {"name": "Corvina Ashdale", "aadhaar": AAD_A, "age": 47}, "diagnosis": "Type 2 diabetes"}
    out = _run(tmp_path, {"export/patient.json": json.dumps(doc)})
    res = json.loads((out / "sanitized" / "export" / "patient.json").read_text(encoding="utf-8"))
    assert res["patient"]["age"] == 47  # documented limitation: JSON numbers keep their type and value
    assert res["diagnosis"] == "Type 2 diabetes"


def test_phase4_pipeline_nested_json_labelled_dates_shifted(tmp_path):
    doc = {
        "patient": {"name": "Corvina Ashdale", "aadhaar": AAD_A},
        "visits": [{"visit_date": "2026-03-04", "labs": [{"test": "Hb", "value": 11.2, "date": "2026-03-06"}]}],
    }
    out = _run(tmp_path, {"export/visits.json": json.dumps(doc)})
    res = json.loads((out / "sanitized" / "export" / "visits.json").read_text(encoding="utf-8"))
    v = res["visits"][0]
    a = dt.date.fromisoformat(v["visit_date"])
    b = dt.date.fromisoformat(v["labs"][0]["date"])
    assert v["visit_date"] != "2026-03-04" and (b - a).days == 2
    assert v["labs"][0]["value"] == 11.2


# ----------------------------------------------------------------------------- free text
def test_phase4_pipeline_free_text_dates_shifted_with_interval(tmp_path):
    note = (
        f"Patient: Corvina Ashdale\nAadhaar: {AAD_A}\nAdmitted on 13/01/2026 with fever.\n"
        "Discharged on 18/01/2026. Review 2026-02-01.\nBP 120/80, Hb 11.2 g/dL.\n"
    )
    out = _run(tmp_path, {"notes/discharge.txt": note})
    text = (out / "sanitized" / "notes" / "discharge.txt").read_text(encoding="utf-8")
    assert "13/01/2026" not in text and "18/01/2026" not in text and "2026-02-01" not in text
    assert "BP 120/80" in text and "Hb 11.2 g/dL" in text
    import re

    d1, d2 = re.findall(r"\d{2}/\d{2}/\d{4}", text)[:2]
    assert (_d(d2) - _d(d1)).days == 5


def test_phase4_pipeline_free_text_ambiguous_date_without_evidence_suppressed(tmp_path):
    out = _run(tmp_path, {"notes/short.txt": "Seen in OPD on 05/03/2026. BP 120/80. Advised rest.\n"})
    text = (out / "sanitized" / "notes" / "short.txt").read_text(encoding="utf-8")
    assert "05/03/2026" not in text and "[DATE]" in text and "BP 120/80" in text
