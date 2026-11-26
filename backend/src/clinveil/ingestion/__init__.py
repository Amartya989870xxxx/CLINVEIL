"""Ingestion: safe discovery, content-based format detection, decoding and limits.

* ``discovery``    sorted, containment-checked file walk; streamed hashing
* ``signatures``   magic-byte detection of formats we never parse (PDF, images, archives, executables)
* ``decoding``     UTF-8 / UTF-8-BOM / UTF-16 (with or without BOM) / cp1252, with plausibility validation
* ``plausibility`` mojibake / corruption / binary-control heuristics
* ``detect``       the decision procedure: bytes + extension -> :class:`Detection` or a quarantine reason
* ``limits``       explicit resource limits derived from the policy

Every input is untrusted: nothing here follows symlinks out of the input root,
reads above the size cap, recurses without a bound, or trusts the extension.
"""
