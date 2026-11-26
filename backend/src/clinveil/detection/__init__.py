"""Multilingual, context-aware PII detection (Phase 2).

Layers (all operate on the Phase 1 IR, never on raw formats):

* ``text`` / ``translit``   offset-safe tokens, normalisation, scripts, cross-script name keys
* ``lexicon``               self-authored vocabularies (clinical, honorifics, kinship, places, names)
* ``semantics``             header / key / path classification (renamed and Hindi labels included)
* ``identifiers``           validated Indian identifiers (phone, Aadhaar+Verhoeff, ABHA, PAN, MRN…)
* ``names``                 contextual patient / relative names (labels, markers, honorifics, cues)
* ``addresses``             Indian address components
* ``clinical``              clinical-context and doctor protection (keep spans)
* ``value_index``           run-local index of confirmed values for cross-channel propagation
* ``resolve``               overlap resolution, protection, merging
* ``engine``                per-document orchestration producing typed :class:`~clinveil.models.findings.Finding` s
"""
