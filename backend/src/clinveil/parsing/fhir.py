"""FHIR R4 enumeration (read-only: nothing here transforms data).

* :func:`context_for` gives every JSON field inside a FHIR document its
  resource type, Bundle entry, resource-relative element path
  (``Patient.identifier.value``) and a *role*:

  ``reference``    ``*.reference`` strings
  ``meta_source``  ``meta.source`` (Bundle or resource)
  ``narrative``    ``text.div`` XHTML
  ``attachment``   ``*.attachment.data`` / Attachment ``data``
  ``identifier``   anything under an ``identifier`` element
  ``date``         date/dateTime/instant elements with FHIR date syntax
  ``name`` / ``telecom`` / ``address`` / ``contact`` / ``photo``
                   identity elements of Patient, RelatedPerson, Person

* :func:`build_index` lists Bundle entries (``fullUrl``, type, id) and every
  reference with the entry it resolves to, so later phases can rewrite ids and
  references together and verify that the output still resolves.
"""

from __future__ import annotations

import re
from typing import Any

from clinveil.models.document import FhirContext, FhirEntry, FhirIndex, FhirReference
from clinveil.parsing.json_format import pointer

DATE_ELEMENTS = frozenset(
    {
        "birthDate",
        "deceasedDateTime",
        "date",
        "recordedDate",
        "authoredOn",
        "issued",
        "timestamp",
        "lastUpdated",
        "effectiveDateTime",
        "effectiveInstant",
        "performedDateTime",
        "onsetDateTime",
        "abatementDateTime",
        "occurrenceDateTime",
        "assertedDate",
        "created",
        "sent",
        "received",
        "whenPrepared",
        "whenHandedOver",
        "valueDate",
        "valueDateTime",
        "valueInstant",
        "start",
        "end",
    }
)
IDENTITY_ELEMENTS = frozenset({"name", "telecom", "address", "contact", "photo"})
PERSON_RESOURCES = frozenset({"Patient", "RelatedPerson", "Person"})
_FHIR_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?")


def _split(path: tuple[Any, ...], root: dict) -> tuple[int | None, str | None, tuple[Any, ...]]:
    """(entry index, resource type, resource-relative path) for a path from the root."""
    if root.get("resourceType") == "Bundle":
        if len(path) >= 3 and path[0] == "entry" and isinstance(path[1], int) and path[2] == "resource":
            entries = root.get("entry")
            res = entries[path[1]].get("resource") if isinstance(entries, list) else None
            rt = res.get("resourceType") if isinstance(res, dict) else None
            return path[1], rt if isinstance(rt, str) else None, path[3:]
        return None, None, path
    rt = root.get("resourceType")
    return None, rt if isinstance(rt, str) else None, path


def context_for(path: tuple[Any, ...], value: Any, root: dict) -> FhirContext:
    entry, rt, rel = _split(path, root)
    names = [p for p in rel if isinstance(p, str)]
    element = ".".join([rt or "Bundle", *names])
    last = names[-1] if names else None
    role: str | None = None
    if last == "reference":
        role = "reference"
    elif last == "source" and len(names) >= 2 and names[-2] == "meta":
        role = "meta_source"
    elif names[-2:] == ["text", "div"]:
        role = "narrative"
    elif last == "data" and ("attachment" in names or "content" in names or "photo" in names):
        role = "attachment"
    elif "identifier" in names:
        role = "identifier"
    elif last in DATE_ELEMENTS and isinstance(value, str) and _FHIR_DATE.fullmatch(value):
        role = "date"
    elif rt in PERSON_RESOURCES and names and names[0] in IDENTITY_ELEMENTS:
        role = names[0]
    return FhirContext(resource_type=rt, entry=entry, element=element, role=role)


def build_index(root: dict) -> FhirIndex:
    is_bundle = root.get("resourceType") == "Bundle"
    entries: list[FhirEntry] = []
    by_url: dict[str, int] = {}
    by_type_id: dict[str, int] = {}
    raw_entries = root.get("entry") if is_bundle else None
    if isinstance(raw_entries, list):
        for i, e in enumerate(raw_entries):
            if not isinstance(e, dict):
                continue
            res = e.get("resource") if isinstance(e.get("resource"), dict) else {}
            url = e.get("fullUrl") if isinstance(e.get("fullUrl"), str) else None
            rt = res.get("resourceType") if isinstance(res.get("resourceType"), str) else None
            rid = res.get("id") if isinstance(res.get("id"), str) else None
            entries.append(FhirEntry(i, pointer(("entry", i)), url, rt, rid))
            if url:
                by_url.setdefault(url, i)
            if rt and rid:
                by_type_id.setdefault(f"{rt}/{rid}", i)

    refs: list[FhirReference] = []
    stack: list[tuple[Any, tuple[Any, ...]]] = [(root, ())]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                p = (*path, k)
                if k == "reference" and isinstance(v, str):
                    entry, _, _ = _split(p, root)
                    refs.append(_resolve(pointer(p), v, entry, by_url, by_type_id))
                elif isinstance(v, dict | list):
                    stack.append((v, p))
        elif isinstance(node, list):
            stack.extend((v, (*path, i)) for i, v in enumerate(node) if isinstance(v, dict | list))
    refs.sort(key=lambda r: r.pointer)
    return FhirIndex(is_bundle=is_bundle, entries=entries, references=refs)


def _resolve(
    ptr: str, value: str, source: int | None, by_url: dict[str, int], by_type_id: dict[str, int]
) -> FhirReference:
    if value.startswith("#"):
        return FhirReference(ptr, value, source, None, contained=True)
    if value in by_url:
        return FhirReference(ptr, value, source, by_url[value])
    tail = "/".join(value.rstrip("/").split("/")[-2:])  # "Patient/123" or ".../Patient/123"
    return FhirReference(ptr, value, source, by_type_id.get(tail))
