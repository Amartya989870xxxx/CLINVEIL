"""Text primitives with offset safety: tokens, per-token normalisation, scripts.

Rule: detectors never compute offsets on a normalised copy of a string. Tokens
carry ``(start, end)`` code-point offsets into the ORIGINAL string, and each
token's normalised ``key`` is derived from its own original slice, so a match on
keys always maps back to an exact original span.

A *word character* is a letter, combining mark, number, or zero-width (non-)joiner,
so Devanagari words with matras, viramas and nuktas are single tokens.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

#: Every Unicode decimal digit (Devanagari, Bengali, Gurmukhi, Gujarati, Tamil, Telugu,
#: Kannada, Malayalam, Odia, full-width, Arabic-Indic…) -> ASCII. One code point maps to
#: one code point, so offsets computed on the translated text are valid on the original.
UNICODE_DIGITS = {
    cp: ord(str(unicodedata.digit(chr(cp))))
    for cp in range(0x80, 0x20000)
    if unicodedata.category(chr(cp)) == "Nd" and unicodedata.digit(chr(cp), None) is not None
}
DEVANAGARI_DIGITS = UNICODE_DIGITS  # historical name: covers all scripts since Phase 2.1
_ZERO_WIDTH = "​‌‍⁠﻿"
_ZW_DELETE = str.maketrans("", "", _ZERO_WIDTH)
_HINGLISH_FUNCTION_WORDS = frozenset(
    "hai hain ka ki ke ko ne se aur nahi nahin bhi raha rahi rahe gaya gayi gaye diya diye liya lena lene karo "
    "kare karna ho hua hui tha thi the ab abhi kal aaj bahut thoda kya kyun kaise mein par wala wali bola boli "
    "kiya kar de do dena chahiye theek sahi utar bukhar dard dawa khana neend raat subah shaam ghar".split()
)


def is_word_char(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LMN" or ch in "‌‍"


def is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ" or "꣠" <= ch <= "ꣿ"


@dataclass(frozen=True, slots=True)
class Token:
    start: int
    end: int
    text: str  # original slice (never logged)
    key: str  # normalised form used for matching

    def __repr__(self) -> str:
        return f"Token({self.start}:{self.end})"

    @property
    def is_devanagari(self) -> bool:
        return any(is_devanagari(c) for c in self.text)

    @property
    def is_capitalized(self) -> bool:
        return self.text[:1].isupper()

    @property
    def is_numeric(self) -> bool:
        return self.key.isdigit()


@lru_cache(maxsize=200_000)
def normalize_token(s: str) -> str:
    """NFKC, zero-width removal, any-script digits -> ASCII, nukta folding, casefold."""
    s = unicodedata.normalize("NFKC", s).translate(_ZW_DELETE).translate(DEVANAGARI_DIGITS)
    s = unicodedata.normalize("NFD", s).replace("़", "")  # nukta: क़ == क for matching
    return unicodedata.normalize("NFC", s).casefold()


def tokenize(text: str) -> list[Token]:
    out: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        if is_word_char(text[i]):
            j = i + 1
            while j < n and is_word_char(text[j]):
                j += 1
            raw = text[i:j]
            out.append(Token(i, j, raw, normalize_token(raw)))
            i = j
        else:
            i += 1
    return out


def normalize_phrase(s: str) -> tuple[str, ...]:
    """Token-key sequence of a phrase: punctuation and separators are irrelevant."""
    return tuple(t.key for t in tokenize(s))


def digits_only(s: str) -> str:
    return "".join(c for c in s.translate(DEVANAGARI_DIGITS) if c.isdigit() and c.isascii())


def script_of(text: str) -> str:
    """``deva`` if any Devanagari letter, ``latin`` if Latin letters, ``mixed`` if both, ``none`` otherwise."""
    deva = any(is_devanagari(c) and unicodedata.category(c)[0] == "L" for c in text)
    latin = any(c.isascii() and c.isalpha() for c in text)
    if deva and latin:
        return "mixed"
    return "deva" if deva else ("latin" if latin else "none")


def is_hinglish(text: str) -> bool:
    """Romanised Hindi cue: at least two Hindi function words among Latin tokens."""
    keys = [t.key for t in tokenize(text) if not t.is_devanagari]
    return sum(k in _HINGLISH_FUNCTION_WORDS for k in keys) >= 2


def language_of(text: str) -> str:
    """Coarse span language for metrics: ``deva``, ``hinglish`` or ``latin`` (``none`` if no letters)."""
    sc = script_of(text)
    if sc in ("deva", "mixed") and any(is_devanagari(c) for c in text):
        return "deva"
    if sc == "none":
        return "none"
    return "hinglish" if is_hinglish(text) else "latin"
