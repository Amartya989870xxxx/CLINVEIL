"""PII detection.

Target architecture (Phase 2): layered detectors that emit typed
:class:`clinveil.models.findings.Finding` objects and never edit text:

1. structural: column/key semantics (header/key classifiers that survive renames)
2. pattern: Indian IDs and phones with dose/lab-value guards
3. label/context: ``Name:``, ``नाम:``, ``Pt.``, honorifics, S/o D/o W/o C/O
4. gazetteer + transliteration: Latin <-> Devanagari name lists
5. propagation: a value found as PII anywhere is PII everywhere in the release
6. preserve rules: ``Dr. <name>``, doses (``1-0-1``, ``BD x 5 days``), eponyms, C/O complaints

The only detector today is the starter's regex baseline (``baseline_regex``).
"""
