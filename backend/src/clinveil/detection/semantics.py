"""Semantic classification of field labels (CSV/TSV headers, JSON keys, key paths).

A label is reduced to normalised *concept tokens*:

* camelCase and separators are split (``FirstName`` -> ``first name``,
  ``patient's_name`` -> ``patient name``, ``Contact#`` -> ``contact``);
* Devanagari label words are mapped to romanised concepts (``मरीज़ का नाम`` ->
  ``mareez naam``) and unknown Devanagari words are romanised;
* noise words (``of``, ``no``, ``number``, ``ka``…) are dropped;
* unknown tokens of 5+ letters are fuzzy-matched (edit distance 1, or 2 for 8+
  letters) against the concept vocabulary, so ``Pateint Nmae`` and ``Adhaar``
  still classify.

Rules are applied from most to least specific (identifiers and dates before
names, names before places, places before clinical/free text). Generic labels
(``name``, ``first``, ``line``, ``value``) are refined with their parent path:
``patients/*/name/first`` is a patient name, ``guardian/name`` a relative,
``facility/name`` an organisation, ``panels/*/name`` clinical.

The result says what a field *holds*. It never causes a schema label itself to
be redacted: only values (or labels that themselves contain personal values) are.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from clinveil.detection.translit import romanize


class Sem(str, Enum):
    PERSON_NAME = "person_name"  # patient or unknown-role person
    RELATIVE_NAME = "relative_name"
    DOCTOR_NAME = "doctor_name"  # clinicians: preserved
    STAFF = "staff"  # hospital personnel / system users: preserved
    ORGANIZATION = "organization"  # hospital, lab, department: preserved
    RELATION = "relation"  # "S/o", "W/o" values: preserved
    PHONE = "phone"
    EMAIL = "email"
    AADHAAR = "aadhaar"
    ABHA_NUMBER = "abha_number"
    ABHA_ADDRESS = "abha_address"
    PAN = "pan"
    MRN = "mrn"
    INSURANCE_ID = "insurance_id"
    ADDRESS = "address"
    HOUSE = "house"
    LOCALITY = "locality"
    LANDMARK = "landmark"
    VILLAGE = "village"
    TEHSIL = "tehsil"  # preserved (generalisable, Phase 4)
    DISTRICT = "district"  # preserved
    STATE = "state"  # preserved
    PIN = "pin"
    DOB = "dob"
    AGE = "age"  # quasi-identifier, Phase 4
    GENDER = "gender"
    DATE = "date"  # clinical/admin date, Phase 4 shifting
    FREE_TEXT = "free_text"
    CLINICAL = "clinical"
    NON_PII_ID = "non_pii_id"  # visit / bill / sample / ticket ids
    UNKNOWN = "unknown"


#: Semantics whose values are preserved as-is (no detectors run on them).
PRESERVED = frozenset(
    {
        Sem.DOCTOR_NAME,
        Sem.STAFF,
        Sem.ORGANIZATION,
        Sem.RELATION,
        Sem.TEHSIL,
        Sem.DISTRICT,
        Sem.STATE,
        Sem.AGE,
        Sem.GENDER,
        Sem.DATE,
        Sem.CLINICAL,
        Sem.NON_PII_ID,
    }
)
#: Semantics whose whole value is personal data.
STRUCTURED_PII = frozenset(
    {
        Sem.PERSON_NAME,
        Sem.RELATIVE_NAME,
        Sem.PHONE,
        Sem.EMAIL,
        Sem.AADHAAR,
        Sem.ABHA_NUMBER,
        Sem.ABHA_ADDRESS,
        Sem.PAN,
        Sem.MRN,
        Sem.INSURANCE_ID,
        Sem.HOUSE,
        Sem.LOCALITY,
        Sem.LANDMARK,
        Sem.VILLAGE,
        Sem.PIN,
        Sem.DOB,
        Sem.ADDRESS,
    }
)


@dataclass(frozen=True, slots=True)
class FieldSemantic:
    sem: Sem
    confidence: float
    evidence: str  # concept names that fired (schema words only, never values)


UNKNOWN = FieldSemantic(Sem.UNKNOWN, 0.0, "")
FREE_TEXT = FieldSemantic(Sem.FREE_TEXT, 1.0, "text")

_DEVA_LABELS = {
    "नाम": "naam",
    "मरीज": "mareez",
    "मरीज़": "mareez",
    "रोगी": "rogi",
    "पिता": "pita",
    "पति": "pati",
    "पत्नी": "patni",
    "माता": "mata",
    "अभिभावक": "guardian",
    "संरक्षक": "guardian",
    "मोबाइल": "mobile",
    "फ़ोन": "phone",
    "फोन": "phone",
    "संपर्क": "sampark",
    "दूरभाष": "phone",
    "पता": "pata",
    "गाँव": "gaon",
    "गांव": "gaon",
    "ग्राम": "gaon",
    "मोहल्ला": "mohalla",
    "तहसील": "tehsil",
    "जिला": "jila",
    "ज़िला": "jila",
    "पिन": "pin",
    "कोड": "code",
    "आधार": "aadhaar",
    "ईमेल": "email",
    "जन्म": "janm",
    "तिथि": "tithi",
    "तारीख": "date",
    "तारीख़": "date",
    "दिनांक": "date",
    "आयु": "age",
    "उम्र": "age",
    "लिंग": "ling",
    "पंजीकरण": "panjikaran",
    "संख्या": "no",
    "सं": "no",
    "सं.": "no",
    "नं": "no",
    "नंबर": "no",
    "आईपीडी": "ipd",
    "ओपीडी": "opd",
    "डॉक्टर": "doctor",
    "चिकित्सक": "doctor",
    "अस्पताल": "hospital",
    "मकान": "makan",
    "निदान": "diagnosis",
    "दवा": "drug",
    "शिकायत": "complaints",
    "टिप्पणी": "notes",
    "राज्य": "state",
    "का": "ka",
    "की": "ki",
    "के": "ke",
}
_NOISE = frozenset("of the ka ki ke a an and or is in for to".split())
PERSON_BY = frozenset("raised called witnessed brought accompanied escorted informed submitted".split())


def _concepts(spec: str) -> frozenset[str]:
    return frozenset(spec.split())


NAME = _concepts(
    "name naam nam fullname firstname lastname givenname surname first last given family middle forename local display"
)
PATIENT = _concepts(
    "patient pt pat rogi mareez marij mariz beneficiary member insured applicant client caller "
    "raised visitor holder person"
)
RELATIVE = _concepts(
    "father fathers husband husbands wife wifes mother mothers spouse guardian relative relatives "
    "attendant kin nok pita pati patni mata parent parents son daughter brother sister informant "
    "caretaker escort emergency"
)
DOCTOR = _concepts(
    "doctor dr doc consultant physician surgeon referring referred attending treating practitioner "
    "author radiologist pathologist specialist clinician"
)
STAFF = _concepts("nurse staff clerk operator technician user agent officer")
STAFF_VERB = _concepts("exported entered created updated signed verified approved prepared recorded")
PATH = _concepts("path file filename source dir directory folder url uri from")
ORG = _concepts(
    "hospital facility lab laboratory clinic department dept unit centre center system organisation "
    "organization org company insurer payer bank branch school panel panels test tests drug medicine "
    "medication diagnosis procedure package scheme plan title section category specialty speciality "
    "ward bed service product type kind"
)
RELATION_W = _concepts("relation relationship rel")
PHONE = _concepts(
    "phone mobile mob mobileno contact contactno tel telephone cell cellphone callback whatsapp "
    "sampark fone ph landline phn msisdn"
)
EMAIL = _concepts("email emailid mail")
AADHAAR = _concepts("aadhaar aadhar adhaar adhar aadhaarno uid uidai")
ABHA = _concepts("abha healthid abhaid phr abhanumber")
PAN = _concepts("pan pancard panno")
INSURANCE = _concepts("pmjay policy insurance ayushman cghs esic esi membership card")
MRN_STRONG = _concepts("uhid mrn crn regno registration panjikaran ipd ipno patientid pid hospitalid umid hosp")
MRN_WEAK = _concepts("patient hospital reg ip adm admission case record file cr opd")
ID_WORDS = _concepts("id no nos number ref code num nr")
NON_PII = _concepts(
    "visit bill sample trip ticket order invoice receipt transaction encounter report specimen claim "
    "batch episode appointment token serial sno sr srno row index entry resource bundle"
)
BIRTH = _concepts("dob birth birthdate dateofbirth janm janam born birthday")
AGE = _concepts("age umar umr aayu ayu")
GENDER = _concepts("gender sex ling")
ADDRESS = _concepts("address addr pata residence resident line postal permanent location")
HOUSE = _concepts("house houseno hno makan flat door building plot")
LOCALITY = _concepts("mohalla muhalla locality colony street area sector basti lane road gali galli")
LANDMARK = _concepts("landmark near nearby")
VILLAGE = _concepts("village vill gaon gram gaav gav city town gaanv majra")
TEHSIL = _concepts("tehsil tahsil taluk taluka block subdistrict mandal")
DISTRICT = _concepts("district distt dist jila zila zilla")
STATE = _concepts("state rajya")
PIN = _concepts("pin pincode zip zipcode postcode")
DATE = _concepts(
    "date dt on at time timestamp registered admitted discharged collected reported generated created "
    "updated exported tarikh tithi mm dd yyyy yy"
)
FREE = _concepts(
    "notes note remarks remark comments comment complaints complaint history advice summary description "
    "narrative text div findings impression course instructions message msg details observation "
    "feedback reason query body content"
)
CLINICAL = _concepts(
    "test result unit range value loinc icd snomed code system diagnosis dx drug strength frequency "
    "duration dose route vitals bp pulse spo2 temp weight height bmi rx procedure package amount status "
    "inr kg rate heart respiratory count level glucose sugar haemoglobin hemoglobin creatinine "
    "allergy allergies"
)

_VOCAB = frozenset().union(
    NAME,
    PATIENT,
    RELATIVE,
    DOCTOR,
    STAFF,
    ORG,
    RELATION_W,
    PHONE,
    EMAIL,
    AADHAAR,
    ABHA,
    PAN,
    INSURANCE,
    MRN_STRONG,
    MRN_WEAK,
    ID_WORDS,
    NON_PII,
    BIRTH,
    AGE,
    GENDER,
    ADDRESS,
    HOUSE,
    LOCALITY,
    LANDMARK,
    VILLAGE,
    TEHSIL,
    DISTRICT,
    STATE,
    PIN,
    DATE,
    FREE,
    CLINICAL,
)
_ACRONYM = re.compile(r"(?<![A-Za-z])(?:[A-Za-z]\.){2,}[A-Za-z]?\.?")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SPLIT = re.compile(r"[^0-9A-Za-zऀ-ॿ]+")


def _edit_distance_le(a: str, b: str, k: int) -> bool:
    """Optimal-string-alignment distance <= k (a transposition counts as one edit)."""
    if abs(len(a) - len(b)) > k:
        return False
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1] <= k


@lru_cache(maxsize=20_000)
def _fuzzy(token: str) -> str:
    if token in _VOCAB or len(token) < 4 or not token.isalpha():
        return token
    k = 2 if len(token) >= 8 else 1
    best = sorted(v for v in _VOCAB if len(v) >= 4 and _edit_distance_le(token, v, k))
    return best[0] if best else token


@lru_cache(maxsize=20_000)
def label_tokens(label: str) -> tuple[str, ...]:
    s = unicodedata.normalize("NFKC", label).replace("'s", " ").replace("’s", " ")
    s = _ACRONYM.sub(lambda m: m.group().replace(".", "") + " ", s)  # "D.O.B." -> "DOB"
    # split camelCase, except pieces that are already a vocabulary word ("WhatsApp")
    s = " ".join(piece if piece.casefold() in _VOCAB else _CAMEL.sub(" ", piece) for piece in _SPLIT.split(s))
    out: list[str] = []
    for raw in _SPLIT.split(s):
        if not raw:
            continue
        if any("ऀ" <= c <= "ॿ" for c in raw):
            word = _DEVA_LABELS.get(raw) or _DEVA_LABELS.get(unicodedata.normalize("NFC", raw).replace("़", ""))
            raw = word or romanize(raw)
        t = raw.casefold()
        if t in _NOISE or not t:
            continue
        out.append(_fuzzy(t))
    # compound forms written without separators
    joined = "".join(out)
    compounds = {
        "dateofbirth": "dob",
        "patientname": "name",
        "mobileno": "mobile",
        "phoneno": "phone",
        "contactno": "contact",
        "aadharno": "aadhaar",
        "aadhaarno": "aadhaar",
        "pincode": "pin",
        "zipcode": "zip",
        "houseno": "house",
        "regno": "regno",
        "ipdno": "ipd",
        "uhidno": "uhid",
    }
    if len(out) == 1 and joined in compounds:
        out = [compounds[joined]]
    return tuple(out)


def _sem(sem: Sem, conf: float, why: str) -> FieldSemantic:
    return FieldSemantic(sem, conf, why)


@lru_cache(maxsize=20_000)
def classify_label(label: str) -> FieldSemantic:
    """Classify one label on its own (see :func:`classify_path` for context)."""
    toks = label_tokens(label)
    t = set(toks)
    if not t:
        return UNKNOWN
    if t & BIRTH or ("janm" in t and "tithi" in t):
        return _sem(Sem.DOB, 0.95, "birth")
    if "by" in t:  # "<role>_by": who did something
        if t & DOCTOR or "ref" in t:
            return _sem(Sem.DOCTOR_NAME, 0.9, "doctor_by")
        if t & STAFF or t & STAFF_VERB:
            return _sem(Sem.STAFF, 0.85, "staff_by")
        if t & PERSON_BY:
            return _sem(Sem.PERSON_NAME, 0.85, "person_by")
    if "health" in t and t & ID_WORDS:
        return _sem(Sem.ABHA_NUMBER, 0.85, "health_id")
    if "postal" in t and t & ID_WORDS:
        return _sem(Sem.PIN, 0.9, "postal_code")
    if t & ABHA:
        return _sem(Sem.ABHA_ADDRESS if t & {"address", "addr"} else Sem.ABHA_NUMBER, 0.95, "abha")
    if t & AADHAAR:
        return _sem(Sem.AADHAAR, 0.95, "aadhaar")
    if t & PAN:
        return _sem(Sem.PAN, 0.9, "pan")
    if t & EMAIL:
        return _sem(Sem.EMAIL, 0.95, "email")
    if t & INSURANCE:
        return _sem(Sem.INSURANCE_ID, 0.9, "insurance")
    if t & PATH:  # "source_path", "exported_from": free text that may embed names/IDs
        return _sem(Sem.UNKNOWN, 0.5, "path")
    if t & DATE and not t & PHONE:
        return _sem(Sem.DATE, 0.9, "date")
    if t & NON_PII and (t & ID_WORDS or len(t) == 1):
        return _sem(Sem.NON_PII_ID, 0.85, "non_pii_id")
    if t & RELATION_W and not t & NAME:
        return _sem(Sem.RELATION, 0.9, "relation")
    if t & DOCTOR:
        return _sem(Sem.DOCTOR_NAME, 0.9, "doctor")
    if t & STAFF and not t & PATIENT:
        return _sem(Sem.STAFF, 0.85, "staff")
    if t & PHONE and t & {"person", "name", "naam"}:
        return _sem(Sem.RELATIVE_NAME, 0.85, "contact_person")
    if t & PHONE:
        return _sem(Sem.PHONE, 0.95, "phone")
    if t & MRN_STRONG or ("patient" in t and t & ID_WORDS) or (t & MRN_WEAK and t & ID_WORDS):
        return _sem(Sem.MRN, 0.9, "mrn")
    if t & RELATIVE:
        return _sem(Sem.RELATIVE_NAME, 0.9 if t & NAME else 0.85, "relative")
    for concept, sem in (
        (VILLAGE, Sem.VILLAGE),
        (LOCALITY, Sem.LOCALITY),
        (TEHSIL, Sem.TEHSIL),
        (DISTRICT, Sem.DISTRICT),
        (STATE, Sem.STATE),
    ):
        if t & concept and t & NAME:  # "Village Name", "District Name" name a place, not a person
            return _sem(sem, 0.85, f"{sem.value}_name")
    if t & NAME or "patient" in t:
        if t & ORG:
            return _sem(Sem.ORGANIZATION, 0.85, "organization")
        generic = not (t & PATIENT)
        return _sem(Sem.PERSON_NAME, 0.8 if generic else 0.9, "name" if generic else "patient_name")
    if t & PIN:
        return _sem(Sem.PIN, 0.9, "pin")
    if t & HOUSE:
        return _sem(Sem.HOUSE, 0.85, "house")
    if t & LANDMARK:
        return _sem(Sem.LANDMARK, 0.85, "landmark")
    if t & VILLAGE:
        return _sem(Sem.VILLAGE, 0.85, "village")
    if t & LOCALITY:
        return _sem(Sem.LOCALITY, 0.8, "locality")
    if t & TEHSIL:
        return _sem(Sem.TEHSIL, 0.9, "tehsil")
    if t & DISTRICT:
        return _sem(Sem.DISTRICT, 0.9, "district")
    if t & STATE:
        return _sem(Sem.STATE, 0.9, "state")
    if t & ADDRESS:
        return _sem(Sem.ADDRESS, 0.85, "address")
    if t & AGE:
        return _sem(Sem.AGE, 0.9, "age")
    if t & GENDER:
        return _sem(Sem.GENDER, 0.9, "gender")
    if t & FREE:
        return _sem(Sem.FREE_TEXT, 0.9, "free_text")
    if t & ORG:
        return _sem(Sem.ORGANIZATION, 0.7, "organization")
    if t & CLINICAL:
        return _sem(Sem.CLINICAL, 0.8, "clinical")
    if t & PATIENT:
        return _sem(Sem.PERSON_NAME, 0.6, "person")
    return UNKNOWN


_GENERIC_CHILD = frozenset(
    {
        "name",
        "naam",
        "first",
        "last",
        "given",
        "family",
        "middle",
        "forename",
        "surname",
        "local",
        "display",
        "fullname",
        "firstname",
        "lastname",
        "givenname",
        "line",
        "value",
        "text",
    }
)


def classify_path(keys: tuple[str, ...]) -> FieldSemantic:
    """Classify a leaf from its key path (nearest key last), refining generic labels by ancestors."""
    if not keys:
        return UNKNOWN
    own = classify_label(keys[-1])
    own_toks = set(label_tokens(keys[-1]))
    generic = (
        own.sem is Sem.UNKNOWN
        or (own.sem is Sem.PERSON_NAME and own.confidence < 0.85)
        or (own_toks and own_toks <= _GENERIC_CHILD)
    )
    if not generic:
        return own
    for anc in reversed(keys[:-1]):
        a = classify_label(anc)
        if a.sem is Sem.UNKNOWN:
            continue
        name_like = own.sem is Sem.PERSON_NAME or bool(own_toks & NAME)
        if a.sem in (Sem.ORGANIZATION, Sem.CLINICAL, Sem.DOCTOR_NAME, Sem.STAFF):
            return _sem(a.sem, 0.85, f"{a.evidence}>child") if name_like or own.sem is Sem.UNKNOWN else own
        if a.sem is Sem.RELATIVE_NAME and (name_like or own.sem is Sem.UNKNOWN):
            return _sem(Sem.RELATIVE_NAME, 0.9, "relative>name")
        if a.sem is Sem.PERSON_NAME and (name_like or own.sem is Sem.UNKNOWN):
            return _sem(Sem.PERSON_NAME, 0.9, f"{a.evidence}>name")
        if a.sem in (Sem.ADDRESS, Sem.VILLAGE, Sem.LOCALITY, Sem.HOUSE) and own_toks & {"line", "text", "value"}:
            return _sem(Sem.ADDRESS, 0.85, "address>line")
        if a.sem is Sem.PHONE and own.sem is Sem.UNKNOWN:
            return _sem(Sem.PHONE, 0.85, "phone>child")
        if a.sem is Sem.FREE_TEXT:
            return FREE_TEXT if own.sem is Sem.UNKNOWN else own
        if name_like:
            break
    return own


_NA_VALUES = frozenset({"", "na", "n/a", "nil", "none", "null", "unknown", "-", "--", "not available", "nill", "."})


def is_empty_value(value: str) -> bool:
    return value.strip().casefold() in _NA_VALUES
