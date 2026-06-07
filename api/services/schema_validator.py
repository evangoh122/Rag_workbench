import re
from typing import List
from api.models.eval_types import ExtractionResult, ValidationResult, ReasonCode, Provenance

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

        # 3. Required fields for 10-K/10-Q: period, Revenue, NetIncomeLoss, Assets.
        required_data_fields = ["Revenue", "NetIncomeLoss", "Assets"]
        
        if not result.period:
            if ReasonCode.MISSING_FIELD not in reason_codes:
                reason_codes.append(ReasonCode.MISSING_FIELD)
            is_valid = False
            
        field_names = {f.name for f in result.fields}
        for req in required_data_fields:
            if req not in field_names:
                if ReasonCode.MISSING_FIELD not in reason_codes:
                    reason_codes.append(ReasonCode.MISSING_FIELD)
                is_valid = False

        # 4. Unit sanity: if Revenue is reported as < 1,000,000, flag as ReasonCode.OUT_OF_RANGE
        revenue_field = next((f for f in result.fields if f.name == "Revenue"), None)
        if revenue_field and isinstance(revenue_field.value, (int, float)):
            if revenue_field.value < 1_000_000:
                reason_codes.append(ReasonCode.OUT_OF_RANGE)
                is_valid = False

        # 5. Enrichment Manifest
        # Generate an "Enrichment Manifest" in ValidationResult.details['enrichment_manifest'] 
        # mapping fields with Provenance.XBRL and their concepts.
        enrichment_manifest = {
            f.name: f.concept for f in result.fields if f.provenance == Provenance.XBRL and f.concept
        }
        
        return ValidationResult(
            is_valid=is_valid,
            reason_codes=reason_codes,
            details={"enrichment_manifest": enrichment_manifest}
        )
