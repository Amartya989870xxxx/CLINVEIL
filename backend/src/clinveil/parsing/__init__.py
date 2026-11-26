"""Format-specific parsing and record enumeration.

Parsers preserve structure (CSV header/delimiter, JSON key paths and value types,
FHIR references) and define the record locators used in ``records.jsonl``.
Phase 1 adds a common internal representation and FHIR-aware enumeration.
"""
