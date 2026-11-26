"""Contextual person-name detection in free text (Latin, Devanagari, Hinglish).

Detectors (each yields :class:`Hit` with entity PATIENT_NAME or RELATIVE_NAME):

  label        ``Name:``, ``Patient Name:``, ``Pt.``, ``नाम:``, ``मरीज़ का नाम:``, ``Report of``
  relative     ``Father's name:``, ``Attendant:``, ``पिता का नाम:``, ``Pita/Pati ka Naam``
  relation     ``S/o``, ``D/o``, ``W/o``, ``C/O <Name>`` (but never ``C/O fever``), ``पुत्र``, ``पत्नी``…
  honorific    ``Shahid sahab``, ``Orvila didi``, ``Kirti ji``, ``रमेश जी`` (patient);
               ``Kelvar Mama``, ``Dunmore Bhaiya`` (kinship: relative)
  title        ``Mr.``, ``Smt.``, ``Shri``, ``श्रीमती``…
  by_cue       ``witnessed by``, ``called by``, ``brought by``…
  role_suffix  ``<Name> (attendant, bed 12)``
  timeline     ``14:00 - <Name> - …`` (nursing/visitor logs) and WhatsApp senders
  possessive   ``Orvila's attendant``
  gazetteer    two capitalised tokens that are a known given name + known surname

Doctor labels (``Consultant:``, ``Referred by:``) yield keep spans instead. Names
are delimited token by token on the ORIGINAL text, so offsets are exact for both
scripts; honorifics and titles are left in place (they identify no one).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from clinveil.detection.clinical import KeepSpan
from clinveil.detection.identifiers import Hit
from clinveil.detection.lexicon import (
    ANATOMY_WORDS,
    COMPLAINT_WORDS,
    DEVA_CLINICAL_KEYS,
    DEVA_HONORIFICS,
    DEVA_PREFIX_TITLES,
    EPONYM_ROOTS,
    GIVEN_NAMES,
    KINSHIP_TERMS,
    KNOWN_PLACES,
    NOT_NAME_WORDS,
    PATIENT_HONORIFICS,
    PREFIX_TITLES,
    PROCEDURE_WORDS,
    SEVERITY_WORDS,
    SURNAMES,
)
from clinveil.detection.semantics import Sem, classify_label
from clinveil.detection.text import Token, normalize_token, tokenize
from clinveil.detection.translit import name_key
from clinveil.models.findings import EntityType

P, R = EntityType.PATIENT_NAME, EntityType.RELATIVE_NAME
_GIVEN_KEYS = frozenset(name_key(n) for n in GIVEN_NAMES)
_SURNAME_KEYS = frozenset(name_key(n) for n in SURNAMES)
_DEVA_STOP = frozenset(
    {
        "आयु",
        "उम्र",
        "पिता",
        "पति",
        "माता",
        "पत्नी",
        "पंजीकरण",
        "मोबाइल",
        "पता",
        "लिंग",
        "वर्ष",
        "ग्राम",
        "तारीख",
        "तारीख़",
        "का",
        "की",
        "के",
        "को",
        "ने",
        "से",
        "में",
        "है",
        "और",
        "पुत्र",
        "पुत्री",
        "मकान",
        "तहसील",
        "जिला",
        "आईपीडी",
        "भर्ती",
        "डिस्चार्ज",
    }
)
_STOP = (
    NOT_NAME_WORDS
    | PATIENT_HONORIFICS
    | KINSHIP_TERMS
    | frozenset({"s", "d", "w", "c", "f", "m", "o", "aged", "yrs", "yr", "y"})
) - frozenset()
_HONORIFIC_TOKENS = PATIENT_HONORIFICS | KINSHIP_TERMS
_SPACE = re.compile(r"[  ]")


_DEVA_STOP_KEYS = frozenset(normalize_token(w) for w in _DEVA_STOP) | DEVA_CLINICAL_KEYS | KNOWN_PLACES
#: Words that follow "C/O" in a presenting complaint: never the start of a relative's name.
CARE_OF_COMPLAINT = COMPLAINT_WORDS | SEVERITY_WORDS | ANATOMY_WORDS | PROCEDURE_WORDS | NOT_NAME_WORDS
_ACTION_VERBS = frozenset(
    "started inserted removed given done changed applied checked administered completed stopped repeated "
    "sent received collected shifted transferred noted seen advised planned continued restarted held "
    "taken passed reviewed explained discontinued".split()
)


def _is_name_token(tok: Token, *, allow_lower: bool) -> bool:
    if tok.is_devanagari:
        return (
            tok.text not in _DEVA_STOP
            and tok.key not in _DEVA_STOP_KEYS
            and tok.text not in DEVA_HONORIFICS
            and not tok.key.isdigit()
        )
    if not tok.text.isalpha() and not all(c.isalpha() or c in "'’-" for c in tok.text):
        return False
    if tok.key in _STOP:
        return False
    return allow_lower or tok.text[0].isupper()


def _gap_ok(text: str, a: int, b: int) -> bool:
    """Tokens are part of one name if separated by one space or an initial's period."""
    gap = text[a:b]
    return gap in (" ", " ", ". ", ".", "_") or (len(gap) == 2 and gap[0] == "." and gap[1] == " ")


