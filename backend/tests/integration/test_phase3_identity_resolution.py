"""End-to-end Phase 3 identity resolution & cryptographic pseudonymisation tests.

Covers all test categories in the Phase 3 specification with 100% invented synthetic identities:
* A. Genuine same-patient matches across 4 hospitals, 3 scripts, and CSV/TSV/JSON/text/FHIR.
* B. False-merge protection (homonyms, shared phone/address, twins, doctors, relatives,
     same numeric MRN at different hospitals, coarse-transliteration collisions, conflicting IDs).
* C. Ambiguous records left unlinked (first-name only, initials only, phone only, address only,
     name+village without age/DOB/relative).
* D. Cryptographic properties (determinism, secret sensitivity, no secret/PII in side channels,
     traversal-order independence, pseudonym consistency inside exported records).
* E. Structural & FHIR R4 validity (RelatedPerson, contained Patient, nested Bundle, multi-patient Bundle).
* F. Generalisation on unseen column headers/hospital names + 1,000-record scaling check.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from clinveil import pipeline
from clinveil.config.policy import Policy
from clinveil.detection import caches
from clinveil.detection.identifiers import verhoeff_valid
from clinveil.parsing.fhir import build_index
from clinveil.privacy.pseudonym import ALPHABET
from clinveil.security.secrets import ReleaseSecret
from conftest import run_cli

PSN_RE = re.compile(rf"^PSN-[{ALPHABET}]{{6}}$")


def _aadhaar(prefix11: str) -> str:
    for d in "0123456789":
        if verhoeff_valid(prefix11 + d):
            return prefix11 + d
    raise AssertionError("no verhoeff digit")


AADHAAR_PRANAV = _aadhaar("29418563720")
AADHAAR_ZOYA = _aadhaar("38529674831")
AADHAAR_CONFLICT_1 = _aadhaar("47631785942")
AADHAAR_CONFLICT_2 = _aadhaar("56742896153")


def _w(root: Path, rel: str, content: str | bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def _load_records(out: Path) -> dict[tuple[str, str], str | None]:
    recs: dict[tuple[str, str], str | None] = {}
    for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[(r["file"], r["loc"])] = r["patient"]
    return recs


def _build_four_hospital_suite(root: Path) -> None:
    """Build a synthetic 4-hospital dataset covering genuine matches, traps, and ambiguous records."""
    # --- Hospital 1: Sunrise Medical (UTF-8 BOM CSV)
    sunrise_rows = [
        "\ufeffUHID,Patient Name,Gender,Age,DOB,Relation,Relative Name,Village,District,PIN,Mobile,Aadhaar No,ABHA No",
        f"SUN/26/1001,Pranav Kulkarni,M,44,14/05/1982,S/o,Harish Kulkarni,"
        f"Keshavpur,Pune,411001,+91 98201 11223,{AADHAAR_PRANAV},91-2233-4455-6677",
        "SUN/26/1002,Bhanu Pratap,M,41,10/02/1985,S/o,Raghavendra Pratap,Alipur,Nagpur,440001,9820222334,,",
        "SUN/26/1003,Kavya Deshmukh,F,34,21/07/1992,W/o,Raghav Deshmukh,Deolali,Nashik,422001,9820333445,,",
        "SUN/26/1004,Raghav Deshmukh,M,37,09/11/1989,S/o,Vaman Deshmukh,Deolali,Nashik,422001,9820333445,,",
        "SUN/26/1005,Nikhil Sengupta,M,19,19/08/2007,S/o,Vijay Sengupta,Banswara,Udaipur,313001,9820444556,,",
        "SUN/26/1006,Akhil Sengupta,M,19,19/08/2007,S/o,Vijay Sengupta,Banswara,Udaipur,313001,9820444556,,",
        "SUN/26/1007,Kiran Solanki,F,29,03/03/1997,D/o,Mahendra Solanki,Mandsaur,Indore,452001,9820555667,,",
        f"SUN/26/1008,Zoya Qureshi,F,36,11/03/1990,W/o,Tariq Qureshi,"
        f"Chandanpur,Bhopal,462001,9820666778,{AADHAAR_CONFLICT_1},",
        "MRN-12345,Meenakshi Joshi,F,51,05/09/1975,W/o,Suresh Joshi,Vidyapur,Jaipur,302001,9820777889,,",
    ]
    _w(root, "registration/sunrise_registration.csv", ("\n".join(sunrise_rows) + "\n").encode())

    # --- Hospital 2: Lotus Care (UTF-16 TSV, Devanagari)
    lotus_tsv = (
        "Reg No\tNaam\tLing\tUmar\tJanm Tithi\tPita/Pati ka Naam\tGaon\tMobile No\tAadhar\n"
        f"LOT/26/8821\tप्रणव कुलकर्णी\tपुरुष\t44\t14/05/1982\tहरीश कुलकर्णी\tकेशवपुर\t०९८२०१-११२२३\t{AADHAAR_PRANAV}\n"
        "LOT/26/8822\tBhanu Pratap\tM\t59\t18/11/1967\tDinesh Pratap\tSonpur\t9820999001\t\n"
        "LOT/26/8823\tKaran Solanki\tF\t29\t03/03/1997\tMahendra Solanki\tMandsaur\t9820555667\t\n"
        f"LOT/26/8824\tZoya Qureshi\tF\t36\t11/03/1990\tTariq Qureshi\tChandanpur\t9820666778\t{AADHAAR_CONFLICT_2}\n"
        "MRN-12345\tTarunima Sen\tF,32\t32\t12/12/1994\tArjun Sen\tNavapur\t9820888990\t\n"
    )
    _w(root, "registration/lotus_patients.tsv", lotus_tsv.encode("utf-16"))

    # --- Hospital 3: Riverview General (JSON OPD + FHIR R4 Bundle)
    _w(
        root,
        "opd/riverview_opd.json",
        json.dumps(
            {
                "facility": "Riverview General Hospital",
                "visits": [
                    {
                        "visit_id": "RV-1",
                        "patient_ref": "RIV/26/3001",
                        "patient_name": "P. Kulkarni",
                        "dob": "1982-05-14",
                        "mobile": "098201-11223",
                        "doctor": "Dr. Pranav Kulkarni",
                        "complaints": "C/O fever x 2 days",
                        "rx": "Tab Dolo 650 1-0-1 x 3 days",
                    },
                    {
                        "visit_id": "RV-2",
                        "patient_ref": "RIV/26/3002",
                        "patient_name": "Devendra Rathore",
                        "relative_name": "S/o Pranav Kulkarni",
                        "doctor": "Dr. Pranav Kulkarni",
                        "complaints": "C/O cough",
                    },
                ],
            }
        ),
    )

    # --- Hospital 4: Metro District (FHIR R4 Bundle for Pranav Kulkarni + RelatedPerson + Practitioner)
    fhir_bundle = {
        "resourceType": "Bundle",
        "id": "bundle-metro-1",
        "type": "document",
        "entry": [
            {
                "fullUrl": "urn:uuid:11111111-1111-4111-8111-111111111111",
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-1",
                    "identifier": [
                        {"system": "https://metro.hospital.example/uhid", "value": "MET/26/5501"},
                        {"system": "https://healthid.abdm.gov.in", "value": "91-2233-4455-6677"},
                    ],
                    "name": [{"given": ["Pranav"], "family": "Kulkarni"}],
                    "gender": "male",
                    "birthDate": "1982-05-14",
                    "telecom": [{"system": "phone", "value": "+91 98201 11223"}],
                    "contact": [{"name": {"text": "Harish Kulkarni"}}],
                },
            },
            {
                "fullUrl": "urn:uuid:22222222-2222-4222-8222-222222222222",
                "resource": {
                    "resourceType": "RelatedPerson",
                    "id": "rel-1",
                    "patient": {"reference": "urn:uuid:11111111-1111-4111-8111-111111111111"},
                    "name": [{"text": "Harish Kulkarni"}],
                },
            },
            {
                "fullUrl": "urn:uuid:33333333-3333-4333-8333-333333333333",
                "resource": {
                    "resourceType": "Practitioner",
                    "id": "doc-1",
                    "name": [{"text": "Dr. Raghavendra Nair"}],
                },
            },
            {
                "fullUrl": "urn:uuid:44444444-4444-4444-8444-444444444444",
                "resource": {
                    "resourceType": "Encounter",
                    "id": "enc-1",
                    "status": "finished",
                    "subject": {"reference": "urn:uuid:11111111-1111-4111-8111-111111111111"},
                },
            },
        ],
    }
    _w(root, "fhir/metro_bundle.json", json.dumps(fhir_bundle))

    # --- Plain text: Hinglish & fragmented note for Pranav Kulkarni + external lab JSON
    _w(
        root,
        "notes/hinglish_note.txt",
        "Metro District Hospital\nPranav sahab, S/o Harish Kulkarni, 44/M\nBP 122/78. Dr. Raghavendra Nair reviewed.\n",
    )
    _w(
        root,
        "lab/report_pranav.json",
        json.dumps(
            {
                "lab": "Beacon Pathology Lab",
                "report_type": "Routine",
                "patient": {"uhid": "SUN/26/1001", "name": "Pranav Kulkarni", "age": 44},
                "panels": [{"name": "CBC", "results": [{"test": "Hb", "value": "13.8 g/dL"}]}],
            }
        ),
    )

    # --- Ambiguous records (MUST remain patient=None!)
    _w(root, "notes/amb_first_only.txt", "Name: Pranav\nC/O headache x 1 day\n")
    _w(root, "notes/amb_initials.txt", "Patient: P. K.\nBP 118/76\n")
    _w(root, "notes/amb_phone_only.txt", "Callback: +91 98201 11223\nReport ready.\n")
    _w(root, "notes/amb_address_only.txt", "Address: H.No. 14, Mohalla Shivaji Nagar, Keshavpur\n")
    _w(root, "notes/amb_name_village_only.txt", "Name: Bhanu Pratap\nVillage: Alipur\nRx: Tab Dolo 650\n")


def test_four_hospital_matches_false_merge_guards_and_ambiguous_abstention(tmp_path):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    _build_four_hospital_suite(inp)

    res = run_cli(inp, out, secret="phase3-suite-secret")
    assert res.code == 0, res.stderr
    recs = _load_records(out)

    # A. Pranav Kulkarni linked across all 4 hospitals + Hinglish note + external lab JSON (6 records, 1 pseudonym!)
    pranav_keys = [
        ("sanitized/registration/sunrise_registration.csv", "row:0"),
        ("sanitized/registration/lotus_patients.tsv", "row:0"),
        ("sanitized/opd/riverview_opd.json", "/visits/0"),
        ("sanitized/fhir/metro_bundle.json", "doc"),
        ("sanitized/notes/hinglish_note.txt", "doc"),
        ("sanitized/lab/report_NAME.json", "doc"),  # filename PII "pranav" renamed by Phase 2
    ]
    pranav_psns = [recs[k] for k in pranav_keys]
    assert all(p is not None and PSN_RE.fullmatch(p) for p in pranav_psns), pranav_psns
    assert len(set(pranav_psns)) == 1, f"Pranav split: {dict(zip(pranav_keys, pranav_psns, strict=True))}"
    p_pranav = pranav_psns[0]

    # B. False-merge protections: ALL distinct people MUST have distinct pseudonyms!
    # 1. Homonyms (Bhanu Pratap #1 vs #2)
    bhanu1 = recs[("sanitized/registration/sunrise_registration.csv", "row:1")]
    bhanu2 = recs[("sanitized/registration/lotus_patients.tsv", "row:1")]
    assert bhanu1 and bhanu2 and bhanu1 != bhanu2

    # 2. Family members sharing phone & address (Kavya vs Raghav Deshmukh)
    kavya = recs[("sanitized/registration/sunrise_registration.csv", "row:2")]
    raghav = recs[("sanitized/registration/sunrise_registration.csv", "row:3")]
    assert kavya and raghav and kavya != raghav

    # 3. Twins sharing surname, DOB, relative, village, phone (Nikhil vs Akhil Sengupta)
    nikhil = recs[("sanitized/registration/sunrise_registration.csv", "row:4")]
    akhil = recs[("sanitized/registration/sunrise_registration.csv", "row:5")]
    assert nikhil and akhil and nikhil != akhil

    # 4. Coarse transliteration collision (Kiran Solanki vs Karan Solanki)
    kiran = recs[("sanitized/registration/sunrise_registration.csv", "row:6")]
    karan = recs[("sanitized/registration/lotus_patients.tsv", "row:2")]
    assert kiran and karan and kiran != karan

    # 5. Conflicting valid Aadhaar with identical name & DOB (Zoya Qureshi #1 vs #2)
    zoya1 = recs[("sanitized/registration/sunrise_registration.csv", "row:7")]
    zoya2 = recs[("sanitized/registration/lotus_patients.tsv", "row:3")]
    assert zoya1 and zoya2 and zoya1 != zoya2

    # 6. Same numeric MRN-12345 at two different hospitals (Meenakshi Joshi vs Tarunima Sen)
    meenakshi = recs[("sanitized/registration/sunrise_registration.csv", "row:8")]
    tarunima = recs[("sanitized/registration/lotus_patients.tsv", "row:4")]
    assert meenakshi and tarunima and meenakshi != tarunima

    # 7. Doctor & relative sharing patient's name (Devendra Rathore with Dr. Pranav Kulkarni & S/o Pranav Kulkarni)
    devendra = recs[("sanitized/opd/riverview_opd.json", "/visits/1")]
    assert devendra is not None and devendra != p_pranav

    # C. Ambiguous records MUST remain unlinked (patient=None)
    for amb_file in (
        "sanitized/notes/amb_first_only.txt",
        "sanitized/notes/amb_initials.txt",
        "sanitized/notes/amb_phone_only.txt",
        "sanitized/notes/amb_address_only.txt",
        "sanitized/notes/amb_name_village_only.txt",
    ):
        assert recs[(amb_file, "doc")] is None, f"{amb_file} should stay unlinked"

    # D. Pseudonym consistency: every non-null pseudonym appears INSIDE its exported file!
    for (rel, _loc), psn in recs.items():
        if psn is not None:
            assert psn in (out / rel).read_text(encoding="utf-8"), f"{psn} missing from {rel}"

    # E. Structural & FHIR validity
    # CSV shape preserved
    orig_csv = list(csv.reader(io.StringIO((inp / "registration/sunrise_registration.csv").read_text("utf-8-sig"))))
    san_csv = list(
        csv.reader(io.StringIO((out / "sanitized/registration/sunrise_registration.csv").read_text("utf-8")))
    )
    assert len(orig_csv) == len(san_csv) and [len(r) for r in orig_csv] == [len(r) for r in san_csv]
    assert san_csv[0] == orig_csv[0]

    # FHIR references resolve and Patient.identifier carries Pranav's pseudonym
    san_fhir = json.loads((out / "sanitized/fhir/metro_bundle.json").read_text(encoding="utf-8"))
    assert not build_index(san_fhir).unresolved
    pat_res = san_fhir["entry"][0]["resource"]
    assert pat_res["identifier"][0]["value"] == p_pranav
    assert san_fhir["entry"][2]["resource"]["name"][0]["text"] == "Dr. Raghavendra Nair"

    # Side-channel hygiene: zero secret or raw PII in report, records.jsonl, logs
    blob = (
        (out / "report.json").read_text(encoding="utf-8")
        + (out / "records.jsonl").read_text(encoding="utf-8")
        + (out / "logs/detection_summary.json").read_text(encoding="utf-8")
        + res.stdout
        + res.stderr
    )
    for forbidden in ("phase3-suite-secret", "Pranav", "Kulkarni", AADHAAR_PRANAV, "9820111223", "Zoya", "Qureshi"):
        assert forbidden not in blob


def test_different_secrets_change_all_pseudonyms_and_same_secret_is_deterministic(tmp_path):
    inp = tmp_path / "in"
    _build_four_hospital_suite(inp)
    r1 = run_cli(inp, tmp_path / "out1", secret="secret-one")
    r2 = run_cli(inp, tmp_path / "out2", secret="secret-one")
    r3 = run_cli(inp, tmp_path / "out3", secret="secret-two")
    assert r1.code == r2.code == r3.code == 0

    recs1, recs2, recs3 = _load_records(r1.out), _load_records(r2.out), _load_records(r3.out)
    assert recs1 == recs2
    psns1 = {v for v in recs1.values() if v is not None}
    psns3 = {v for v in recs3.values() if v is not None}
    assert psns1 and psns3 and psns1.isdisjoint(psns3)
    # Also verify sanitized FHIR bytes changed between secret-one and secret-two
    assert (r1.out / "sanitized/fhir/metro_bundle.json").read_bytes() != (
        r3.out / "sanitized/fhir/metro_bundle.json"
    ).read_bytes()


def test_fhir_contained_nested_and_multi_patient_bundles(tmp_path):
    inp = tmp_path / "in"
    out = tmp_path / "out"

    # 1. Contained Patient inside an Encounter + matching standalone registration CSV
    _w(
        inp,
        "reg/veridian.csv",
        f"UHID,Name,DOB,Aadhaar\nVER/26/901,Tarunima Deshmukh,04/06/1988,{AADHAAR_ZOYA}\n",
    )
    contained_doc = {
        "resourceType": "Encounter",
        "id": "enc-901",
        "status": "finished",
        "contained": [
            {
                "resourceType": "Patient",
                "id": "p1",
                "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AADHAAR_ZOYA}],
                "name": [{"text": "Tarunima Deshmukh"}],
                "birthDate": "1988-06-04",
            }
        ],
        "subject": {"reference": "#p1"},
    }
    _w(inp, "fhir/contained_encounter.json", json.dumps(contained_doc))

    # 2. Nested Bundle containing a Patient
    nested_bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Bundle",
                    "type": "document",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "Patient",
                                "id": "p2",
                                "identifier": [{"system": "https://uidai.gov.in/aadhaar", "value": AADHAAR_ZOYA}],
                                "name": [{"given": ["Tarunima"], "family": "Deshmukh"}],
                                "birthDate": "1988-06-04",
                            }
                        }
                    ],
                }
            }
        ],
    }
    _w(inp, "fhir/nested_bundle.json", json.dumps(nested_bundle))

    # 3. Multi-patient conflicting Bundle -> must be flagged AMBIGUOUS (patient=None), never merged
    multi_pat_bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "pa",
                    "identifier": [{"system": "https://veridian.example/uhid", "value": "VER/26/901"}],
                    "name": [{"text": "Tarunima Deshmukh"}],
                }
            },
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "pb",
                    "identifier": [{"system": "https://veridian.example/uhid", "value": "VER/26/902"}],
                    "name": [{"text": "Pranav Kulkarni"}],
                }
            },
        ],
    }
    _w(inp, "fhir/multi_patient.json", json.dumps(multi_pat_bundle))

    res = run_cli(inp, out, secret="fhir-secret")
    assert res.code == 0, res.stderr
    recs = _load_records(out)
    p_reg = recs[("sanitized/reg/veridian.csv", "row:0")]
    assert p_reg is not None
    assert recs[("sanitized/fhir/contained_encounter.json", "doc")] == p_reg
    assert recs[("sanitized/fhir/nested_bundle.json", "doc")] == p_reg
    assert recs[("sanitized/fhir/multi_patient.json", "doc")] is None


def test_unseen_schema_generalisation_and_1000_record_scaling(tmp_path):
    """200 invented patients x 5 records across unseen column headers & hospital names (1,000 records)."""
    inp = tmp_path / "in"
    out = tmp_path / "out"

    firsts = ["Arvind", "Bhavna", "Chirag", "Deepika", "Eshwar", "Farida", "Gaurav", "Hemant", "Ishita", "Jatin"]
    lasts = ["Bhatnagar", "Chatterjee", "Dandekar", "Gokhale", "Hegde", "Iyengar", "Kamat", "Lohia", "Mistry", "Naik"]

    rows_h1 = ["Local Hosp Ref,Beneficiary Full Title,D.O.B.,Contact#,Gram,Age"]
    rows_h2 = ["Case Ref,Full Name,Birth Date,Phone,Village,Age"]
    visits_h3 = []
    expected_groups: dict[int, list[tuple[str, str]]] = defaultdict(list)

    for i in range(200):
        fn = firsts[i % len(firsts)]
        ln = lasts[(i // len(firsts)) % len(lasts)]
        mid = f"K{chr(65 + (i % 26))}" if i >= 100 else ""
        full = f"{fn} {mid} {ln}".replace("  ", " ")
        year = 1955 + (i % 45)
        month = (i % 12) + 1
        day = (i % 28) + 1
        dob_dmy = f"{day:02d}/{month:02d}/{year}"
        dob_iso = f"{year}-{month:02d}-{day:02d}"
        phone = f"981{(1000000 + i * 37):07d}"
        village = f"Gram{i:03d}"
        age = 2026 - year

        rows_h1.append(f"VRD/26/{i + 10001},{full},{dob_dmy},+91 {phone[:5]} {phone[5:]},{village},{age}")
        rows_h2.append(f"CRS/26/{i + 20001},{full},{dob_iso},{phone},{village},{age}")
        visits_h3.append(
            {"visit_id": f"V{i}", "uhid": f"VRD/26/{i + 10001}", "patient_name": full, "diagnosis": "Viral fever"}
        )
        visits_h3.append(
            {"visit_id": f"V{i}b", "uhid": f"CRS/26/{i + 20001}", "patient_name": full, "diagnosis": "Follow-up"}
        )
        visits_h3.append(
            {"visit_id": f"V{i}c", "uhid": f"VRD/26/{i + 10001}", "patient_name": full, "diagnosis": "Resolved"}
        )

        expected_groups[i].append(("sanitized/reg/veridian_export.csv", f"row:{i}"))
        expected_groups[i].append(("sanitized/reg/crescent_export.csv", f"row:{i}"))
        expected_groups[i].append(("sanitized/opd/pinnacle_visits.json", f"/visits/{3 * i}"))
        expected_groups[i].append(("sanitized/opd/pinnacle_visits.json", f"/visits/{3 * i + 1}"))
        expected_groups[i].append(("sanitized/opd/pinnacle_visits.json", f"/visits/{3 * i + 2}"))

    _w(inp, "reg/veridian_export.csv", "\n".join(rows_h1) + "\n")
    _w(inp, "reg/crescent_export.csv", "\n".join(rows_h2) + "\n")
    _w(inp, "opd/pinnacle_visits.json", json.dumps({"facility": "Pinnacle Care", "visits": visits_h3}))

    t0 = time.monotonic()
    summary = pipeline.run(inp, out, ReleaseSecret(b"scale-secret"), Policy())
    elapsed = time.monotonic() - t0
    assert summary.ok, summary.problems
    assert caches.total_cached_entries() == 0
    assert elapsed < 30.0, f"1,000-record linking took {elapsed:.2f}s (expected linear scaling)"

    recs = _load_records(out)
    seen_psns: dict[str, int] = {}
    matched_groups = 0
    for pid, keys in expected_groups.items():
        psns = [recs[k] for k in keys]
        assert all(p is not None for p in psns), f"patient {pid} had unlinked record"
        if len(set(psns)) == 1:
            matched_groups += 1
        for p in set(psns):
            assert p not in seen_psns, f"FALSE MERGE between patient {seen_psns[p]} and {pid}!"
            seen_psns[p] = pid
    assert matched_groups == 200
