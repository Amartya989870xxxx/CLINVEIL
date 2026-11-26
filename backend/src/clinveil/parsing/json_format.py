# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""JSON record enumeration and RFC 6901 pointers (starter-equivalent).

A document is treated as one record (``doc``) when it is a FHIR resource (a
Bundle or any object with a string ``resourceType``), not an object, or has no
top-level list of objects. Otherwise each element of each top-level
list-of-objects is a record ``/<key>/<i>``.
"""

from __future__ import annotations

import json
from typing import Any


def pointer_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def pointer(path: tuple[Any, ...] | list[Any]) -> str:
    """RFC 6901 pointer for a structural path of keys and indices (``()`` -> ``""``)."""
    return "".join("/" + (pointer_escape(p) if isinstance(p, str) else str(p)) for p in path)


def is_fhir(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("resourceType"), str)


def _is_record_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


_SINGLE_PATIENT_OBJECT_KEYS = frozenset({"patient", "subject", "beneficiary", "client"})
_MULTI_RECORD_LIST_KEYS = frozenset(
    {"patients", "visits", "records", "results", "claims", "encounters", "admissions", "entries", "rows", "tickets"}
)


def is_single_document(data: Any) -> bool:
    if not isinstance(data, dict) or is_fhir(data):
        return True
    list_keys = [k for k, v in data.items() if _is_record_list(v)]
    if not list_keys:
        return True
    # A single-patient report (e.g. lab report with top-level "patient": {...} and "panels": [...])
    # is one document ("doc"), not one record per sub-panel.
    has_single_patient_obj = any(
        k.lower() in _SINGLE_PATIENT_OBJECT_KEYS and isinstance(v, dict) for k, v in data.items()
    )
    return bool(has_single_patient_obj and not any(k.lower() in _MULTI_RECORD_LIST_KEYS for k in list_keys))


def record_locators(data: Any) -> list[str]:
    if is_single_document(data):
        return ["doc"]
    return [f"/{pointer_escape(k)}/{i}" for k, v in data.items() if _is_record_list(v) for i in range(len(v))]


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