def name_after(
    text: str, tokens: list[Token], pos: int, *, allow_lower: bool, max_tokens: int = 4
) -> tuple[int, int] | None:
    """Span of name tokens starting at (or just after) ``pos``; titles before the name are skipped."""
    i = next((k for k, t in enumerate(tokens) if t.start >= pos), None)
    if i is None or text[pos : tokens[i].start].strip("  ") not in ("", ":", "-", "–"):
        return None
    while (
        i < len(tokens)
        and (tokens[i].key in PREFIX_TITLES or tokens[i].text in DEVA_PREFIX_TITLES)
        and i + 1 < len(tokens)
        and _gap_ok(text, tokens[i].end, tokens[i + 1].start)
    ):
        i += 1
    start = end = None
    taken = 0
    while i < len(tokens) and taken < max_tokens:
        tok = tokens[i]
        if start is not None and not _gap_ok(text, end, tok.start):
            break
        if not _is_name_token(tok, allow_lower=allow_lower):
            break
        start = tok.start if start is None else start
        end = tok.end
        taken += 1
        i += 1
    return (start, end) if start is not None else None


def name_before(
    text: str, tokens: list[Token], upto: int, *, max_tokens: int = 3, allow_comma: bool = False
) -> tuple[int, int] | None:
    """Span of capitalised/Devanagari name tokens ending (modulo one space) right before ``upto``."""
    j = max((k for k, t in enumerate(tokens) if t.end <= upto), default=-1)
    gaps = ("", " ", "\u00a0") + ((",", ", ", " , ", " ,") if allow_comma else ())
    if j < 0 or text[tokens[j].end : upto] not in gaps:
        return None
    start = end = None
    taken = 0
    while j >= 0 and taken < max_tokens:
        tok = tokens[j]
        if end is not None and not _gap_ok(text, tok.end, start):
            break
        if not _is_name_token(tok, allow_lower=False):
            break
        end = tok.end if end is None else end
        start = tok.start
        taken += 1
        j -= 1
    return (start, end) if start is not None else None


