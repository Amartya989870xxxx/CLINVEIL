"""Parsing into the common IR (:mod:`clinveil.models.document`).

* ``builder``      Detection -> Document (fields, records, channels, payloads, FHIR context)
* ``csv_format``   CSV/TSV read/write and conservative delimiter sniffing
* ``json_format``  record locators, RFC 6901 pointers, FHIR detection
* ``json_safety``  depth/size/node-bounded strict JSON loading
* ``fhir``         FHIR R4 element roles, Bundle entries, reference resolution
* ``attachments``  declared and embedded base64 payloads
"""
