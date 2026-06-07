import unittest
from unittest.mock import MagicMock
from api.models.eval_types import ExtractionResult, ExtractedField, Provenance, ValidationResult, ReasonCode
from api.services.xbrl_validator import XbrlCrossValidator

class TestXbrlValidator(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.validator = XbrlCrossValidator(client=self.mock_client)

    def test_validate_match(self):
        # Setup result
        fields = [
            ExtractedField(name="Revenue", value=100.0, provenance=Provenance.XBRL, concept="Revenue"),
            ExtractedField(name="NetIncome", value=50.0, provenance=Provenance.XBRL, concept="NetIncomeLoss")
        ]
        result = ExtractionResult(
            cik="0000320193",
            accession="0000320193-23-000064",
            form_type="10-K",
            period="2023-09-30",
            fields=fields
        )
        
        # Setup validation state
        validation_state = ValidationResult(
            is_valid=True,
            details={"enrichment_manifest": {"Revenue": "Revenue", "NetIncome": "NetIncomeLoss"}}
        )
        
        # Mock client behavior
        self.mock_client.get_fact.side_effect = lambda cik, concept, period: 100.0 if concept == "Revenue" else 50.0
        
        # Run validation
        self.validator.validate(result, validation_state)
        
        # Assertions
        self.assertTrue(validation_state.is_valid)
        self.assertEqual(validation_state.details['cross_validation_results']['Revenue']['status'], 'match')
        self.assertEqual(validation_state.details['cross_validation_results']['Revenue']['confidence'], 1.0)
        self.assertEqual(validation_state.details['cross_validation_results']['NetIncome']['status'], 'match')

    def test_validate_mismatch(self):
        # Setup result
        fields = [
            ExtractedField(name="Revenue", value=110.0, provenance=Provenance.XBRL, concept="Revenue")
        ]
        result = ExtractionResult(
            cik="0000320193",
            accession="0000320193-23-000064",
            form_type="10-K",
            period="2023-09-30",
            fields=fields
        )
        
        # Setup validation state
        validation_state = ValidationResult(
            is_valid=True,
            details={"enrichment_manifest": {"Revenue": "Revenue"}}
        )
        
        # Mock client behavior (ground truth is 100.0, extracted is 110.0 -> > 1% diff)
        self.mock_client.get_fact.return_value = 100.0
        
        # Run validation
        self.validator.validate(result, validation_state)
        
        # Assertions
        self.assertFalse(validation_state.is_valid)
        self.assertIn(ReasonCode.XBRL_MISMATCH, validation_state.reason_codes)
        self.assertEqual(validation_state.details['cross_validation_results']['Revenue']['status'], 'mismatch')
        self.assertEqual(validation_state.details['cross_validation_results']['Revenue']['confidence'], 0.0)

    def test_validate_within_tolerance(self):
        # Setup result (100.5 is within 1% of 100.0)
        fields = [
            ExtractedField(name="Revenue", value=100.5, provenance=Provenance.XBRL, concept="Revenue")
        ]
        result = ExtractionResult(
            cik="0000320193",
            accession="0000320193-23-000064",
            form_type="10-K",
            period="2023-09-30",
            fields=fields
        )
        
        validation_state = ValidationResult(
            is_valid=True,
            details={"enrichment_manifest": {"Revenue": "Revenue"}}
        )
        
        self.mock_client.get_fact.return_value = 100.0
        
        self.validator.validate(result, validation_state)
        
        self.assertTrue(validation_state.is_valid)
        self.assertEqual(validation_state.details['cross_validation_results']['Revenue']['status'], 'match')

    def test_no_manifest(self):
        result = ExtractionResult(cik="1", accession="1", form_type="1", period="2023-01-01", fields=[])
        validation_state = ValidationResult(is_valid=True, details={})
        
        self.validator.validate(result, validation_state)
        self.assertTrue(validation_state.is_valid)
        self.assertNotIn('cross_validation_results', validation_state.details)

    def test_fact_not_found_in_api(self):
        fields = [ExtractedField(name="Revenue", value=100.0, provenance=Provenance.XBRL, concept="Revenue")]
        result = ExtractionResult(cik="1", accession="1", form_type="1", period="2023-01-01", fields=fields)
        validation_state = ValidationResult(is_valid=True, details={"enrichment_manifest": {"Revenue": "Revenue"}})
        
        self.mock_client.get_fact.return_value = None
        
        self.validator.validate(result, validation_state)
        
        self.assertTrue(validation_state.is_valid)
        self.assertEqual(validation_state.details['cross_validation_results'], {})

if __name__ == '__main__':
    unittest.main()
