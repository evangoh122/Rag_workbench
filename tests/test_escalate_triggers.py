"""
tests/test_escalate_triggers.py

Unit tests for all eight always-escalate trigger predicates
(api/services/escalate_triggers.py).

Run with: python -m pytest tests/test_escalate_triggers.py -v
"""
import unittest

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
    ReasonCode,
    ValidationResult,
)
from api.services.escalate_triggers import (
    check_balance_sheet_identity_failure,
    check_amended_or_restatement,
    check_8k_critical_items,
    check_going_concern,
    check_xbrl_mismatch,
    check_unrecognized_concept,
    check_out_of_historical_range,
    check_downstream_action_field,
    evaluate_triggers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(
    form_type: str = "10-K",
    fields: list[ExtractedField] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000064",
        form_type=form_type,
        period="2023-09-30",
        fields=fields or [],
    )


def _vs(*reason_codes: ReasonCode) -> ValidationResult:
    return ValidationResult(is_valid=not reason_codes, reason_codes=list(reason_codes))


def _narrative(value: str) -> ExtractedField:
    return ExtractedField(
        name="note", value=value, provenance=Provenance.NARRATIVE_LLM
    )


def _xbrl_field(name: str, value: float = 100.0) -> ExtractedField:
    return ExtractedField(name=name, value=value, provenance=Provenance.XBRL)


# ---------------------------------------------------------------------------
# 1. Balance sheet identity failure
# ---------------------------------------------------------------------------

class TestBalanceSheetIdentity(unittest.TestCase):
    def test_fires_on_identity_violation(self):
        result = _result()
        vs = _vs(ReasonCode.IDENTITY_VIOLATION)
        self.assertEqual(check_balance_sheet_identity_failure(result, vs), "BALANCE_SHEET_IDENTITY")

    def test_no_fire_without_violation(self):
        result = _result()
        vs = _vs()
        self.assertIsNone(check_balance_sheet_identity_failure(result, vs))


# ---------------------------------------------------------------------------
# 2. Amended / restatement
# ---------------------------------------------------------------------------

class TestAmendedRestatement(unittest.TestCase):
    def test_fires_on_form_type_amendment(self):
        self.assertEqual(
            check_amended_or_restatement(_result("10-K/A"), _vs()),
            "AMENDED_RESTATEMENT",
        )

    def test_fires_on_10q_amendment(self):
        self.assertEqual(
            check_amended_or_restatement(_result("10-Q/A"), _vs()),
            "AMENDED_RESTATEMENT",
        )

    def test_fires_on_restatement_in_narrative(self):
        result = _result(fields=[_narrative("This filing includes a restatement of prior results.")])
        self.assertEqual(check_amended_or_restatement(result, _vs()), "AMENDED_RESTATEMENT")

    def test_no_fire_on_normal_10k(self):
        self.assertIsNone(check_amended_or_restatement(_result("10-K"), _vs()))


# ---------------------------------------------------------------------------
# 3. 8-K critical items
# ---------------------------------------------------------------------------

class TestEightKCriticalItems(unittest.TestCase):
    def test_fires_on_item_1_03(self):
        field = ExtractedField(name="ItemNumber", value="1.03", provenance=Provenance.STRUCTURED_TABLE)
        result = _result("8-K", [field])
        self.assertEqual(check_8k_critical_items(result, _vs()), "8K_CRITICAL_ITEM")

    def test_fires_on_item_4_02(self):
        field = ExtractedField(name="ItemNumber", value="4.02", provenance=Provenance.STRUCTURED_TABLE)
        result = _result("8-K", [field])
        self.assertEqual(check_8k_critical_items(result, _vs()), "8K_CRITICAL_ITEM")

    def test_fires_on_source_span_hint(self):
        field = ExtractedField(
            name="note", value="...", provenance=Provenance.NARRATIVE_LLM,
            source_span="Item 4.01 — Changes in Registrant's Certifying Accountant"
        )
        result = _result("8-K", [field])
        self.assertEqual(check_8k_critical_items(result, _vs()), "8K_CRITICAL_ITEM")

    def test_no_fire_on_safe_8k_item(self):
        field = ExtractedField(name="ItemNumber", value="2.02", provenance=Provenance.STRUCTURED_TABLE)
        result = _result("8-K", [field])
        self.assertIsNone(check_8k_critical_items(result, _vs()))

    def test_no_fire_on_non_8k(self):
        field = ExtractedField(name="ItemNumber", value="1.03", provenance=Provenance.STRUCTURED_TABLE)
        result = _result("10-K", [field])
        self.assertIsNone(check_8k_critical_items(result, _vs()))


# ---------------------------------------------------------------------------
# 4. Going concern
# ---------------------------------------------------------------------------

class TestGoingConcern(unittest.TestCase):
    def test_fires_on_going_concern_phrase(self):
        result = _result(fields=[_narrative("There is substantial doubt about our ability to continue as a going concern.")])
        self.assertEqual(check_going_concern(result, _vs()), "GOING_CONCERN")

    def test_fires_on_substantial_doubt(self):
        result = _result(fields=[_narrative("Management identified substantial doubt about the company's future.")])
        self.assertEqual(check_going_concern(result, _vs()), "GOING_CONCERN")

    def test_no_fire_on_benign_narrative(self):
        result = _result(fields=[_narrative("The company reported strong revenue growth this quarter.")])
        self.assertIsNone(check_going_concern(result, _vs()))

    def test_no_fire_on_xbrl_field(self):
        field = ExtractedField(name="note", value="going concern doubt", provenance=Provenance.XBRL)
        result = _result(fields=[field])
        self.assertIsNone(check_going_concern(result, _vs()))


# ---------------------------------------------------------------------------
# 5. XBRL mismatch
# ---------------------------------------------------------------------------

class TestXbrlMismatch(unittest.TestCase):
    def test_fires_on_xbrl_mismatch_reason_code(self):
        self.assertEqual(
            check_xbrl_mismatch(_result(), _vs(ReasonCode.XBRL_MISMATCH)),
            "XBRL_MISMATCH",
        )

    def test_no_fire_without_mismatch(self):
        self.assertIsNone(check_xbrl_mismatch(_result(), _vs()))


# ---------------------------------------------------------------------------
# 6. Unrecognized concept
# ---------------------------------------------------------------------------

class TestUnrecognizedConcept(unittest.TestCase):
    def test_fires_on_unknown_concept(self):
        self.assertEqual(
            check_unrecognized_concept(_result(), _vs(ReasonCode.UNKNOWN_CONCEPT)),
            "UNRECOGNIZED_CONCEPT",
        )

    def test_no_fire_without_unknown_concept(self):
        self.assertIsNone(check_unrecognized_concept(_result(), _vs()))


# ---------------------------------------------------------------------------
# 7. Out of historical range
# ---------------------------------------------------------------------------

class TestOutOfHistoricalRange(unittest.TestCase):
    def test_fires_on_out_of_range(self):
        self.assertEqual(
            check_out_of_historical_range(_result(), _vs(ReasonCode.OUT_OF_RANGE)),
            "OUT_OF_HISTORICAL_RANGE",
        )

    def test_no_fire_without_out_of_range(self):
        self.assertIsNone(check_out_of_historical_range(_result(), _vs()))


# ---------------------------------------------------------------------------
# 8. Downstream action field
# ---------------------------------------------------------------------------

class TestDownstreamActionField(unittest.TestCase):
    def test_fires_on_downstream_marker(self):
        field = ExtractedField(
            name="EPS", value=2.34, provenance=Provenance.XBRL,
            source_span="DOWNSTREAM:earnings-release-table"
        )
        result = _result(fields=[field])
        self.assertEqual(check_downstream_action_field(result, _vs()), "DOWNSTREAM_ACTION_FIELD")

    def test_no_fire_without_marker(self):
        result = _result(fields=[_xbrl_field("EPS", 2.34)])
        self.assertIsNone(check_downstream_action_field(result, _vs()))

    def test_no_fire_on_empty_fields(self):
        self.assertIsNone(check_downstream_action_field(_result(), _vs()))


# ---------------------------------------------------------------------------
# evaluate_triggers — integration
# ---------------------------------------------------------------------------

class TestEvaluateTriggers(unittest.TestCase):
    def test_no_triggers_on_clean_record(self):
        self.assertEqual(evaluate_triggers(_result(), _vs()), [])

    def test_single_trigger_fires(self):
        vs = _vs(ReasonCode.IDENTITY_VIOLATION)
        fired = evaluate_triggers(_result(), vs)
        self.assertIn("BALANCE_SHEET_IDENTITY", fired)

    def test_multiple_triggers_fire(self):
        vs = _vs(ReasonCode.IDENTITY_VIOLATION, ReasonCode.XBRL_MISMATCH)
        fired = evaluate_triggers(_result(), vs)
        self.assertIn("BALANCE_SHEET_IDENTITY", fired)
        self.assertIn("XBRL_MISMATCH", fired)

    def test_all_eight_triggers_registered(self):
        from api.services.escalate_triggers import _ALL_TRIGGERS
        self.assertEqual(len(_ALL_TRIGGERS), 8)


if __name__ == "__main__":
    unittest.main()
