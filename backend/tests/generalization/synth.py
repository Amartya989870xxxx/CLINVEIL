"""Seeded generator of *unseen-style* synthetic hospital exports, with its own answer key.

Nothing here is taken from the organiser's practice data: patient names are
invented from Latin/Devanagari syllable pairs (and checked against the engine's
gazetteer, so detection must come from context), header/key vocabularies are
renamed variants that never occur in the practice files, ID prefixes and phone
formats are new, and PII is moved into alternate channels (filenames, metadata
paths, dynamic JSON keys, base64 payloads, CSV headers, logs, WhatsApp forwards).

``generate(seed)`` returns ``(files, truth)`` where ``truth`` lists every PII value
(``kind``, ``value``) and every clinical value that must survive.
"""

from __future__ import annotations

import base64
import contextlib
import json
import random
from dataclasses import dataclass, field

from clinveil.detection.lexicon import GIVEN_NAMES, NOT_NAME_WORDS, SURNAMES

SYL = [
    ("ka", "क"),
    ("ra", "र"),
    ("vi", "वि"),
    ("la", "ला"),
    ("na", "ना"),
    ("sa", "स"),
    ("tu", "तु"),
    ("mi", "मि"),
    ("ro", "रो"),
    ("de", "दे"),
    ("va", "व"),
    ("ni", "नि"),
    ("pa", "प"),
    ("ya", "या"),
    ("shi", "शि"),
    ("gu", "गु"),
    ("ha", "ह"),
    ("ju", "जु"),
    ("lo", "लो"),
    ("bha", "भा"),
    ("te", "ते"),
    ("mo", "मो"),
    ("dha", "धा"),
    ("ki", "कि"),
]
END = [("n", "न"), ("r", "र"), ("l", "ल"), ("sh", "श"), ("t", "त"), ("m", "म")]

HEADERS = {
    "name": ["Name of Patient", "Pt Full Name", "PatientFullName", "Rogi ka Naam", "मरीज़ का नाम", "Beneficiary Name"],
    "relative": ["Father/Husband Name", "Guardian Name", "Pita ka Naam", "पिता/पति का नाम", "Next of Kin"],
    "phone": ["Contact#", "Cell No", "Mobile Number", "संपर्क नंबर", "WhatsApp No", "Ph"],
    "mrn": ["Hospital ID", "CR No", "Patient Ref", "MRN", "Registration Number", "पंजीकरण संख्या"],
    "aadhaar": ["UID No", "Aadhar Card", "Aadhaar Number", "आधार"],
    "village": ["Gram/Mohalla", "Village Name", "Gaon", "ग्राम"],
    "dob": ["Date of Birth", "D.O.B.", "Janm Tithi", "जन्म तिथि"],
    "address": ["Residential Address", "Pata", "पता", "Address Line"],
    "pin": ["Postal Code", "Pincode", "पिन कोड"],
}
ID_PREFIX = ["SVH-26-", "RMC/2026/", "KGM2026-", "CHC/UNN/"]
PHONE_FMT = ["+91 {a} {b}", "0{a}-{b}", "{a}{b}", "+91-{a}{b}", "{a} {b}"]
CLINICAL = [
    "Tab Dolo 650 1-0-1 x 5 days",
    "BP 128/84",
    "SpO2 97%",
    "C/O fever x 4 days",
    "K/C/O DM2 x 6 yrs",
    "Inj Ceftriaxone 1 g IV x 7 days",
    "RBS 182 mg/dL",
    "Ward 3 (Surgery)",
    "Dr. Ramesh Iyer",
    "Parkinson's disease",
    "H/O TB 5 yrs back",
]


@dataclass
class Person:
    given: str
    surname: str
    given_deva: str
    surname_deva: str
    relative: str
    relative_deva: str
    phone_a: str
    phone_b: str
    mrn: str
    aadhaar: str
    village: str
    dob: str

    @property
    def name(self) -> str:
        return f"{self.given} {self.surname}"

    @property
    def phone(self) -> str:
        return self.phone_a + self.phone_b


@dataclass
class Truth:
    pii: list[tuple[str, str]] = field(default_factory=list)  # (kind, value): name tokens, digits, ids
    clinical: list[str] = field(default_factory=list)


def _word(rng: random.Random, n: int) -> tuple[str, str]:
    while True:
        parts = [rng.choice(SYL) for _ in range(n)] + [rng.choice(END)]
        lat = "".join(p[0] for p in parts).capitalize()
        deva = "".join(p[1] for p in parts)
        if lat.lower() not in GIVEN_NAMES | SURNAMES | NOT_NAME_WORDS and len(lat) >= 4:
            return lat, deva