# --------------------------------------------------------------------------- label patterns
_COLON = r"\s*[:：\-–]\s*"
PATIENT_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:patient(?:'s|’s)?\s*name|name\s+of\s+(?:the\s+)?patient|pt\.?\s*name|full\s+name|patient|"
    r"pt|name|naam|beneficiary)"
    + _COLON
    + r"|(?:मरीज़?\s*का\s*नाम|रोगी\s*का\s*नाम|नाम|मरीज़?|रोगी)"
    + _COLON
    + r"|\breport\s+(?:of|for)\s+)"
)
RELATIVE_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:father(?:'s|’s)?\s*name|husband(?:'s|’s)?\s*name|mother(?:'s|’s)?\s*name|wife(?:'s|’s)?\s*name|"
    r"spouse(?:'s)?(?:\s*name)?|guardian(?:'s)?(?:\s*name)?|attendant(?:'s)?(?:\s*name)?|relative(?:'s)?(?:\s*name)?|"
    r"next\s+of\s+kin|nok|informant|caretaker|contact\s+person|emergency\s+contact(?:\s*name)?|"
    r"pita(?:\s*/\s*pati)?\s*ka\s*naam|pati\s*ka\s*naam|visitor)"
    + _COLON
    + r"|(?:पिता|पति|माता|पत्नी|अभिभावक)(?:\s*/\s*(?:पिता|पति))?\s*का\s*नाम"
    + _COLON
    + r"|(?:अभिभावक|परिचारक)"
    + _COLON
    + ")"
)
DOCTOR_LABEL_RE = re.compile(
    r"(?i)\b(?:consultant|treating\s+doctor|attending\s+doctor|doctor|ref(?:erred)?\.?\s*by|ref\.?\s*doctor|"
    r"surgeon|physician|signed\s+by|reported\s+by|verified\s+by)" + _COLON
)
RELATION_RE = re.compile(
    r"(?i)(?<![/\w])(?:([SDWFMC])\s?/\s?O|son\s+of|daughter\s+of|wife\s+of|husband\s+of|"
    r"father\s+of|mother\s+of|care\s+of)\b\.?\s*:?\s*"
)
# the lookahead excludes the particles "का/की/के" (``पिता का नाम``), not names that start with them (``केशव``)
DEVA_RELATION_RE = re.compile(r"(?:पुत्र|पुत्री|पत्नी|पति|पिता|माता|सुपुत्र|सुपुत्री|धर्मपत्नी)\s+(?!(?:का|की|के)(?=[\s:।,]|$))")
TITLE_RE = re.compile(r"(?i)\b(?:(?:Mr|Mrs|Ms|Miss|Shri|Shree|Sri|Smt|Shrimati|Kumari|Km|Late)\b\.?|Pt\.)\s+")
DEVA_TITLE_RE = re.compile(r"(?:श्रीमती|श्री|सुश्री|कुमारी|स्व\.)\s*")
BY_CUE_RE = re.compile(
    r"(?i)\b(?:witnessed|called|brought|accompanied|escorted|informed|identified|received|"
    r"handed\s+over|collected)\s+by\s+"
)
ROLE_SUFFIX_RE = re.compile(
    r"\s*\(\s*(?:attendant|relative|visitor|guardian|wife|husband|son|daughter|father|"
    r"mother|brother|sister|caretaker|escort|friend|neighbou?r|bystander)\b",
    re.I,
)
TIMELINE_RE = re.compile(r"(?m)^[ \t]*\[?\d{1,2}[:.]\d{2}(?:\s*[ap]\.?m\.?)?\]?[ \t]*[-–:][ \t]*")
WHATSAPP_RE = re.compile(r"(?m)^\[\d{1,2}/\d{1,2}/\d{2,4},?\s*\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?\]\s*")
MUSLIM_PREFIX_RE = re.compile(r"\b(?:Mohd|Md|Mohammad|Mohammed|Muhammad|Syed|Sk|Shaikh|Sheikh)\.?(?=\s+[A-Z])")
POSSESSIVE_RE = re.compile(
    r"\b([A-Z][a-z]{2,})(?:'s|’s)\s+(?:attendant|husband|wife|son|daughter|mother|father|"
    r"relative|family|brother|sister|guardian|sample|report|reports|condition)\b"
)


