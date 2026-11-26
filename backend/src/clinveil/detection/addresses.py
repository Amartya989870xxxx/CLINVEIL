"""Indian address components (Latin and Devanagari).

Address text is found either through field semantics (an ``Address``/``पता``
column) or inline labels (``Address:``, ``पता:``, ``Vill.``, ``ग्राम:``). Inside an
address, comma-separated segments are classified:

  HOUSE      ``H.No. 712``, ``House 9``, ``Makan No. B-7``, ``मकान नं. 731``, ``Flat 3B``
  LOCALITY   ``Ward 17`` (address wards only), ``Mohalla Teen Batti``, ``… Colony/Nagar/Basti/Tola``
  LANDMARK   ``near Old Water Tank``, ``opp. Post Office``, ``behind Bus Stand``, ``… के पास/पीछे``
  VILLAGE    ``Vill. X``, ``Village X``, ``ग्राम X``, or an *unlabelled* segment of an address
  PIN        6-digit code after a district/PIN label or ending an address
  preserved  ``Tehsil X``, ``Distt. X``, ``जिला X``, state and known district names (Phase 4 generalises)

``C/O <name>`` segments are left to the relative-name detector.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from clinveil.detection.identifiers import Hit
from clinveil.detection.lexicon import UP_DISTRICTS
from clinveil.detection.text import DEVANAGARI_DIGITS, normalize_phrase
from clinveil.models.findings import EntityType

H, L, LM, V, PIN = (EntityType.HOUSE, EntityType.LOCALITY, EntityType.LANDMARK, EntityType.VILLAGE, EntityType.PIN)

HOUSE_RE = re.compile(
    r"(?i)^(?:H\.?\s?No\.?|House(?:\s+No\.?)?|Makan\s+No\.?|Flat(?:\s+No\.?)?|Plot(?:\s+No\.?)?|Door\s+No\.?|"
    r"Qtr\.?(?:\s+No\.?)?|मकान\s*(?:नं\.?|नंबर|संख्या)|म\.\s?नं\.?)\s*[:#]?\s*[\w/-]+"
)
WARD_RE = re.compile(r"(?i)^(?:Ward|वार्ड)\s*(?:No\.?\s*)?\d+$")
LOCALITY_RE = re.compile(
    r"(?i)^(?:(?:Mohalla|Mohallah|Muhalla|Mohl\.?|Colony|Gali|Galli|Lane|Street|Road|Sector|Basti|Tola)\b|"
    r"(?:मोहल्ला|मुहल्ला|गली|कॉलोनी)(?=\s|$)).*|.*\b(?:Colony|Nagar|Basti|Tola|Bazar|Bazaar|Puram|Enclave|Mohalla)$"
)
LANDMARK_RE = re.compile(
    r"(?i)^(?:near|nr\.?|opp\.?|opposite|behind|beside|in\s+front\s+of|next\s+to|"
    r"adjacent\s+to)\b.+|.+\s(?:के|की)\s(?:पास|पीछे|सामने|बगल\s+में|बगल)$"
)
VILLAGE_RE = re.compile(
    r"(?i)^(?:(?:Vill(?:age)?\.?|Gram|Gaon|Gaanv|Village)(?=[\s:.])|(?:ग्राम|गाँव|गांव)(?=[\s:]))"
    r"\s*[:.]?\s*(?P<v>.+)$"
)
_DEVA_END = r"(?=[\s:.,]|$)"  # \b is unreliable after Devanagari vowel signs
KEEP_RE = re.compile(
    r"(?i)^(?:(?:Tehsil|Tahsil|Teh\.?|Taluka?|Block|Distt?\.?|District|Jila|Zila|State|Uttar\s+Pradesh|"
    r"UP|U\.P\.)\b|(?:तहसील|जिला|ज़िला|राज्य|उत्तर\s+प्रदेश)" + _DEVA_END + ")"
)
CO_RE = re.compile(r"(?i)^(?:C/O|S/O|D/O|W/O|care\s+of)\b")
PIN_TAIL_RE = re.compile(r"(?:^|[\s\-–,:])(?P<pin>[1-9]\d{5})\s*$")
PIN_LABEL_RE = re.compile(r"(?i)(?:\bPIN(?:\s*Code)?|\bPincode|पिन(?:\s*कोड)?)\s*[:\-]?\s*(?P<pin>[1-9]\d{5})\b")
ADDRESS_LABEL_RE = re.compile(
    r"(?im)(?:\b(?:Address|Addr|Residence|Res\.)(?:\s*\([^)\n]{0,30}\))?\s*[:\-]|"
    r"पता(?:\s*\([^)\n]{0,30}\))?\s*[:\-])[ \t]*(?P<a>[^\n]+)"
)
INLINE_VILLAGE_RE = re.compile(
    r"(?i)(?:\bVill(?:age)?\.|\bVillage\s*:|\bGram\s*:|\bGaon\s*:|ग्राम\s*:?|गाँव\s*:?|गांव\s*:?)"
    r"[ \t]*(?P<v>[^,\n;:]{2,40}?)(?=\s*(?:,|\n|;|$|\s{2,}|\s+(?:Tehsil|तहसील|Distt|जिला)))"
)


def _segments(text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    i = start
    for part in re.split(r"(,|;|\n)", text[start:end]):
        if part in (",", ";", "\n"):
            i += len(part)
            continue
        s = i + (len(part) - len(part.lstrip()))
        e = i + len(part.rstrip())
        if e > s:
            yield s, e
        i += len(part)


def _is_known_place(seg: str) -> bool:
    keys = normalize_phrase(seg)
    return bool(keys) and (" ".join(keys) in UP_DISTRICTS or all(k in UP_DISTRICTS for k in keys))


def address_components(text: str, start: int = 0, end: int | None = None, *, base_conf: float = 0.85) -> list[Hit]:
    """Classify the comma-separated segments of ``text[start:end]`` as an address."""
    end = len(text) if end is None else end
    segs = list(_segments(text, start, end))
    hits: list[Hit] = []
    for n, (s, e) in enumerate(segs):
        seg = text[s:e]
        tail = PIN_TAIL_RE.search(seg.translate(DEVANAGARI_DIGITS))
        if tail and (n == len(segs) - 1 or KEEP_RE.match(seg)):
            hits.append(Hit(s + tail.start("pin"), s + tail.end("pin"), PIN, base_conf, "address_pin"))
            seg_core_end = s + tail.start("pin")
            seg = text[s:seg_core_end].rstrip(" -–,:")
            e = s + len(seg)
            if not seg:
                continue
        if CO_RE.match(seg) or KEEP_RE.match(seg) or _is_known_place(seg):
            continue
        if HOUSE_RE.match(seg):
            m = HOUSE_RE.match(seg)
            hits.append(Hit(s, s + m.end(), H, base_conf, "address_house"))
            rest = seg[m.end() :].strip(" ,")
            if rest and len(rest) > 2:
                r0 = s + seg.index(rest, m.end())
                hits.append(Hit(r0, r0 + len(rest), L, base_conf - 0.05, "address_house_rest"))
        elif WARD_RE.match(seg):
            hits.append(Hit(s, e, L, base_conf, "address_ward"))
        elif LANDMARK_RE.match(seg):
            hits.append(Hit(s, e, LM, base_conf, "address_landmark"))
        elif (vm := VILLAGE_RE.match(seg)) is not None:
            hits.append(Hit(s + vm.start("v"), s + vm.end("v"), V, base_conf, "address_village"))
        elif LOCALITY_RE.match(seg):
            hits.append(Hit(s, e, L, base_conf, "address_locality"))
        elif re.search(r"[A-Za-zऀ-ॿ]", seg) and not re.fullmatch(r"[\d\s/.-]+", seg):
            # unlabelled segment inside an address: the village / locality name
            nxt_keep = n + 1 < len(segs) and KEEP_RE.match(text[segs[n + 1][0] : segs[n + 1][1]])
            hits.append(Hit(s, e, V if nxt_keep else L, base_conf - 0.1, "address_unlabelled"))
    return hits


def detect_addresses(text: str) -> list[Hit]:
    """Address components in free text: labelled address lines, inline village and PIN labels."""
    hits: list[Hit] = []
    for m in ADDRESS_LABEL_RE.finditer(text):
        hits.extend(address_components(text, m.start("a"), m.end("a")))
    for m in INLINE_VILLAGE_RE.finditer(text):
        v = m.group("v").strip()
        if v and not _is_known_place(v):
            s = m.start("v") + (len(m.group("v")) - len(m.group("v").lstrip()))
            hits.append(Hit(s, s + len(v), V, 0.85, "village_label"))
    scan = text.translate(DEVANAGARI_DIGITS)
    for m in PIN_LABEL_RE.finditer(scan):
        hits.append(Hit(m.start("pin"), m.end("pin"), PIN, 0.9, "pin_label"))
    return hits
