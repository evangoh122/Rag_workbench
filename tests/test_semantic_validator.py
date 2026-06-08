"""
tests/test_semantic_validator.py

Unit tests for SemanticValidator (api/services/semantic_validator.py).
The validator performs three checks in-place on a ValidationResult:
  1. Accounting identity (Assets = Liabilities + Equity, Revenue - COGS = GrossProfit)
  2. Referential integrity (extracted company name fuzzy-matches EDGAR company name)
  3. Plausibility (current value within 3 std deviations of historical values)

Run with: python -m pytest tests/test_semantic_validator.py -v
      or:  python -m unittest tests.test_semantic_validator
"""
import unittest
from unittest.mock import MagicMock

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
    ValidationResult,
    ReasonCode,
)
from api.services.semantic_validator import SemanticValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(fields: list[ExtractedField], cik: str = "0000320193") -> ExtractionResult:
    return ExtractionResult(
        cik=cik,
        accession="0000320193-23-000064",
        form_type="10-K",
        period="2023-09-30",
        fields=fields,
    )


def _xbrl_field(name: str, value: float, concept: str | None = None) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=value,
        provenance=Provenance.XBRL,
        concept=concept or name,
    )


def _make_mock_client(historical: list[float] | None = None, company_name: str = "Apple Inc") -> MagicMock:
    client = MagicMock()
    client.get_historical_values.return_value = historical if historical is not None else []
    mock_company = MagicMock()
    mock_company.name = company_name
    client._get_company_object.return_value = mock_company
    return client


# ---------------------------------------------------------------------------
# Identity violation tests
# ---------------------------------------------------------------------------

class TestIdentityViolation(unittest.TestCase):
    """Balance-sheet / income-statement accounting identity checks."""

    def setUp(self):
        self.client = _make_mock_client()

    def test_identity_violation_balance_sheet(self):
        """Assets=1000, Liabilities=600, Equity=200 => 1000 != 800 => IDENTITY_VIOLATION."""
        fields = [
            _xbrl_field("Assets", 1000, "Assets"),
            _xbrl_field("Liabilities", 600, "Liabilities"),
            _xbrl_field("StockholdersEquity", 200, "StockholdersEquity"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=self.client)
        validator.validate(result, state)

        self.assertFalse(state.is_valid)
        self.assertIn(ReasonCode.IDENTITY_VIOLATION, state.reason_codes)
        self.assertIn("identity_violations", state.details)
        self.assertGreater(len(state.details["identity_violations"]), 0)

    def test_identity_pass_within_tolerance(self):
        """Assets=1000, Liabilities=600, Equity=401 => diff ~0.1% < 1% => valid."""
        fields = [
            _xbrl_field("Assets", 1000, "Assets"),
            _xbrl_field("Liabilities", 600, "Liabilities"),
            _xbrl_field("StockholdersEquity", 401, "StockholdersEquity"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=self.client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertNotIn(ReasonCode.IDENTITY_VIOLATION, state.reason_codes)

    def test_partial_fields_no_identity_check(self):
        """Only Assets provided — cannot evaluate identity, so no violation."""
        fields = [
            _xbrl_field("Assets", 1000, "Assets"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=self.client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertNotIn(ReasonCode.IDENTITY_VIOLATION, state.reason_codes)

    def test_gross_profit_identity(self):
        """Revenue=1000, COGS=600, GrossProfit=300 => should be 400 => IDENTITY_VIOLATION."""
        fields = [
            _xbrl_field("Revenue", 1000, "Revenues"),
            _xbrl_field("CostOfGoodsSold", 600, "CostOfGoodsAndServicesSold"),
            _xbrl_field("GrossProfit", 300, "GrossProfit"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=self.client)
        validator.validate(result, state)

        self.assertFalse(state.is_valid)
        self.assertIn(ReasonCode.IDENTITY_VIOLATION, state.reason_codes)
        self.assertIn("identity_violations", state.details)
        self.assertGreater(len(state.details["identity_violations"]), 0)


# ---------------------------------------------------------------------------
# Plausibility tests
# ---------------------------------------------------------------------------

class TestPlausibility(unittest.TestCase):
    """Historical plausibility checks using mean ± 3 std deviations."""

    def test_plausibility_out_of_range(self):
        """historical=[100,105,102,98,103], current=500 => >3σ => OUT_OF_RANGE."""
        historical = [100, 105, 102, 98, 103]
        client = _make_mock_client(historical=historical)

        fields = [
            _xbrl_field("NetIncomeLoss", 500, "NetIncomeLoss"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertFalse(state.is_valid)
        self.assertIn(ReasonCode.OUT_OF_RANGE, state.reason_codes)
        self.assertIn("plausibility_violations", state.details)
        self.assertGreater(len(state.details["plausibility_violations"]), 0)

    def test_plausibility_within_range(self):
        """historical=[100,105,102,98,103], current=101 => within 3σ => valid."""
        historical = [100, 105, 102, 98, 103]
        client = _make_mock_client(historical=historical)

        fields = [
            _xbrl_field("NetIncomeLoss", 101, "NetIncomeLoss"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertNotIn(ReasonCode.OUT_OF_RANGE, state.reason_codes)

    def test_plausibility_insufficient_history(self):
        """Only 2 historical values — check requires ≥3, so no violation."""
        historical = [100, 105]
        client = _make_mock_client(historical=historical)

        fields = [
            _xbrl_field("NetIncomeLoss", 999999, "NetIncomeLoss"),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertNotIn(ReasonCode.OUT_OF_RANGE, state.reason_codes)


# ---------------------------------------------------------------------------
# Referential integrity tests
# ---------------------------------------------------------------------------

class TestReferentialIntegrity(unittest.TestCase):
    """Fuzzy name-match between extracted company name and EDGAR company name."""

    def test_referential_mismatch(self):
        """Extracted 'Wrong Corp' vs EDGAR 'Apple Inc' => REFERENTIAL violation."""
        client = _make_mock_client(company_name="Apple Inc")

        fields = [
            ExtractedField(
                name="EntityRegistrantName",
                value="Wrong Corp",
                provenance=Provenance.NARRATIVE_LLM,
            ),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertFalse(state.is_valid)
        self.assertIn(ReasonCode.REFERENTIAL, state.reason_codes)

    def test_referential_match(self):
        """Extracted 'apple inc' vs EDGAR 'Apple Inc' => fuzzy match => no violation."""
        client = _make_mock_client(company_name="Apple Inc")

        fields = [
            ExtractedField(
                name="EntityRegistrantName",
                value="apple inc",
                provenance=Provenance.NARRATIVE_LLM,
            ),
        ]
        result = _make_result(fields)
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertNotIn(ReasonCode.REFERENTIAL, state.reason_codes)


# ---------------------------------------------------------------------------
# Edge-case / smoke tests
# ---------------------------------------------------------------------------

class TestNoFields(unittest.TestCase):
    """Empty field list should produce no violations."""

    def test_no_fields_no_violations(self):
        client = _make_mock_client()
        result = _make_result([])
        state = ValidationResult(is_valid=True)

        validator = SemanticValidator(client=client)
        validator.validate(result, state)

        self.assertTrue(state.is_valid)
        self.assertEqual(state.reason_codes, [])


if __name__ == "__main__":
    unittest.main()