def _aadhaar(rng: random.Random) -> str:
    from clinveil.detection.identifiers import verhoeff_valid

    while True:
        d = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(11))
        if verhoeff_valid(d):
            return d


def _person(rng: random.Random, n: int) -> Person:
    g, gd = _word(rng, 2)
    s, sd = _word(rng, 2)
    r, rd = _word(rng, 2)
    return Person(
        g,
        s,
        gd,
        sd,
        f"{r} {s}",
        f"{rd} {sd}",
        str(rng.randint(6, 9)) + f"{rng.randint(0, 9999):04d}",
        f"{rng.randint(0, 99999):05d}",
        rng.choice(ID_PREFIX) + f"{rng.randint(1000, 999999):06d}",
        _aadhaar(rng),
        _word(rng, 3)[0] + " " + rng.choice(["Khurd", "Kalan", "Pur"]),
        f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(1940, 2015)}",
    )


def _phone(rng: random.Random, p: Person, deva: bool = False) -> str:
    s = rng.choice(PHONE_FMT).format(a=p.phone_a, b=p.phone_b)
    return s.translate(str.maketrans("0123456789", "०१२३४५६७८९")) if deva else s


def generate(seed: int, n_patients: int = 12) -> tuple[dict[str, bytes], Truth]:
    rng = random.Random(seed)
    people = [_person(rng, i) for i in range(n_patients)]
    truth = Truth(clinical=list(CLINICAL))
    for p in people:
        truth.pii += [
            ("name", p.given),
            ("name", p.surname),
            ("name", p.given_deva),
            ("name", p.surname_deva),
            ("name", p.relative.split()[0]),
            ("digits", p.phone),
            ("id", p.mrn),
            ("digits", p.aadhaar),
            ("text", p.village),
            ("dob", p.dob),
        ]
    h = {k: rng.choice(v) for k, v in HEADERS.items()}
    files: dict[str, bytes] = {}

    # registration CSV with renamed headers
    cols = [
        h["mrn"],
        h["name"],
        h["relative"],
        h["dob"],
        h["address"],
        h["village"],
        h["pin"],
        h["phone"],
        h["aadhaar"],
        "Remarks",
    ]
    rows = [",".join(f'"{c}"' for c in cols)]
    for p in people:
        addr = f"H.No. {rng.randint(1, 499)}, near Old Water Tank, Tehsil Purwa, Distt. Unnao"
        rows.append(
            ",".join(
                f'"{v}"'
                for v in [
                    p.mrn,
                    p.name,
                    f"S/o {p.relative}",
                    p.dob,
                    addr,
                    p.village,
                    str(rng.randint(200000, 289999)),
                    _phone(rng, p),
                    " ".join([p.aadhaar[:4], p.aadhaar[4:8], p.aadhaar[8:]]),
                    "allergic to sulfa",
                ]
            )
        )
    files["reg/hospital_master.csv"] = "\n".join(rows).encode("utf-8")

    # UTF-16 TSV with Devanagari names and headers
    tsv = ["\t".join([h["mrn"], "नाम", "पिता का नाम", "मोबाइल"])]
    for p in people[:6]:
        tsv.append("\t".join([p.mrn, f"{p.given_deva} {p.surname_deva}", p.relative_deva, _phone(rng, p, deva=True)]))
    files["reg/local_register.tsv"] = "\n".join(tsv).encode("utf-16")

    # nested JSON with unseen keys, a dynamic name-keyed index, metadata path
    visits = []
    for i, p in enumerate(people):
        honor = rng.choice(["ji", "sahab", "didi", "behenji", "babu"])
        visits.append(
            {
                "encounter_no": f"V{1000 + i}",
                "pt": {"full_name": p.name, "cell": _phone(rng, p)},
                "hospital_ref": p.mrn,
                "consultant": "Dr. Ramesh Iyer",
                "observations": f"{p.given} {honor} ka BP 128/84, SpO2 97%. Tab Dolo 650 1-0-1 x 5 days.",
                "chief_complaint": "C/O fever x 4 days",
            }
        )
    p0 = people[0]
    files["opd/visits_export.json"] = json.dumps(
        {
            "_meta": {"exported_from": f"E:\\HMIS\\{p0.given}_{p0.surname}_{p0.mrn[-6:]}\\dump.json"},
            "encounters": visits,
            "lookup_by_patient": {p.name: p.mrn for p in people[:4]},
        },
        ensure_ascii=False,
        indent=1,
    ).encode("utf-8")

    # discharge notes: English and Devanagari labels, relative and address lines, filename with PII
    for p in people[:4]:
        note = (
            f"DISCHARGE SUMMARY\nPt. Name: {p.name}      Age/Sex: 52/M\nCR No: {p.mrn}\n"
            f"S/o {p.relative}\nAddress: H.No. 712, Mohalla Teen Batti, {p.village}, Tehsil Purwa, Distt. Unnao\n"
            f"Contact: {_phone(rng, p)}\nWard 3 (Surgery). K/C/O DM2 x 6 yrs. H/O TB 5 yrs back.\n"
            f"Treated with Inj Ceftriaxone 1 g IV x 7 days. {p.given} sahab ki halat ab theek hai.\n"
            f"Dr. Ramesh Iyer reviewed the patient.\n"
        )
        files[f"discharge/DS_{p.given}_{p.surname}_{p.mrn.replace('/', '-')}.txt"] = note.encode("utf-8")
    for p in people[4:7]:
        note = (
            f"डिस्चार्ज सारांश\nरोगी का नाम: {p.given_deva} {p.surname_deva}    आयु: 60 वर्ष\n"
            f"पति का नाम: {p.relative_deva}\nपंजीकरण संख्या: {p.mrn}\nमोबाइल: {_phone(rng, p, deva=True)}\n"
            f"RBS 182 mg/dL. Parkinson's disease.\n"
        )
        files[f"discharge/hindi_{rng.randint(100, 999)}.txt"] = note.encode("utf-8")

    # base64 attachment, visitor log, WhatsApp forward, ambulance-style CSV
    p = people[7]
    payload = base64.b64encode(f"Referral for {p.name} ({p.mrn}), contact {p.phone}.".encode()).decode()
    files["forms/referral.json"] = json.dumps(
        {"doc": "referral", "file": {"mime_type": "text/plain", "payload": payload}}
    ).encode()
    v1, v2 = people[8], people[9]
    files["notes/visitors.txt"] = (
        f"VISITOR LOG\n09:15 - {v1.name} (relative, bed 4), mob {_phone(rng, v1)}\n"
        f"10:30 - Dr. Ramesh Iyer took round.\n"
    ).encode()
    files["lab/forward_1.txt"] = (
        f"[02/03/26, 7:10 pm] {v2.given} Chachu: <attachment: report.pdf>\n"
        f"Report of {v2.given} ji  44 Y / M\nRBS 182 mg/dL\n"
        f"Koi problem ho to call karo {_phone(rng, v2)}\n"
    ).encode()
    v3 = people[10]
    files["misc/transport.csv"] = (
        f"trip,remarks\nT-1,oxygen given\nT-2,brought by {v3.name} {_phone(rng, v3)}\n"
    ).encode()
    # PII in a CSV header
    files["misc/vitals_grid.csv"] = (
        f"time,{people[0].mrn} {people[0].given},{people[1].mrn} {people[1].given}\n06:00,120/80,118/76\n"
    ).encode()
    return files, truth


