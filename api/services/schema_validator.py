"""
schema_validator.py — Layer-1 validation (Phase 2).
Checks field presence, types, and unit sanity per form type.
"""
from __future__ import annotations

import re
from typing import Callable

from api.models.eval_types import (
    ExtractionResult, ExtractedField, ValidationResult, ReasonCode, Provenance,
)

ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
CIK_RE = re.compile(r"^\d{1,10}$")

REQUIRED_FIELDS_BY_FORM: dict[str, list[str]] = {
    "10-K": [
        "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
        "StockholdersEquity", "OperatingIncomeLoss",
    ],
    "10-Q": [
        "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
        "StockholdersEquity",
    ],
    "8-K": [],
}

def validate_extraction(result: ExtractionResult) -> ValidationResult:
    reason_codes: list[ReasonCode] = []
    details: dict = {}

    if not CIK_RE.fullmatch(result.cik):
        reason_codes.append(ReasonCode.BAD_TYPE)
        details["cik"] = f"Expected 1-10 digits, got '{result.cik}'"

    if not ACCESSION_RE.match(result.accession):
        reason_codes.append(ReasonCode.BAD_TYPE)
        details["accession"] = f"Expected nnnnnnnnnn-nn-nnnnnn format, got '{result.accession}'"

    field_map = {f.name: f for f in result.fields if f.name}

    required = REQUIRED_FIELDS_BY_FORM.get(result.form_type, [])
    for field_name in required:
        if field_name not in field_map:
            reason_codes.append(ReasonCode.MISSING_FIELD)
            details.setdefault("missing_fields", []).append(field_name)
        else:
            field = field_map[field_name]
            if not isinstance(field.value, (int, float)):
                reason_codes.append(ReasonCode.BAD_TYPE)
                details.setdefault("bad_types", {})[field_name] = f"Expected numeric, got {type(field.value).__name__}"

    for field in result.fields:
        if field.provenance == Provenance.XBRL and isinstance(field.value, (int, float)):
            if _is_suspicious_scale(field):
                reason_codes.append(ReasonCode.OUT_OF_RANGE)
                details.setdefault("scale_warnings", {})[field.name] = (
                    f"Value {field.value:,.0f} appears to be in thousands but provenance is XBRL"
                )

    is_valid = len(reason_codes) == 0
    return ValidationResult(is_valid=is_valid, reason_codes=reason_codes, details=details)


def _is_suspicious_scale(field: ExtractedField) -> bool:
    if not isinstance(field.value, (int, float)):
        return False
    v = abs(field.value)
    if v > 1e12:
        return True
    return False


def _required_field_checker(form_type: str) -> Callable[[ExtractionResult], bool]:
    """Factory for predicate-style checks."""
    required = REQUIRED_FIELDS_BY_FORM.get(form_type, [])
    field_names = [f.name for f in []]
    def check(result: ExtractionResult) -> bool:
        names = {f.name for f in result.fields}
        return all(r in names for r in required)
    return check
