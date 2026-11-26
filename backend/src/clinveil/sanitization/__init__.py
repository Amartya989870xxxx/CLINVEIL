"""Sanitisation: apply detection decisions to each format while preserving structure.

Invariants: CSV keeps delimiter, header and row count; JSON keeps key paths and
value types; FHIR stays a valid R4 Bundle with resolvable references; nothing
unprocessed is ever written to ``sanitized/``.
"""