def evaluate(out_dir, truth: Truth) -> dict:
    """Search every release channel (content + decoded base64, filenames, report, logs) for each PII value."""
    import re
    from pathlib import Path

    deva_digits = str.maketrans("०१२३४५६७८९", "0123456789")
    texts, names = [], []
    for p in Path(out_dir).rglob("*"):
        if p.is_file():
            names.append(p.relative_to(out_dir).as_posix())
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"[A-Za-z0-9+/]{24,}={0,2}", t):
                with contextlib.suppress(ValueError):
                    t += "\n" + base64.b64decode(m.group() + "=" * (-len(m.group()) % 4)).decode("utf-8", "ignore")
            texts.append(t)
    hay = ("\n".join(texts) + "\n" + "\n".join(names)).translate(deva_digits)
    digits = re.sub(r"(?<=\d)[\s\-./()_]+(?=\d)", "", hay)
    leaked = []
    for kind, value in truth.pii:
        if kind == "name":
            hit = re.search(r"(?<![\wऀ-ॿ])" + re.escape(value) + r"(?![\wऀ-ॿ])", hay, re.I)
        elif kind == "digits":
            hit = value in digits
        elif kind == "id":
            core = re.findall(r"\d+", value)[-1]
            hit = core in digits
        else:
            hit = value.lower() in hay.lower()
        if hit:
            leaked.append(kind)
    kept = sum(c in hay for c in truth.clinical)
    return {
        "pii_total": len(truth.pii),
        "pii_leaked": len(leaked),
        "leaked_kinds": sorted(leaked),
        "clinical_total": len(truth.clinical),
        "clinical_kept": kept,
    }
