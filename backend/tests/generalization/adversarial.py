"""Phase 2.1 adversarial generator: the attack classes of the independent audit, on unseen data.

Independent of ``synth.py`` and of the practice dataset: names are built from a
separate syllable inventory (and rejected if the engine's gazetteer or stop lists
know them, so detection must come from context), and every case uses a
resource type, column header, relationship format, digit script, encoding or ID
prefix that neither the practice data nor the earlier tests use.

``cases(seed)`` returns a list of :class:`Case` (files + values that must vanish +
values that must survive), grouped by ``category`` so the test reports per-class
results instead of one opaque number.
"""

from __future__ import annotations

import base64
import html
import json
import random
import urllib.parse
from dataclasses import dataclass, field

from clinveil.detection import lexicon
from clinveil.detection.lexicon import GIVEN_NAMES, NOT_NAME_WORDS, SURNAMES

KNOWN_PLACES = getattr(lexicon, "KNOWN_PLACES", lexicon.UP_DISTRICTS)  # also runs against Phase 2 code

_SYL = ["zor", "vel", "tam", "qui", "dar", "fen", "mak", "rov", "sil", "nub", "jor", "kes", "lun", "pav", "hes", "gar"]
_END = ["ith", "ova", "esh", "and", "ule", "ika", "orn", "ash"]
_DEVA_SYL = ["ज़ो", "वे", "ता", "कि", "दा", "फे", "मा", "रो", "सि", "नु", "जो", "के"]
_DEVA_END = ["रथ", "वा", "श", "न्द", "ला", "का"]
_DIGIT_SCRIPTS = {  # 0-9 in each script
    "bengali": "০১২৩৪৫৬৭৮৯",
    "gurmukhi": "੦੧੨੩੪੫੬੭੮੯",
    "gujarati": "૦૧૨૩૪૫૬૭૮૯",
    "tamil": "௦௧௨௩௪௫௬௭௮௯",
    "telugu": "౦౧౨౩౪౫౬౭౮౯",
    "kannada": "೦೧೨೩೪೫೬೭೮೯",
    "malayalam": "൦൧൨൩൪൫൬൭൮൯",
    "odia": "୦୧୨୩୪୫୬୭୮୯",
    "fullwidth": "０１２３４５６７８９",
}
_STOP = NOT_NAME_WORDS | GIVEN_NAMES | SURNAMES | KNOWN_PLACES


@dataclass
class Case:
    category: str
    files: dict[str, bytes]
    vanish: list[str]
    keep: list[str] = field(default_factory=list)
    fhir: bool = False


def _name(rng: random.Random) -> str:
    while True:
        w = (rng.choice(_SYL) + rng.choice(_END)).capitalize()
        if w.casefold() not in _STOP:
            return w


def _person(rng: random.Random) -> tuple[str, str]:
    return _name(rng), _name(rng)


def _deva(rng: random.Random) -> str:
    return rng.choice(_DEVA_SYL) + rng.choice(_DEVA_END)


def _phone(rng: random.Random) -> str:
    return str(rng.choice("6789")) + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _in_script(digits: str, script: str) -> str:
    return "".join(_DIGIT_SCRIPTS[script][int(d)] for d in digits)


def _bundle(patient: dict, resources: list[dict]) -> bytes:
    entries = [{"fullUrl": "urn:uuid:pt-0001", "resource": {"resourceType": "Patient", "id": "pt-0001", **patient}}]
    for i, r in enumerate(resources):
        entries.append({"fullUrl": f"urn:uuid:res-{i:04d}", "resource": {"id": f"res-{i:04d}", **r}})
    return json.dumps({"resourceType": "Bundle", "id": "bx", "type": "collection", "entry": entries}).encode()


SUBJECT = {"reference": "urn:uuid:pt-0001"}


