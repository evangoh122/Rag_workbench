import re
from typing import List, Optional
from api.models.eval_types import ExtractionResult, ValidationResult, ReasonCode, Provenance

# Concept families for required field detection.
# EdgarTools sets f.name = human-readable label (e.g. "Net sales") and
# f.concept = GAAP concept tag.  We match on EITHER so tests using
# name="Revenue" (no concept) and real filings using concept= both pass.
REVENUE_CONCEPTS = {
    "Revenue",
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
}
NET_INCOME_CONCEPTS = {"NetIncomeLoss", "NetIncome", "ProfitLoss"}
ASSETS_CONCEPTS = {"Assets"}

_REQUIRED_CONCEPT_FAMILIES = [REVENUE_CONCEPTS, NET_INCOME_CONCEPTS, ASSETS_CONCEPTS]


def _field_matches_family(f, family: set) -> bool:
    """Return True if f.name OR f.concept is in the concept family."""
    if f.name in family:
        return True
    if f.concept and f.concept in family:
        return True
    return False


def _find_revenue_field(fields):
    """Return the first field that belongs to the Revenue concept family, or None."""
    for f in fields:
        if _field_matches_family(f, REVENUE_CONCEPTS):
            return f
    return None


class SchemaValidator:
    """
    Validates the basic schema and format of ExtractionResult.
    """

    @staticmethod
    def validate(result: ExtractionResult) -> ValidationResult:
        reason_codes: List[ReasonCode] = []
        is_valid = True

        # 1. CIK format: ^\d{10}$
        if not re.match(r"^\d{10}$", result.cik):
            reason_codes.append(ReasonCode.BAD_TYPE)
            is_valid = False

        # 2. Accession format: ^\d{10}-\d{2}-\d{6}$
        if not re.match(r"^\d{10}-\d{2}-\d{6}$", result.accession):
            if ReasonCode.BAD_TYPE not in reason_codes:
                reason_codes.append(ReasonCode.BAD_TYPE)
            is_valid = False

        # 3. Required fields for 10-K/10-Q: period, Revenue family, NetIncomeLoss family, Assets.
        # Match on f.name OR f.concept so both hardcoded test names and real EdgarTools
        # human-readable labels (with concept= set) are accepted.
        if not result.period:
            if ReasonCode.MISSING_FIELD not in reason_codes:
                reason_codes.append(ReasonCode.MISSING_FIELD)
            is_valid = False

        for family in _REQUIRED_CONCEPT_FAMILIES:
            if not any(_field_matches_family(f, family) for f in result.fields):
                if ReasonCode.MISSING_FIELD not in reason_codes:
                    reason_codes.append(ReasonCode.MISSING_FIELD)
                is_valid = False

        # 4. Unit sanity: if Revenue is reported as < 1,000,000, flag as ReasonCode.OUT_OF_RANGE
        revenue_field = _find_revenue_field(result.fields)
        if revenue_field and isinstance(revenue_field.value, (int, float)):
            if revenue_field.value < 1_000_000:
                reason_codes.append(ReasonCode.OUT_OF_RANGE)
                is_valid = False

        # 5. Enrichment Manifest
        # Generate an "Enrichment Manifest" in ValidationResult.details['enrichment_manifest']
        # mapping fields with Provenance.XBRL and their concepts.
        # Uses f.name as the key (unchanged) for downstream compatibility.
        enrichment_manifest = {
            f.name: f.provenance for f in result.fields if f.provenance == Provenance.XBRL
        }

        return ValidationResult(
            is_valid=is_valid,
            reason_codes=reason_codes,
            details={"enrichment_manifest": enrichment_manifest}
        )
