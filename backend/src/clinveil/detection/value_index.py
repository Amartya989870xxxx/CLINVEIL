"""Run-local Sensitive Value Index: confirmed PII values found again in other channels.

Seeds come only from high-confidence findings (structured PII fields, explicit
labels, validated identifiers) made on the actual input during pass 1. Matching
in pass 2 is token-based, so punctuation and separators never matter
(``Orvila_Tamsen`` = ``Orvila Tamsen``; ``TST-26-004417`` = ``TST/26/004417``):

* ``phrases``      exact token-key sequences (IDs, e-mails, PAN, insurance, multi-token villages)
* ``name_seqs``    phonetic name-key sequences of full names (>= 2 tokens), so spelling
                   variants and Devanagari forms match (``Orvilla Tamssen`` ~ ``Orvila Tamsen``)
* ``name_tokens``  single *identifying* name tokens (>= 3 letters, not generic like
                   ``Devi``/``Kumar``, not a common or clinical word). In content they must
                   look like a name (capitalised Latin, or Devanagari); in filenames, keys,
                   headers and metadata any case matches
* ``digits``       phones (10-digit core), Aadhaar (12), ABHA (14), MRN digit cores (>= 5;
                   >= 6 in content unless zero-padded), matched as whole digit runs

The index lives only in memory for one run: it has no serialisation path, its
``repr`` shows sizes only, and it is discarded when the run ends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from clinveil.detection.identifiers import Hit, mrn_digit_core
from clinveil.detection.lexicon import (
    GENERIC_NAME_TOKENS,
    KINSHIP_TERMS,
    NOT_NAME_WORDS,
    PATIENT_HONORIFICS,
    PREFIX_TITLES,
    UP_DISTRICTS,
)
from clinveil.detection.text import Token, tokenize
from clinveil.detection.translit import name_key
from clinveil.models.channels import Channel
from clinveil.models.findings import EntityType

NAME_TYPES = frozenset({EntityType.PATIENT_NAME, EntityType.RELATIVE_NAME})
_NON_IDENTIFYING = (
    GENERIC_NAME_TOKENS | NOT_NAME_WORDS | PATIENT_HONORIFICS | KINSHIP_TERMS | PREFIX_TITLES | UP_DISTRICTS
)
_LOOSE_CHANNELS = frozenset({Channel.FILENAME, Channel.KEY, Channel.HEADER, Channel.METADATA})
_SEP_ONLY = re.compile(r"[ \t._\-/\\,:()]*")


def _identifying(tok: Token) -> bool:
    if tok.key in _NON_IDENTIFYING or tok.text in _NON_IDENTIFYING or tok.key.isdigit():
        return False
    return len(tok.key) >= (2 if tok.is_devanagari else 3)


@dataclass
class SensitiveValueIndex:
    phrases: dict[tuple[str, ...], EntityType] = field(default_factory=dict, repr=False)
    name_seqs: dict[tuple[str, ...], EntityType] = field(default_factory=dict, repr=False)
    name_tokens: dict[str, EntityType] = field(default_factory=dict, repr=False)
    digits: dict[str, EntityType] = field(default_factory=dict, repr=False)

    def __repr__(self) -> str:
        return (
            f"SensitiveValueIndex(phrases={len(self.phrases)}, names={len(self.name_seqs)}, "
            f"tokens={len(self.name_tokens)}, digits={len(self.digits)})"
        )

    def __reduce__(self):  # never pickled, never written anywhere
        raise TypeError("SensitiveValueIndex cannot be serialised")

    def __len__(self) -> int:
        return len(self.phrases) + len(self.name_seqs) + len(self.name_tokens) + len(self.digits)

    # ------------------------------------------------------------------ seeding
    def add(self, value: str, entity: EntityType) -> None:
        toks = tokenize(value)
        if not toks:
            return
        if entity in NAME_TYPES:
            words = [t for t in toks if not t.key.isdigit() and t.key not in PREFIX_TITLES]
            keys = tuple(k for k in (name_key(t.text) for t in words) if k)
            if len(keys) >= 2:
                self.name_seqs.setdefault(keys, entity)
            for t in words:
                if _identifying(t):
                    self.name_tokens.setdefault(t.key, entity)
            return
        digits = "".join(c for c in value if c.isdigit() and c.isascii()) or "".join(
            t.key for t in toks if t.key.isdigit()
        )
        if entity is EntityType.PHONE and len(digits) >= 10:
            self.digits.setdefault(digits[-10:], entity)
        elif entity in (EntityType.AADHAAR, EntityType.ABHA_NUMBER) and len(digits) in (12, 14):
            self.digits.setdefault(digits, entity)
        elif entity is EntityType.MRN:
            self.phrases.setdefault(tuple(t.key for t in toks), entity)
            core = mrn_digit_core(value)
            if len(core) >= 5:
                self.digits.setdefault(core, entity)
        elif entity in (EntityType.EMAIL, EntityType.PAN, EntityType.INSURANCE_ID, EntityType.ABHA_ADDRESS):
            self.phrases.setdefault(tuple(t.key for t in toks), entity)
        elif entity is EntityType.VILLAGE:
            keys = tuple(t.key for t in toks)
            if (len(keys) >= 2 or len(keys[0]) >= 6) and " ".join(keys) not in UP_DISTRICTS:
                self.phrases.setdefault(keys, entity)

    # ------------------------------------------------------------------ matching
    def match(self, text: str, channel: Channel) -> list[Hit]:
        if not len(self) or not text:
            return []
        toks = tokenize(text)
        loose = channel in _LOOSE_CHANNELS
        hits: list[Hit] = []
        self._match_phrases(text, toks, hits)
        self._match_names(text, toks, hits, loose)
        self._match_digits(text, toks, hits, loose)
        return hits

    def _match_phrases(self, text: str, toks: list[Token], hits: list[Hit]) -> None:
        if not self.phrases:
            return
        lengths = sorted({len(k) for k in self.phrases}, reverse=True)
        for i in range(len(toks)):
            for n in lengths:
                if i + n > len(toks):
                    continue
                key = tuple(t.key for t in toks[i : i + n])
                ent = self.phrases.get(key)
                if ent is not None and all(
                    _SEP_ONLY.fullmatch(text[toks[j].end : toks[j + 1].start]) for j in range(i, i + n - 1)
                ):
                    hits.append(Hit(toks[i].start, toks[i + n - 1].end, ent, 0.9, "propagation_phrase"))
                    break

    def _match_names(self, text: str, toks: list[Token], hits: list[Hit], loose: bool) -> None:
        keys = [name_key(t.text) if not t.key.isdigit() else "" for t in toks]
        for i in range(len(toks)):
            for n in (3, 2):
                seq = tuple(keys[i : i + n])
                if (
                    len(seq) == n
                    and all(seq)
                    and seq in self.name_seqs
                    and all(_SEP_ONLY.fullmatch(text[toks[j].end : toks[j + 1].start]) for j in range(i, i + n - 1))
                    and (loose or all(_looks_like_name(t) for t in toks[i : i + n]))
                ):
                    hits.append(Hit(toks[i].start, toks[i + n - 1].end, self.name_seqs[seq], 0.88, "propagation_name"))
                    break
            tok = toks[i]
            ent = self.name_tokens.get(tok.key)
            if ent is not None and (loose or _looks_like_name(tok)):
                hits.append(Hit(tok.start, tok.end, ent, 0.85 if loose else 0.78, "propagation_token"))

    def _match_digits(self, text: str, toks: list[Token], hits: list[Hit], loose: bool) -> None:
        if not self.digits:
            return
        # whole numeric tokens and runs of numeric tokens joined by phone-style separators
        i = 0
        while i < len(toks):
            if not toks[i].key.isdigit():
                core = re.search(r"\d{5,}$", toks[i].key)  # "adm009917" -> 009917
                if core and self.digits.get(core.group()) is EntityType.MRN:
                    hits.append(Hit(toks[i].start, toks[i].end, EntityType.MRN, 0.88, "propagation_digits"))
                i += 1
                continue
            j = i
            run = toks[i].key
            while (
                j + 1 < len(toks)
                and toks[j + 1].key.isdigit()
                and re.fullmatch(r"[ \-.]", text[toks[j].end : toks[j + 1].start])
                and len(run) < 14
            ):
                j += 1
                run += toks[j].key
            found = False
            for cand, a, b in ((run, i, j), (run[-10:], i, j)):
                ent = self.digits.get(cand)
                if ent is not None and ent is not EntityType.MRN:
                    hits.append(Hit(toks[a].start, toks[b].end, ent, 0.9, "propagation_digits"))
                    found = True
                    break
            if not found:
                for k in range(i, j + 1):
                    d = toks[k].key
                    ent = self.digits.get(d)
                    if ent is EntityType.MRN and (loose or len(d) >= 6 or d.startswith("0")):
                        hits.append(Hit(toks[k].start, toks[k].end, ent, 0.88, "propagation_digits"))
            i = j + 1


def _looks_like_name(tok: Token) -> bool:
    return tok.is_devanagari or tok.text[:1].isupper()
