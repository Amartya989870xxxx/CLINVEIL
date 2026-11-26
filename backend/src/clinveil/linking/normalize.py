"""Safe normalisation and comparison of patient identity evidence across scripts.

Key design invariants:
* Uses :func:`clinveil.detection.translit.name_key_strict` (retaining vowel qualities so
  ``Kiran`` != ``Karan``, ``Sita`` != ``Satya``, ``Alok`` != ``Alka``), never the coarse
  redaction key alone.
* Controlled schwa-only tolerance (``Kamlesh`` == ``Kamalesh`` == ``कमलेश``) requires
  identical consonant skeletons and identical non-``a`` vowels, preventing false merges.
* Aadhaar requires exact 12 digits starting with 2–9 AND a valid Verhoeff checksum.
  Masked Aadhaar is never accepted.
* Hospital-specific MRNs are namespaced by their issuing hospital scope so
  ``Hospital-A / MRN-12345`` never matches ``Hospital-B / MRN-12345``.
* All memo caches are registered in :mod:`clinveil.detection.caches` and cleared at run end.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlparse

from clinveil.detection.identifiers import (
    AADHAAR_MASKED_RE,
    ABHA_ADDRESS_RE,
    EMAIL_RE,
    INSURANCE_RE,
    PAN_RE,
    mrn_digit_core,
    verhoeff_valid,
)
from clinveil.detection.lexicon import (
    DEVA_CLINICAL_KEYS,
    DEVA_HONORIFICS,
    DEVA_PREFIX_TITLES,
    GENERIC_NAME_TOKENS,
    KINSHIP_TERMS,
    KNOWN_PLACES,
    NOT_NAME_WORDS,
    PATIENT_HONORIFICS,
    PREFIX_TITLES,
)
from clinveil.detection.text import UNICODE_DIGITS, digits_only, tokenize
from clinveil.detection.translit import _FOLDS, latin_name_form, name_key, romanize
from clinveil.linking.models import DateEvidence, NameEvidence, NameGrade

_TITLE_TOKENS = PREFIX_TITLES | PATIENT_HONORIFICS | KINSHIP_TERMS | frozenset({"dr", "doctor", "prof", "pt", "late"})
_DEVA_TITLE_TOKENS = DEVA_PREFIX_TITLES | DEVA_HONORIFICS
_RELATION_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:(?:[SDWFMC]\s?/\s?O|son\s+of|daughter\s+of|wife\s+of|husband\s+of|care\s+of|"
    r"Mr|Mrs|Ms|Miss|Smt|Shri|Shree|Sri|Kumari|Km|Late|Pt)\b\.?\s*:?\s*|"
    r"(?:पुत्र|पुत्री|पत्नी|पति|पिता|माता|श्रीमती|श्री|सुश्री|कुमारी|स्व\.)\s*:?\s*)+"
)
_TRAILING_HONORIFIC_RE = re.compile(
    r"(?i)(?:\s+(?:ji|jee|sahab|saheb|sahib|didi|bhaiya|bhai|behen|behenji|babu|devi\s+ji)|"
    r"\s+(?:जी|साहब|दीदी|भैया|भाई|बहन|बहनजी))\.?\s*$"
)
_NAME_STOP = NOT_NAME_WORDS | DEVA_CLINICAL_KEYS | KNOWN_PLACES | frozenset({"s", "d", "w", "c", "f", "m", "o"})
_GENERIC_MRN_PREFIXES = frozenset(
    {
        "mrn",
        "uhid",
        "crn",
        "ipd",
        "ip",
        "opd",
        "op",
        "adm",
        "pat",
        "patient",
        "pid",
        "reg",
        "hosp",
        "hos",
        "id",
        "no",
        "case",
        "rec",
        "record",
        "cr",
        "pt",
        "p",
        "h",
    }
)
_HOSPITAL_STOP = frozenset(
    {
        "hospital",
        "multispeciality",
        "multispecialty",
        "speciality",
        "specialty",
        "charitable",
        "medical",
        "centre",
        "center",
        "clinic",
        "sadan",
        "seva",
        "trust",
        "general",
        "district",
        "healthcare",
        "health",
        "nursing",
        "home",
        "institute",
        "foundation",
        "dispensary",
        "memorial",
        "care",
        "system",
        "his",
        "emr",
        "ehr",
        "ehospital",
        "hmis",
        "opeedee",
        "example",
        "com",
        "org",
        "net",
        "in",
        "gov",
        "hl7",
        "terminology",
        "codesystem",
        "uhid",
        "mrn",
        "registration",
        "reg",
        "claims",
        "opd",
        "ipd",
        "lab",
        "labs",
        "patients",
        "patient",
        "legacy",
        "export",
        "exports",
        "rx",
        "discharge",
        "summary",
        "notes",
        "report",
        "reports",
        "billing",
        "fhir",
        "bundle",
        "csv",
        "tsv",
        "json",
        "txt",
        "aspatal",
        "chikitsalaya",
        "jila",
        "zila",
    }
)
_LAB_WORDS = frozenset({"lab", "labs", "laboratory", "pathology", "diagnostic", "diagnostics", "imaging", "scans"})
_VILLAGE_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:vill(?:age)?|gram|gaon|gaav|gaanv|mohalla|muhalla|post|p\.?o\.?|ward|gram\s+panchayat|"
    r"ग्राम|गाँव|गांव|मोहल्ला|पोस्ट)\b\.?\s*[:\-]?\s*"
)


_LINK_VOWELS = (
    ("aa", "a"),
    ("ee", "i"),
    ("ii", "i"),
    ("oo", "u"),
    ("uu", "u"),
    ("au", "o"),
    ("ou", "o"),
    ("ai", "e"),
    ("ei", "e"),
)


# --------------------------------------------------------------------------- names
@lru_cache(maxsize=100_000)
def strict_name_token(token: str) -> str:
    """Strict cross-script token key that preserves vowel qualities (``Kiran`` != ``Karan``).

    Folds consonants and Indian diphthong/length equivalences (``au``/``ou``->``o``,
    ``ai``/``ei``->``e``, ``ee``/``ii``->``i``, ``oo``/``uu``->``u``, ``qu``->``k``,
    trailing ``ey``->``e`` and ``y``->``i``, initial ``o``->``u`` and ``e``->``i``)
    while keeping distinct medial vowels (``i`` vs ``a``, ``o`` vs ``a``) strictly apart.
    """
    t = latin_name_form(token)
    if not t:
        return ""
    t = t.replace("qu", "k")
    for a, b in _FOLDS:
        t = t.replace(a, b)
    for a, b in _LINK_VOWELS:
        t = t.replace(a, b)
    if len(t) >= 2:
        if t.endswith("ey") and len(t) >= 4:
            t = t[:-1]  # pandey -> pande, dubey -> dube
        elif t.endswith("y") and len(t) >= 3:
            t = t[:-1] + "i"  # tripathy -> tripati, chaudhary -> chaudhari
        if t[0] == "o":
            t = "u" + t[1:]  # omar ~ umar
        elif t[0] == "e":
            t = "i" + t[1:]  # eshaan ~ ishaan
    return re.sub(r"(.)\1+", r"\1", t)


@lru_cache(maxsize=100_000)
def schwa_skeleton(strict_tok: str) -> str:
    """Delete medial schwa ``a`` between consonants while keeping all other vowels intact.

    ``kamales`` -> ``kamles`` (matches ``kamles`` / ``कमलेश``), while
    ``kiran`` -> ``kirn`` != ``karan`` -> ``krn``, ``sita`` -> ``sit`` != ``satia`` -> ``stia``.
    """
    if len(strict_tok) <= 2:
        return strict_tok
    out = [strict_tok[0]]
    vowels = set("aeiou")
    for i in range(1, len(strict_tok)):
        ch = strict_tok[i]
        if (
            ch == "a"
            and i + 1 < len(strict_tok)
            and strict_tok[i - 1] not in vowels
            and strict_tok[i + 1] not in vowels
        ):
            continue
        out.append(ch)
    return "".join(out)


def build_name_evidence(raw_text: str, *, confidence: float, source: str) -> NameEvidence | None:
    """Normalise a raw patient or relative name string into :class:`NameEvidence`."""
    cleaned = _RELATION_PREFIX_RE.sub("", raw_text.strip())
    cleaned = _TRAILING_HONORIFIC_RE.sub("", cleaned).strip(" ,:;-–()")
    if not cleaned:
        return None
    # Handle "Last, First" format (e.g. "Kulkarni, Pranav")
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        if len(parts) == 2 and not any(len(p.split()) > 3 for p in parts):
            cleaned = f"{parts[1]} {parts[0]}"
    toks = tokenize(cleaned)
    strict_list: list[str] = []
    skel_list: list[str] = []
    ident_list: list[str] = []
    init_list: list[str] = []
    initial_flags: list[bool] = []
    for tok in toks:
        if tok.key.isdigit():
            continue
        if tok.key in _TITLE_TOKENS or tok.text in _DEVA_TITLE_TOKENS:
            continue
        if tok.key in _NAME_STOP or tok.text in _NAME_STOP:
            continue
        lf = latin_name_form(tok.text)
        st = strict_name_token(tok.text)
        if not st:
            continue
        is_init = len(lf) == 1 and not tok.is_devanagari
        strict_list.append(st)
        skel_list.append(schwa_skeleton(st))
        init_list.append(st[0])
        initial_flags.append(is_init)
        if not is_init and tok.key not in GENERIC_NAME_TOKENS and lf not in GENERIC_NAME_TOKENS:
            ident_list.append(st)
    if not strict_list:
        return None
    # If every token was marked generic (e.g. "Devi Singh"), keep strict tokens as identifying fallback
    if not ident_list and not all(initial_flags):
        ident_list = [s for s, ini in zip(strict_list, initial_flags, strict=True) if not ini]
    return NameEvidence(
        strict_tokens=tuple(strict_list),
        skeleton_tokens=tuple(skel_list),
        identifying_strict=tuple(ident_list),
        initials=tuple(init_list),
        is_single_token=len(strict_list) == 1,
        is_initial_only=all(initial_flags),
        confidence=confidence,
        source=source,
    )


def combine_name_parts(parts: list[str], *, confidence: float, source: str) -> NameEvidence | None:
    """Assemble split name fields (e.g., ``FirstName`` + ``LastName`` or FHIR ``given`` + ``family``)."""
    joined = " ".join(p.strip() for p in parts if p and p.strip())
    return build_name_evidence(joined, confidence=confidence, source=source) if joined else None


def _tokens_variant_equal(a_strict: str, a_skel: str, b_strict: str, b_skel: str) -> bool:
    if a_strict == b_strict:
        return True
    if len(a_strict) >= 3 and len(b_strict) >= 3 and a_skel == b_skel:
        return True
    # Allow trailing schwa difference (e.g. "ram" vs "rama", "siv" vs "siva") when >=3 chars
    if len(a_strict) >= 3 and len(b_strict) >= 3:
        if a_strict + "a" == b_strict or b_strict + "a" == a_strict:
            return True
        if a_skel + "a" == b_skel or b_skel + "a" == a_skel:
            return True
    return False


def _token_matches_initial(short_tok: str, full_tok: str) -> bool:
    return len(short_tok) == 1 and len(full_tok) >= 2 and short_tok[0] == full_tok[0]


def compare_names(a: NameEvidence, b: NameEvidence) -> NameGrade:
    """Compare two normalised names with strict vowel preservation and abbreviation support."""
    if a.is_initial_only or b.is_initial_only:
        return NameGrade.NONE
    sa, sb = a.strict_tokens, b.strict_tokens
    ka, kb = a.skeleton_tokens, b.skeleton_tokens

    # Case 1: Both have >= 2 tokens (full names)
    if len(sa) >= 2 and len(sb) >= 2:
        if sa == sb or (len(sa) == 2 and len(sb) == 2 and sa == (sb[1], sb[0])):
            return NameGrade.EXACT_FULL
        # Same length, every position strict-or-schwa-variant equal
        if len(sa) == len(sb) and all(_tokens_variant_equal(sa[i], ka[i], sb[i], kb[i]) for i in range(len(sa))):
            return NameGrade.VARIANT_FULL
        # Reversed 2-token variant ("Kulkarni Pranav" vs "Pranav Kulkarni")
        if (
            len(sa) == 2
            and len(sb) == 2
            and _tokens_variant_equal(sa[0], ka[0], sb[1], kb[1])
            and _tokens_variant_equal(sa[1], ka[1], sb[0], kb[0])
        ):
            return NameGrade.VARIANT_FULL
        # Middle-name omission (e.g. "Anil Kumar Verma" vs "Anil Verma") when first & last match
        if len(sa) != len(sb) and (
            _tokens_variant_equal(sa[0], ka[0], sb[0], kb[0]) and _tokens_variant_equal(sa[-1], ka[-1], sb[-1], kb[-1])
        ):
            return NameGrade.VARIANT_FULL
        # Abbreviated given/middle name: "R. Sharma" vs "Rajesh Sharma" or "A. K. Verma" vs "Anil Kumar Verma"
        if _tokens_variant_equal(sa[-1], ka[-1], sb[-1], kb[-1]):
            a_given, b_given = sa[:-1], sb[:-1]
            if (
                len(a_given) == len(b_given)
                and all(
                    _tokens_variant_equal(a_given[i], ka[i], b_given[i], kb[i])
                    or _token_matches_initial(a_given[i], b_given[i])
                    or _token_matches_initial(b_given[i], a_given[i])
                    for i in range(len(a_given))
                )
                and (any(len(x) == 1 for x in a_given) or any(len(x) == 1 for x in b_given))
            ):
                return NameGrade.ABBREVIATED_FULL
            # "R. Verma" vs "Rajesh Kumar Verma" (single initial + matching surname)
            if (len(a_given) == 1 and _token_matches_initial(a_given[0], b_given[0])) or (
                len(b_given) == 1 and _token_matches_initial(b_given[0], a_given[0])
            ):
                return NameGrade.ABBREVIATED_FULL
        return NameGrade.CONFLICT

    # Case 2: At least one is a single-token name (e.g. fragmented "Kavya, W/o ..." or "Farooq sahab")
    single, other = (a, b) if a.is_single_token else (b, a)
    tok_s, tok_k = single.strict_tokens[0], single.skeleton_tokens[0]
    if len(tok_s) < 2 or not single.identifying_strict:
        return NameGrade.NONE
    # Match against other's identifying tokens (handles both "Kavya" in "Kavya Devi" and "Farooq" in "Mohd Farooq")
    other_ident_indices = [i for i, st in enumerate(other.strict_tokens) if st in other.identifying_strict or i == 0]
    if any(
        _tokens_variant_equal(tok_s, tok_k, other.strict_tokens[i], other.skeleton_tokens[i])
        for i in other_ident_indices
    ):
        return NameGrade.FIRST_ONLY_MATCH
    return NameGrade.CONFLICT


def best_name_grade(names_a: tuple[NameEvidence, ...], names_b: tuple[NameEvidence, ...]) -> NameGrade:
    """Best match grade across all patient-name mentions of two records/clusters."""
    if not names_a or not names_b:
        return NameGrade.NONE
    order = {
        NameGrade.EXACT_FULL: 5,
        NameGrade.VARIANT_FULL: 4,
        NameGrade.ABBREVIATED_FULL: 3,
        NameGrade.FIRST_ONLY_MATCH: 2,
        NameGrade.NONE: 1,
        NameGrade.CONFLICT: 0,
    }
    best = NameGrade.CONFLICT
    saw_comparable = False
    for na in names_a:
        for nb in names_b:
            g = compare_names(na, nb)
            if g is not NameGrade.NONE:
                saw_comparable = True
            if order[g] > order[best]:
                best = g
    return best if saw_comparable else NameGrade.NONE


# --------------------------------------------------------------------------- identifiers
def normalize_aadhaar(raw: str) -> str | None:
    """Return 12 ASCII digits ONLY if unmasked, starting with 2–9, and Verhoeff-valid."""
    if AADHAAR_MASKED_RE.search(raw):
        return None
    d = digits_only(raw)
    if len(d) == 12 and d[0] in "23456789" and verhoeff_valid(d):
        return d
    return None


def normalize_abha_number(raw: str) -> str | None:
    d = digits_only(raw)
    return d if len(d) == 14 else None


def normalize_abha_address(raw: str) -> str | None:
    m = ABHA_ADDRESS_RE.search(raw.strip())
    return m.group(0).casefold() if m else None


def normalize_pan(raw: str) -> str | None:
    m = PAN_RE.search(raw.strip().translate(UNICODE_DIGITS).upper())
    return m.group(0) if m else None


def normalize_insurance(raw: str) -> str | None:
    s = raw.strip().translate(UNICODE_DIGITS)
    m = INSURANCE_RE.search(s)
    if m:
        return re.sub(r"[^A-Z0-9]", "", m.group(0).upper())
    alnum = re.sub(r"[^A-Z0-9]", "", s.upper())
    if len(alnum) >= 6 and sum(c.isdigit() for c in alnum) >= 4:
        return alnum
    return None


def normalize_email(raw: str) -> str | None:
    m = EMAIL_RE.search(raw.strip())
    if not m or ABHA_ADDRESS_RE.fullmatch(m.group(0)):
        return None
    return m.group(0).casefold()


def normalize_phone(raw: str) -> str | None:
    """Return 10-digit Indian mobile core (starts with 6–9) or None."""
    d = digits_only(raw)
    if len(d) == 10 and d[0] in "6789":
        return d
    if len(d) == 11 and d.startswith("0") and d[1] in "6789":
        return d[1:]
    if len(d) == 12 and d.startswith("91") and d[2] in "6789":
        return d[2:]
    if len(d) == 13 and d.startswith("091") and d[3] in "6789":
        return d[3:]
    if len(d) == 14 and d.startswith("0091") and d[4] in "6789":
        return d[4:]
    return None


@lru_cache(maxsize=10_000)
def normalize_hospital(raw: str) -> tuple[str | None, bool]:
    """Normalise a hospital/facility name, URL, or filename stem into ``(slug, is_external_lab)``.

    Preserves distinctive identifiers like ``Hospital-A`` -> ``hospital_a`` and
    ``Hospital-B`` -> ``hospital_b`` so two distinct hospitals never collapse together.
    """
    if not raw or not raw.strip():
        return None, False
    text = raw.strip()
    if "://" in text:
        host = urlparse(text).hostname or ""
        text = host.replace(".", " ")
    else:
        # Strip trailing city/branch/subtitle after comma, em-dash, or pipe ("Arogya Seva Sadan, Sitapur")
        text = re.split(r"[,|—–]", text, maxsplit=1)[0].strip()
    # Convert Devanagari hospital names to Latin so Latin/Devanagari headers align
    if any("ऀ" <= c <= "ॿ" for c in text):
        text = romanize(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    raw_tokens = re.findall(r"[a-z0-9]+", text)
    if not raw_tokens:
        return None, False
    is_lab = bool(set(raw_tokens) & _LAB_WORDS)
    # Keep "hospital_a" / "hospital_1" intact when suffix is a single letter or short number
    for i in range(len(raw_tokens) - 1):
        if raw_tokens[i] in ("hospital", "hosp", "clinic", "facility", "site", "unit") and (
            len(raw_tokens[i + 1]) == 1 or raw_tokens[i + 1].isdigit()
        ):
            return f"{raw_tokens[i]}_{raw_tokens[i + 1]}", is_lab
    kept = [t for t in raw_tokens if t not in _HOSPITAL_STOP and not t.isdigit() and len(t) >= 2]
    if not kept:
        return None, is_lab
    # Collapse common prefix-style compounds ("dhhardoi" -> "hardoi", "jeevan jyoti" -> "jeevanjyoti")
    joined = "".join(kept[:2]) if len(kept) >= 2 and len(kept[0]) + len(kept[1]) <= 14 else kept[0]
    if joined.startswith("dhh") and len(joined) > 3:
        joined = joined[2:]  # dhhardoi -> hardoi (aligns "District Hospital Hardoi" & "dhhardoi")
    return joined, is_lab


def normalize_mrn(raw: str, hospital: str | None) -> tuple[str, str, str, bool] | None:
    """Return ``(scope, canonical_mrn, digit_core, has_distinctive_prefix)`` or None.

    * Hospital-prefixed MRNs (e.g. ``SUN/26/100101``, ``LOT-008821``) carry a distinctive
      issuing-system prefix (``has_distinctive_prefix=True``).
    * Generic or numeric MRNs (``MRN-12345``, ``UHID-099102``, ``004123``) are strictly
      namespaced to ``hospital`` (or ``"unscoped"`` if unknown) so two different known
      hospitals never share a scope.
    """
    s = raw.strip().translate(UNICODE_DIGITS)
    parts = re.findall(r"[A-Za-z]+|\d+", s)
    if not parts:
        return None
    all_digits = "".join(p for p in parts if p.isdigit())
    if len(all_digits) < 3:
        return None
    canonical = "-".join(p.upper() for p in parts)
    core = mrn_digit_core(s)
    alpha_prefix = parts[0].lower() if parts[0].isalpha() else ""
    distinctive = bool(alpha_prefix and len(alpha_prefix) >= 2 and alpha_prefix not in _GENERIC_MRN_PREFIXES)
    if hospital:
        scope = f"hosp:{hospital}"
    elif distinctive:
        scope = f"pfx:{alpha_prefix}"
    else:
        scope = "unscoped"
    return scope, canonical, core, distinctive


# --------------------------------------------------------------------------- dates, ages, gender, geography
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
_SLASH_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)")
_NAMED_DMY_RE = re.compile(r"(?i)(?<!\d)(\d{1,2})[\s\-./]+([A-Za-z]{3,9})[\s\-./,]+(\d{4})(?!\d)")
_NAMED_MDY_RE = re.compile(r"(?i)\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})(?!\d)")
_YEAR_ONLY_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*$")


def _valid_ymd(y: int, m: int, d: int) -> tuple[int, int, int] | None:
    if not (1900 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    try:
        dt.date(y, m, d)
        return (y, m, d)
    except ValueError:
        return None


def normalize_dob(raw: str, *, month_first_hint: bool = False) -> tuple[DateEvidence | None, int | None]:
    """Parse a DOB value into ``(DateEvidence | None, birth_year | None)``."""
    s = raw.strip().translate(UNICODE_DIGITS)
    if not s:
        return None, None
    m = _ISO_DATE_RE.search(s)
    if m:
        ymd = _valid_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if ymd:
            return DateEvidence(ymd, None), ymd[0]
    m = _NAMED_DMY_RE.search(s)
    if m and m.group(2).lower() in _MONTHS:
        ymd = _valid_ymd(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        if ymd:
            return DateEvidence(ymd, None), ymd[0]
    m = _NAMED_MDY_RE.search(s)
    if m and m.group(1).lower() in _MONTHS:
        ymd = _valid_ymd(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        if ymd:
            return DateEvidence(ymd, None), ymd[0]
    m = _SLASH_DATE_RE.search(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y = 1900 + y if y >= 30 else 2000 + y
        if month_first_hint:
            ymd = _valid_ymd(y, a, b)
            if ymd:
                return DateEvidence(ymd, None), ymd[0]
        if a > 12:
            ymd = _valid_ymd(y, b, a)
            if ymd:
                return DateEvidence(ymd, None), ymd[0]
        elif b > 12:
            ymd = _valid_ymd(y, a, b)
            if ymd:
                return DateEvidence(ymd, None), ymd[0]
        else:
            dmy = _valid_ymd(y, b, a)
            mdy = _valid_ymd(y, a, b)
            if dmy:
                alt = mdy if (mdy and mdy != dmy and not month_first_hint) else None
                return DateEvidence(dmy, alt), dmy[0]
    m = _YEAR_ONLY_RE.match(s)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2030:
            return None, y
    return None, None


_AGE_STRUCTURED_RE = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")
_AGE_FREE_RE = re.compile(
    r"(?i)(?:(?:\b(?:age|aged|umar|umr)\b|आयु|उम्र)\s*[:/\-]?\s*(\d{1,3})\b"
    r"|(?<!\d)(\d{1,3})\s*(?:(?:/\s*[MF]\b)|(?:y(?:rs?|ears?)?\s*/\s*[MF]\b)|(?:yrs?|years?|वर्ष|साल)\b))"
)
_DURATION_BEFORE_RE = re.compile(r"(?i)(?:x|for|since|past|last|over|about|approx\.?|×)\s*$")
_DURATION_AFTER_RE = re.compile(r"(?i)^\s*(?:back|ago|history|h/o|duration|prior|earlier)\b")


def extract_ages(text: str, *, structured: bool = False) -> set[int]:
    """Extract plausible patient ages (0–120), ignoring medication durations and history spans."""
    s = text.translate(UNICODE_DIGITS)
    out: set[int] = set()
    if structured:
        # Avoid interpreting age bands ("45-49") as exact ages here
        if re.search(r"\d+\s*[-–]\s*\d+", s):
            return out
        m = _AGE_STRUCTURED_RE.search(s)
        if m:
            v = int(m.group(1))
            if 0 <= v <= 120:
                out.add(v)
        return out
    for m in _AGE_FREE_RE.finditer(s):
        raw_num = m.group(1) or m.group(2)
        if not raw_num:
            continue
        before = s[max(0, m.start() - 18) : m.start()]
        after = s[m.end() : m.end() + 20]
        if _DURATION_BEFORE_RE.search(before) or _DURATION_AFTER_RE.search(after):
            continue
        v = int(raw_num)
        if 0 <= v <= 120:
            out.add(v)
    return out


_GENDER_FREE_RE = re.compile(
    r"(?i)(?:\b(?:sex|gender|ling)\b|लिंग)\s*[:\-]?\s*(male|female|m|f|पुरुष|महिला|स्त्री)\b"
    r"|(?<!\d)\d{1,3}\s*(?:y(?:rs?|ears?)?)?\s*/\s*([MF])\b"
)
_RELATION_GENDER_RE = re.compile(r"(?i)(?<![/\w])([SDW])\s?/\s?O\b|(पुत्र|पुत्री|पत्नी)\b")


def extract_genders(text: str, *, structured: bool = False) -> set[str]:
    """Extract canonical patient gender (``M`` / ``F``)."""
    out: set[str] = set()
    if structured:
        val = text.strip().casefold()
        if val in ("m", "male", "पुरुष", "पु"):
            out.add("M")
        elif val in ("f", "female", "महिला", "स्त्री", "म"):
            out.add("F")
        elif val in ("o", "other", "transgender"):
            out.add("O")
        return out
    for m in _GENDER_FREE_RE.finditer(text.translate(UNICODE_DIGITS)):
        tok = (m.group(1) or m.group(2) or "").casefold()
        if tok in ("m", "male", "पुरुष"):
            out.add("M")
        elif tok in ("f", "female", "महिला", "स्त्री"):
            out.add("F")
    for m in _RELATION_GENDER_RE.finditer(text):
        code = (m.group(1) or m.group(2) or "").upper()
        if code in ("S", "पुत्र"):
            out.add("M")
        elif code in ("D", "W", "पुत्री", "पत्नी"):
            out.add("F")
    return out


@lru_cache(maxsize=20_000)
def normalize_village(raw: str) -> str | None:
    """Cross-script phonetic key for a village/locality name (``केशवपुर`` == ``Keshavpur``)."""
    cleaned = _VILLAGE_PREFIX_RE.sub("", raw.strip()).strip(" ,.;:-–()")
    if not cleaned:
        return None
    cleaned = cleaned.split(",")[0].strip()
    toks = [name_key(t.text) for t in tokenize(cleaned) if not t.key.isdigit()]
    toks = [t for t in toks if t and t not in {"grm", "gn", "vl", "vlg", "mhl", "pst", "tsl", "dst"}]
    if not toks:
        return None
    key = " ".join(toks)
    return key if len(key) >= 2 else None


@lru_cache(maxsize=10_000)
def normalize_district(raw: str) -> str | None:
    cleaned = re.sub(r"(?i)^\s*(?:distt?\.?|district|जिला|ज़िला)\s*[:\-]?\s*", "", raw.strip()).strip(" ,.;:-")
    if not cleaned:
        return None
    toks = [strict_name_token(t.text) for t in tokenize(cleaned) if not t.key.isdigit()]
    toks = [t for t in toks if t]
    return " ".join(toks) if toks else None
