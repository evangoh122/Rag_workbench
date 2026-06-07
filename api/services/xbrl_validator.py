import logging
from typing import Dict, Any
from api.models.eval_types import ExtractionResult, ValidationResult, ReasonCode
from api.services.companyfacts_client import CompanyFactsClient

logger = logging.getLogger(__name__)

class XbrlCrossValidator:
    def __init__(self, client: CompanyFactsClient = None):
        self.client = client or CompanyFactsClient()

    def validate(self, result: ExtractionResult, validation_state: ValidationResult):
        """
        Cross-validates extracted fields against ground truth XBRL facts.
        
        Args:
            result: The ExtractionResult to validate.
            validation_state: The current ValidationResult (modified in-place).
        """
        manifest = validation_state.details.get('enrichment_manifest', {})
        if not manifest:
            logger.debug("No enrichment_manifest found in validation_state. Skipping XBRL cross-validation.")
            return

        cross_validation_results = {}
        period_end = result.period
        
        if not period_end:
            logger.warning(f"No period found for result {result.accession}. Cannot perform XBRL cross-validation.")
            return

        for field_name in manifest:
            field = next((f for f in result.fields if f.name == field_name), None)
            if not field or field.value is None:
                continue

            concept = field.concept
            if not concept:
                continue

            try:
                ground_truth = self.client.get_fact(result.cik, concept, period_end)
                
                if ground_truth is not None:
                    # Compare with 1% tolerance
                    try:
                        extracted_value = float(field.value)
                        diff = abs(extracted_value - ground_truth)
                        tolerance = abs(ground_truth * 0.01)
                        
                        if diff <= tolerance:
                            cross_validation_results[field_name] = {
                                "status": "match",
                                "confidence": 1.0,
                                "ground_truth": ground_truth
                            }
                        else:
                            logger.warning(f"XBRL Mismatch for {field_name}: extracted={extracted_value}, ground_truth={ground_truth}")
                            cross_validation_results[field_name] = {
                                "status": "mismatch",
                                "confidence": 0.0,
                                "ground_truth": ground_truth
                            }
                            if ReasonCode.XBRL_MISMATCH not in validation_state.reason_codes:
                                validation_state.reason_codes.append(ReasonCode.XBRL_MISMATCH)
                            validation_state.is_valid = False
                    except (ValueError, TypeError):
                        logger.error(f"Could not convert field {field_name} value to float: {field.value}")
                        continue
            except Exception as e:
                logger.error(f"Error during cross-validation for field {field_name}: {e}")
                continue

        validation_state.details['cross_validation_results'] = cross_validation_results