def cases(seed: int) -> list[Case]:
    rng = random.Random(seed)
    out: list[Case] = []
    g, s = _person(rng)
    rg, rs = _person(rng)
    while len({g, s, rg, rs}) < 4 or g[:4] == rg[:4]:  # distinct people (a doctor may not share the surname)
        rg, rs = _person(rng)
    ph, ph2 = _phone(rng), _phone(rng)
    uhid = f"KGX-{2020 + seed % 7}-{rng.randint(1000000, 9999999)}"

    # 1. unseen FHIR resources carrying free text
    out.append(
        Case(
            "fhir_unseen_resources",
            {
                "fhir/b.json": _bundle(
                    {"name": [{"text": f"{g} {s}"}], "identifier": [{"system": "urn:x:uhid", "value": uhid}]},
                    [
                        {
                            "resourceType": "Procedure",
                            "status": "completed",
                            "subject": SUBJECT,
                            "code": {"text": "Lower segment caesarean section"},
                            "note": [{"text": f"Consent signed by husband {rg} {rs}, mob {ph}."}],
                        },
                        {
                            "resourceType": "Immunization",
                            "status": "completed",
                            "patient": SUBJECT,
                            "vaccineCode": {"text": "Tdap"},
                            "note": [{"text": f"Card shown by S/o {rg} {rs}"}],
                        },
                        {
                            "resourceType": "ServiceRequest",
                            "status": "active",
                            "intent": "order",
                            "subject": SUBJECT,
                            "code": {"text": "Serum ferritin"},
                            "note": [{"text": f"Call {g} {s} on {ph2} with report"}],
                        },
                        {
                            "resourceType": "CarePlan",
                            "status": "active",
                            "intent": "plan",
                            "subject": SUBJECT,
                            "description": f"Home care plan for {g} {s}; ANC visits monthly",
                        },
                        {
                            "resourceType": "AllergyIntolerance",
                            "patient": SUBJECT,
                            "code": {"text": "Penicillin"},
                            "note": [{"text": f"Reported by attendant {rg} {rs}"}],
                        },
                        {
                            "resourceType": "Communication",
                            "status": "completed",
                            "subject": SUBJECT,
                            "payload": [{"contentString": f"Patient: {g} {s} discharged, Hb 10.2 g/dL"}],
                        },
                    ],
                )
            },
            vanish=[g, s, rg, rs, ph, ph2, uhid.split("-")[-1]],
            keep=[
                "Lower segment caesarean section",
                "Tdap",
                "Serum ferritin",
                "ANC visits monthly",
                "Penicillin",
                "Hb 10.2 g/dL",
            ],
            fhir=True,
        )
    )

    # 2. new clinical CSV columns next to identity columns
    cols = {
        "Sputum AFB": "Negative",
        "Serum Ferritin": "12 ng/mL",
        "Echo LVEF": "55%",
        "Dialysis Mode": "HD",
        "Diet Plan": "Diabetic diet",
        "Line Care": "Daily dressing",
        "Cell Type": "Lymphocytes",
        "Gram Reaction": "Gram negative",
        "Birth Order": "2",
        "Mother Blood Group": "B+",
        "Care Level": "Step-down",
        "Code Status": "Full code",
    }
    header = "Reg Ref,Patient Name,Guardian Name," + ",".join(cols)
    row = f"{uhid},{g} {s},{rg} {rs}," + ",".join(cols.values())
    out.append(
        Case(
            "clinical_columns",
            {"lab/sheet.csv": f"{header}\n{row}\n".encode()},
            vanish=[g, s, rg, rs],
            keep=list(cols.values()) + list(cols),
        )
    )

    # 3. relationship formats (patient before and after the marker)
    d1, d2 = _deva(rng), _deva(rng)
    rel_lines = [
        f"{g}, D/o {rg} {rs}, admitted with fever.",
        f"Smt. {g} w/o {rg} {rs} reviewed in OPD.",
        f"{g} {s} Son of {rg} came for dressing.",
        f"Attendant: {rg} {rs} (husband)",
        f"मरीज़ {d1} पुत्री {d2} भर्ती",
        f"Address: C/O {rg} {rs}, H.No. 41, Gali No 3",
    ]
    out.append(
        Case(
            "relationship_formats",
            {f"notes/r{i}.txt": t.encode() for i, t in enumerate(rel_lines)},
            vanish=[g, rg, rs, d1, d2],
            keep=["admitted with fever", "reviewed in OPD", "came for dressing", "भर्ती"],
        )
    )

    # 4. phones in other digit scripts
    script = rng.choice(sorted(_DIGIT_SCRIPTS))
    p_script = _in_script(ph, script)
    out.append(
        Case(
            f"digits_{script}",
            {"notes/d.txt": f"Mob: {p_script}, BP 130/80".encode()},
            vanish=[p_script],
            keep=["BP 130/80"],
        )
    )

    # 5. encodings: %-encoded path, HTML entities in a narrative, URL-safe base64
    enc_name = urllib.parse.quote(f"{g} {s}")
    narrative = "".join(f"&#{ord(c)};" if i % 2 == 0 else c for i, c in enumerate(f"{g} {s}"))
    b64 = base64.urlsafe_b64encode(f"Name: {g} {s}?? ph {ph}>>".encode()).decode().rstrip("=")
    out.append(
        Case(
            "encodings",
            {
                "reg/r.csv": f"Reg Ref,Patient Name\n{uhid},{g} {s}\n".encode(),
                "x/meta.json": json.dumps(
                    {"_meta": {"source": f"file:///exp/{enc_name}/{urllib.parse.quote(uhid)}.json"}, "rows": [{"k": 1}]}
                ).encode(),
                "fhir/n.json": _bundle(
                    {
                        "name": [{"text": f"{g} {s}"}],
                        "text": {
                            "status": "generated",
                            "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{narrative} &amp; family</p></div>',
                        },
                    },
                    [],
                ),
                "notes/b.txt": f"scan: {b64} end".encode(),
            },
            vanish=[g, s, ph, uhid.split("-")[-1]],
            keep=["family"],
            fhir=True,
        )
    )

    # 6. unusual ID prefixes reappearing in filenames and text
    adm = f"SGX/IP/{seed % 90 + 10}/{rng.randint(10000, 99999)}"
    out.append(
        Case(
            "id_prefixes",
            {
                "reg/adm.csv": f"IP Number,Patient Name\n{adm},{g} {s}\n".encode(),
                f"ds/{adm.replace('/', '-')}_summary.txt": f"IP {adm}: discharged stable, Hb 11 g/dL".encode(),
            },
            vanish=[adm.split("/")[-1], g, s],
            keep=["discharged stable", "Hb 11 g/dL"],
        )
    )

    # 7. similar-name patients + a doctor sharing a given name
    g2 = g[:-1] + ("a" if g[-1] != "a" else "e")
    out.append(
        Case(
            "similar_names_and_doctor",
            {
                "reg/p.csv": f"Reg Ref,Patient Name\n{uhid},{g} {s}\nKGX-1-{seed:07d},{g2} {s}\n".encode(),
                "notes/n.txt": f"Dr. {g} {rs} saw {g2} {s} today. {g} {s} stable on Tab Metformin 500 mg BD.".encode(),
            },
            vanish=[f"{g2} {s}", f"{g} {s}"],
            keep=[f"Dr. {g} {rs}", "Tab Metformin 500 mg BD"],
        )
    )
    return out


def html_unescape(s: str) -> str:
    return html.unescape(s)