def detect_names(text: str) -> tuple[list[Hit], list[KeepSpan]]:
    tokens = tokenize(text)
    hits: list[Hit] = []
    keeps: list[KeepSpan] = []

    def add(span: tuple[int, int] | None, entity: EntityType, conf: float, det: str) -> None:
        if span and span[1] > span[0]:
            hits.append(Hit(span[0], span[1], entity, conf, det))

    for m in DOCTOR_LABEL_RE.finditer(text):
        seg = re.match(r"[^,\n(;]{0,60}", text[m.end() :])
        keeps.append(KeepSpan(m.start(), m.end() + (seg.end() if seg else 0), "doctor"))
    relative_labels: list[tuple[int, int]] = []
    for m in RELATIVE_LABEL_RE.finditer(text):
        relative_labels.append((m.start(), m.end()))
        add(name_after(text, tokens, m.end(), allow_lower=True), R, 0.9, "relative_label")
    for m in PATIENT_LABEL_RE.finditer(text):
        if any(a <= m.start() < b for a, b in relative_labels):
            continue  # "नाम:" inside "पिता का नाम:" / "name:" inside "Father's name:"
        if _qualified_non_person_label(text, m):
            continue  # "Test Name:", "Drug Name:", "दवा का नाम:": the value is not a person
        conf = 0.85 if m.group().lower().startswith("report") else 0.92
        add(
            name_after(text, tokens, m.end(), allow_lower=not m.group().lower().startswith("report")),
            P,
            conf,
            "patient_label",
        )
    for m in RELATION_RE.finditer(text):
        if (m.group(1) or "").upper() == "C" or m.group().lower().startswith("care"):
            nxt = next((t for t in tokens if t.start >= m.end()), None)
            if nxt is None or nxt.key in CARE_OF_COMPLAINT or not nxt.text[:1].isupper() and not nxt.is_devanagari:
                continue  # "C/O fever …", "C/O Left knee pain": a presenting complaint
            # "C/O <Name>" (care of): contextual only, never seeded into the run-wide index
            add(name_after(text, tokens, m.end(), allow_lower=False), R, 0.85, "care_of")
            continue
        add(name_after(text, tokens, m.end(), allow_lower=False), R, 0.9, "relation_marker")
        if (m.group(1) or "").upper() in ("S", "D", "W") or re.match(r"(?i)(?:son|daughter|wife)\s", m.group()):
            # "Rani, W/o Velan": the name BEFORE the marker is the patient
            add(name_before(text, tokens, m.start(), allow_comma=True), P, 0.85, "name_before_relation")
    for m in DEVA_RELATION_RE.finditer(text):
        add(name_after(text, tokens, m.end(), allow_lower=False), R, 0.85, "relation_marker")
        add(name_before(text, tokens, m.start(), allow_comma=True), P, 0.85, "name_before_relation")
    for m in TITLE_RE.finditer(text):
        add(name_after(text, tokens, m.end(), allow_lower=False), P, 0.85, "title")
    for m in DEVA_TITLE_RE.finditer(text):
        add(name_after(text, tokens, m.end(), allow_lower=False), P, 0.85, "title")
    for m in BY_CUE_RE.finditer(text):
        add(name_after(text, tokens, m.end(), allow_lower=False, max_tokens=3), R, 0.85, "by_cue")
    for m in WHATSAPP_RE.finditer(text):
        span = name_after(text, tokens, m.end(), allow_lower=False, max_tokens=3)
        if span:
            add(span, R, 0.85, "message_sender")
    for m in TIMELINE_RE.finditer(text):
        span = name_after(text, tokens, m.end(), allow_lower=False, max_tokens=3)
        if not span:
            continue
        inside = [t for t in tokens if span[0] <= t.start < span[1]]
        if any(t.key in PROCEDURE_WORDS or t.key in ANATOMY_WORDS for t in inside):
            continue  # "14:00 - Blood Transfusion started": an action, not a person
        nxt = next((t for t in tokens if t.start >= span[1]), None)
        if nxt is not None and nxt.key in _ACTION_VERBS and text[span[1] : nxt.start] == " ":
            continue
        follow = text[span[1] : span[1] + 3]
        if len(inside) >= 2 or follow[:2] in (" (", " -", " –", ", "):
            add(span, _timeline_role(text, span), 0.8, "timeline")
    for m in MUSLIM_PREFIX_RE.finditer(text):
        span = name_after(text, tokens, m.end(), allow_lower=False, max_tokens=3)
        if span:
            add((m.start(), span[1]), P, 0.8, "name_prefix")
    for tok in tokens:
        honor = tok.key in _HONORIFIC_TOKENS or tok.text in DEVA_HONORIFICS
        if honor:
            span = name_before(text, tokens, tok.start)
            if span:
                kin = tok.key in KINSHIP_TERMS
                add(span, R if kin else P, 0.82, "kinship" if kin else "honorific")
    for m in ROLE_SUFFIX_RE.finditer(text):
        add(name_before(text, tokens, m.start()), R, 0.85, "role_suffix")
    for m in POSSESSIVE_RE.finditer(text):
        root = normalize_token(m.group(1))
        if root not in NOT_NAME_WORDS and root not in EPONYM_ROOTS:  # "Crohn's condition" is a disease
            add((m.start(1), m.end(1)), P, 0.8, "possessive")
    hits.extend(_gazetteer(text, tokens))
    return hits, keeps


