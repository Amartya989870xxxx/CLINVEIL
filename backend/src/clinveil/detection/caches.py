"""Registry of the detection layer's memo caches, cleared at the end of every run.

Several pure helpers are memoised with :func:`functools.lru_cache` for speed
(token normalisation, transliteration, phonetic name keys, label
classification). Their keys are fragments of the input, so after a run they
would hold patient names and label text in process memory. The pipeline calls
:func:`clear_all` in a ``finally`` block, so no cache outlives the run that
filled it, also when the engine is used as a library (tests, notebooks).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _registered() -> list[Callable[..., Any]]:
    from clinveil.detection import semantics, text, translit

    return [
        text.normalize_token,
        translit.romanize,
        translit.latin_name_form,
        translit.name_key,
        translit.name_key_strict,
        semantics.classify_label,
        semantics.label_tokens,
        semantics._fuzzy,
    ]


def clear_all() -> None:
    for fn in _registered():
        fn.cache_clear()  # type: ignore[attr-defined]


def total_cached_entries() -> int:
    return sum(fn.cache_info().currsize for fn in _registered())  # type: ignore[attr-defined]
