"""Cross-script name normalisation (rule-based, deterministic, no external data).

* :func:`romanize` turns Devanagari into an approximate Latin spelling
  (``मोहम्मद`` -> ``mohammad``, ``शाहिद`` -> ``shahid``) using a hand-written
  akshara table with schwa deletion at word ends.
* :func:`name_key` maps a single name token in either script to a coarse phonetic
  key that is stable across common Indian spelling variants:

      Mohammad / Mohammed / Muhammad / Mohd / Md. / मोहम्मद  -> "mhmd"
      Seeta / Sita / सीता                                   -> "st"
      Tripathi / Tripathy / त्रिपाठी                        -> "trpt"

  It folds aspiration (``kh``->``k``, ``sh``->``s``…), ``w``/``v``, ``z``/``j``,
  ``q``/``k``, drops non-initial vowels and ``y``, and collapses repeats.

A key match is *evidence that two spellings may denote the same name*, never proof
that two records belong to the same person (that is Phase 3's decision, which
needs corroborating identifiers).
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_CONS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "n",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "n",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "ळ": "l",
    "\ue000": "gy",  # ज्ञ (rewritten to this private-use code point before scanning): "gyan", not "jnan"
}
_JNA = "\u091c\u094d\u091e"  # ज + virama + ञ
_NUKTA = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"}
_VOWELS = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "ऑ": "o",
}
_MATRAS = {
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ॉ": "o",
}
_VIRAMA, _NUKTA_SIGN = "्", "़"
_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}


@lru_cache(maxsize=50_000)
def romanize(text: str) -> str:
    """Approximate Latin spelling of Devanagari text; non-Devanagari characters pass through."""
    s = unicodedata.normalize("NFD", text).replace(_JNA, "\ue000")
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in _CONS:
            base = _CONS[ch]
            if i + 1 < n and s[i + 1] == _NUKTA_SIGN:
                base = _NUKTA.get(ch, base)
                i += 1
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in _MATRAS:
                out.append(base + _MATRAS[nxt])
                i += 2
                continue
            if nxt == _VIRAMA:
                out.append(base)
                i += 2
                continue
            # inherent schwa, dropped at the end of a word (schwa deletion)
            end_of_word = not nxt or not ("ऀ" <= nxt <= "ॿ") or nxt in _NASAL
            out.append(base if end_of_word and out else base + "a")
            i += 1
            continue
        if ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _NASAL:
            out.append(_NASAL[ch])
        elif ch in (_NUKTA_SIGN, _VIRAMA):
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_VARIANT_TOKENS = {
    "md": "mohammad",
    "mohd": "mohammad",
    "mohammed": "mohammad",
    "muhammad": "mohammad",
    "mohamad": "mohammad",
    "mohamed": "mohammad",
    "mohmmad": "mohammad",
    "mohammad": "mohammad",
    "mehmood": "mahmood",
}
_FOLDS = (
    ("chh", "c"),
    ("ch", "c"),
    ("sh", "s"),
    ("kh", "k"),
    ("gh", "g"),
    ("th", "t"),
    ("dh", "d"),
    ("ph", "f"),
    ("bh", "b"),
    ("b", "v"),  # Bimla / Vimla, Binod / Vinod (b/v alternate across Hindi, Bengali, Odia spellings)
    ("jh", "j"),
    ("w", "v"),
    ("z", "j"),
    ("q", "k"),
    ("x", "ks"),
    ("ck", "k"),
)
_VOWELS_RE = re.compile(r"[aeiouy]")
_REPEATS = re.compile(r"(.)\1+")


@lru_cache(maxsize=100_000)
def latin_name_form(token: str) -> str:
    """Lower-case Latin spelling of a name token in either script, with variants unified."""
    t = romanize(token) if any("ऀ" <= c <= "ॿ" for c in token) else token
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if c.isascii() and c.isalpha()).lower()
    return _VARIANT_TOKENS.get(t, t)


@lru_cache(maxsize=100_000)
def name_key(token: str) -> str:
    """Coarse phonetic key of one name token (see module docstring)."""
    t = latin_name_form(token)
    if not t:
        return ""
    for a, b in _FOLDS:
        t = t.replace(a, b)
    head = "a" if t[0] in "aeiou" else t[0]  # an initial vowel is kept as one class: Umar ~ Omar, Ishaan ~ Eshaan
    t = head + _VOWELS_RE.sub("", t[1:])
    return _REPEATS.sub(r"\1", t)


_STRICT_VOWELS = (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ou", "u"), ("ei", "e"))


@lru_cache(maxsize=100_000)
def name_key_strict(token: str) -> str:
    """Finer key that KEEPS vowel qualities (``Kiran`` != ``Karan``, ``Sita`` != ``Satya``).

    Consonants are folded as in :func:`name_key`; long vowels are shortened (``Neeta`` ==
    ``Nita`` == ``नीता``) and repeats collapsed. :func:`name_key` stays the recall-oriented
    key used for redaction; this one is for Phase 3 linking, where a false merge of two
    patients is worse than a missed variant.
    """
    t = latin_name_form(token)
    if not t:
        return ""
    for a, b in _FOLDS:
        t = t.replace(a, b)
    for a, b in _STRICT_VOWELS:
        t = t.replace(a, b)
    return _REPEATS.sub(r"\1", t)


def name_keys(tokens: list[str]) -> tuple[str, ...]:
    return tuple(k for k in (name_key(t) for t in tokens) if k)
