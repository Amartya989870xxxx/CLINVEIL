"""Typed PII findings: the auditable contract between detection and sanitisation.

A :class:`Finding` records *where* personal data is (field address and code-point
offsets into that field's ORIGINAL value), *what* it is, *how sure* we are, *which*
detector found it and on *what kind of evidence*, and what to do with it. It never
stores the matched text, so a finding cannot leak PII through ``repr``, logs,
tracebacks or reports.

Entity names follow the evaluator vocabulary (``scoring.toml`` type weights);
``DOCTOR_NAME`` exists only to record explicit preservation decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from clinveil.models.channels import Channel

__all__ = ["Action", "Channel", "EntityType", "Evidence", "Finding"]


class EntityType(str, Enum):
    PATIENT_NAME = "PATIENT_NAME"
    RELATIVE_NAME = "RELATIVE_NAME"
    DOCTOR_NAME = "DOCTOR_NAME"  # preserved
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    AADHAAR = "AADHAAR"
    AADHAAR_MASKED = "AADHAAR_MASKED"
    ABHA_NUMBER = "ABHA_NUMBER"
    ABHA_ADDRESS = "ABHA_ADDRESS"
    PAN = "PAN"
    MRN = "MRN"  # UHID, registration, IPD/admission numbers
    INSURANCE_ID = "INSURANCE_ID"
    HOUSE = "HOUSE"
    LOCALITY = "LOCALITY"
    LANDMARK = "LANDMARK"
    VILLAGE = "VILLAGE"
    PIN = "PIN"
    DOB = "DOB"


#: Direct identifiers (the evaluator's "critical" leaks); the rest are quasi-identifiers.
DIRECT = frozenset(
    {
        EntityType.PATIENT_NAME,
        EntityType.PHONE,
        EntityType.EMAIL,
        EntityType.AADHAAR,
        EntityType.ABHA_NUMBER,
        EntityType.ABHA_ADDRESS,
        EntityType.PAN,
        EntityType.MRN,
        EntityType.INSURANCE_ID,
    }
)


class Evidence(str, Enum):
    FIELD_SEMANTICS = "field_semantics"  # the value of a field whose label means PII
    VALIDATED_PATTERN = "validated_pattern"  # structure + checksum / unambiguous format
    PATTERN = "pattern"
    LABEL = "label"  # inline label or relationship marker ("Name:", "S/o", "पिता का नाम:")
    CONTEXT = "context"  # honorific, kinship, title, timeline, role cue
    ADDRESS_STRUCTURE = "address_structure"
    GAZETTEER = "gazetteer"
    PROPAGATION = "propagation"  # a confirmed value seen again elsewhere


class Action(str, Enum):
    REDACT = "redact"  # typed placeholder
    GENERALIZE = "generalize"  # e.g. FHIR birthDate -> birth year (keeps the element valid)


@dataclass(frozen=True, slots=True)
class Finding:
    entity: EntityType
    start: int  # code-point offsets into the field's ORIGINAL value
    end: int
    confidence: float
    detector: str
    evidence: Evidence
    action: Action
    field: str  # field address within the document
    record: str  # record locator
    channel: Channel
    document: str  # safe document id (SHA-256 prefix), never a file name
    clinical_conflict: bool = False  # overlapped a clinical keep span but evidence was strong enough

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.end < self.start:
            raise ValueError("finding end precedes start")

    @property
    def direct(self) -> bool:
        return self.entity in DIRECT

    @property
    def quasi(self) -> bool:
        return not self.direct
