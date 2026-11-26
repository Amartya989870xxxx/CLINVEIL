"""Typed PII findings: the contract between detection and sanitisation.

Detectors emit ``Finding`` objects; they never edit text. The sanitiser resolves
overlaps and applies ``action``. ``surface`` holds the original text and is
excluded from ``repr`` so a finding can never leak PII into a log or traceback.

Entity type names match the evaluator's ``scoring.toml`` type weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EntityType(str, Enum):
    PATIENT_NAME = "PATIENT_NAME"
    RELATIVE_NAME = "RELATIVE_NAME"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    AADHAAR = "AADHAAR"
    AADHAAR_MASKED = "AADHAAR_MASKED"
    ABHA_NUMBER = "ABHA_NUMBER"
    ABHA_ADDRESS = "ABHA_ADDRESS"
    MRN = "MRN"
    PAN = "PAN"
    INSURANCE_ID = "INSURANCE_ID"
    DOB = "DOB"
    HOUSE = "HOUSE"
    LOCALITY = "LOCALITY"
    LANDMARK = "LANDMARK"
    VILLAGE = "VILLAGE"
    PIN = "PIN"
    AGE = "AGE"  # quasi-identifier: generalised, not removed
    DATE = "DATE"  # clinical date: shifted, not removed


class Channel(str, Enum):
    """Where the PII hides (mirrors the truth file's ``channel``)."""

    CONTENT = "content"
    FILENAME = "filename"
    HEADER = "header"
    KEY = "key"
    METADATA = "metadata"
    BASE64 = "base64"


class Action(str, Enum):
    REDACT = "redact"  # replace with a typed placeholder
    PSEUDONYMIZE = "pseudonymize"  # replace with the patient pseudonym
    GENERALIZE = "generalize"  # age band, district, PIN prefix
    SHIFT = "shift"  # per-patient date shift
    KEEP = "keep"  # explicit "not PII" decision (doctor, dose, eponym)


class Method(str, Enum):
    REGEX = "regex"
    COLUMN = "column"
    LABEL = "label"
    GAZETTEER = "gazetteer"
    CONTEXT = "context"
    LINKED_VALUE = "linked_value"  # a value already known to be PII elsewhere in the release


@dataclass(frozen=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True)
class Finding:
    entity: EntityType
    channel: Channel
    locator: str  # record locator: "row:3", "/visits/2", "doc", "@header", "@filename"
    span: Span | None
    confidence: float
    method: Method
    action: Action
    surface: str = field(repr=False, compare=True)  # ORIGINAL TEXT: never log, never repr

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