def _gazetteer(text: str, tokens: list[Token]) -> Iterator[Hit]:
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if not _gap_ok(text, a.end, b.start):
            continue
        if a.is_devanagari and b.is_devanagari:
            if name_key(a.text) in _GIVEN_KEYS and name_key(b.text) in _SURNAME_KEYS and len(name_key(a.text)) >= 2:
                yield Hit(a.start, b.end, P, 0.75, "gazetteer")
            continue
        if not (_is_name_token(a, allow_lower=False) and _is_name_token(b, allow_lower=False)):
            continue
        if a.key in KNOWN_PLACES or b.key in KNOWN_PLACES:
            continue
        if a.key in GIVEN_NAMES and b.key in SURNAMES:
            yield Hit(a.start, b.end, P, 0.75, "gazetteer")
        elif a.key in GIVEN_NAMES and len(b.key) >= 3:
            yield Hit(a.start, b.end, P, 0.6, "gazetteer_weak")


_BARE_NAME_LABEL = re.compile(r"(?i)\s*(?:name|naam|नाम)\s*[:：\-–]\s*$")
_QUALIFIER_BEFORE = re.compile(r"([^\W\d_][\w\u0900-\u097f]*)(?:'s|’s)?[ \t]*(?:(?:का|की|के|ka|ki|ke)[ \t]+)?$")
_PERSON_LABEL_SEMS = frozenset({Sem.PERSON_NAME, Sem.RELATIVE_NAME, Sem.UNKNOWN})


def _qualified_non_person_label(text: str, m: re.Match[str]) -> bool:
    """A bare ``Name:`` label whose preceding word makes it a non-person label (Phase 2.1, P1).

    ``Test Name: Hemoglobin`` or ``Drug Name: Paracetamol`` would otherwise be read as a patient
    label, and the clinical value would seed the run-wide index. The two-word label is classified
    with the same classifier as column headers; anything that is not a person label (clinical,
    organisation, place, doctor, staff, file path) disables the patient-label rule. An unknown
    qualifier keeps it (recall first).
    """
    if not _BARE_NAME_LABEL.fullmatch(m.group()):
        return False
    start = max(text.rfind("\n", max(0, m.start() - 60), m.start()) + 1, m.start() - 60)  # bounded look-back
    q = _QUALIFIER_BEFORE.search(text[start : m.start()])
    if not q:
        return False
    sem = classify_label(f"{q.group(1)} name")
    return sem.sem not in _PERSON_LABEL_SEMS or sem.evidence == "path"


_RELATIVE_CONTEXT = re.compile(
    r"(?i)\b(?:attendant|relative|visitor|guardian|wife|husband|son|daughter|father|mother|brother|sister|"
    r"caretaker|escort|bystander|kin|informant|family|spouse)\b"
)


def _timeline_role(text: str, span: tuple[int, int]) -> EntityType:
    """Nursing/visitor log line: the person is a relative when the line says so, else the patient."""
    line_end = text.find("\n", span[1])
    rest = text[span[1] : line_end if line_end >= 0 else len(text)][:60]
    return R if _RELATIVE_CONTEXT.search(rest) else P


def looks_like_person_name(value: str) -> bool:
    """Shape check for values of name-labelled fields (1-5 alphabetic tokens, not clinical words)."""
    toks = tokenize(value)
    if not toks or len(toks) > 6 or any(t.key.isdigit() for t in toks):
        return False
    words = [t for t in toks if t.key not in PREFIX_TITLES and t.key not in {"s", "d", "w", "c", "o"}]
    return bool(words) and any(t.key not in NOT_NAME_WORDS for t in words)
