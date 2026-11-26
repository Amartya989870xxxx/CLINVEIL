"""JSON record enumeration and RFC 6901 pointers (starter-equivalent).

A document is treated as one record (``doc``) when it is a FHIR Bundle, not an
object, or has no top-level list of objects. Otherwise each element of each
top-level list-of-objects is a record ``/<key>/<i>``.
"""

from __future__ import annotations

import json
from typing import Any


def pointer_escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _is_record_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def is_single_document(data: Any) -> bool:
    return (
        not isinstance(data, dict)
        or data.get("resourceType") == "Bundle"
        or not any(_is_record_list(v) for v in data.values())
    )


def record_locators(data: Any) -> list[str]:
    if is_single_document(data):
        return ["doc"]
    return [f"/{pointer_escape(k)}/{i}" for k, v in data.items() if _is_record_list(v) for i in range(len(v))]


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
