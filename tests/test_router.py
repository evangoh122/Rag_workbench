"""
tests/test_router.py

Unit tests for ConfidenceRouter (api/services/router.py).
Verifies trigger-override behaviour, threshold-based routing, and
that thresholds are injectable (not hard-coded).

Run with: python -m pytest tests/test_router.py -v
"""
import unittest

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
    ReasonCode,
    Route,
    ValidationResult,
)
from api.services.router import ConfidenceRouter


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


def _xbrl_fields(n: int = 1) -> list[ExtractedField]:
    return [ExtractedField(name=f"f{i}", value=float(i), provenance=Provenance.XBRL) for i in range(n)]


def _narrative_fields(n: int = 1) -> list[ExtractedField]:
    return [ExtractedField(name=f"f{i}", value=float(i), provenance=Provenance.NARRATIVE_LLM) for i in range(n)]


# ---------------------------------------------------------------------------
# Threshold-based routing (no triggers)
# ---------------------------------------------------------------------------

class TestThresholdRouting(unittest.TestCase):
    """Thresholds injected via constructor so tests are not environment-sensitive."""

    def setUp(self):
        # high=0.90, low=0.70 — explicit test values
        self.router = ConfidenceRouter(high_threshold=0.90, low_threshold=0.70)

    def test_xbrl_only_routes_auto(self):
        # XBRL score = 0.98 >= 0.90 => AUTO
        result = _result(fields=_xbrl_fields(3))
        decision = self.router.route(result, _vs())
        self.assertEqual(decision.route, Route.AUTO)
        self.assertAlmostEqual(decision.confidence, 0.98)
        self.assertEqual(decision.triggers_fired, [])

    def test_structured_table_routes_sampled_review(self):
        # STRUCTURED_TABLE score = 0.85, which is < 0.90 but >= 0.70 => SAMPLED_REVIEW
        field = ExtractedField(name="f", value=1.0, provenance=Provenance.STRUCTURED_TABLE)
        result = _result(fields=[field])
        decision = self.router.route(result, _vs())
        self.assertEqual(decision.route, Route.SAMPLED_REVIEW)
        self.assertAlmostEqual(decision.confidence, 0.85)

    def test_narrative_llm_routes_escalate(self):
        # NARRATIVE_LLM score = 0.55 < 0.70 => ESCALATE
        result = _result(fields=_narrative_fields(2))
        decision = self.router.route(result, _vs())
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertAlmostEqual(decision.confidence, 0.55)
        self.assertEqual(decision.triggers_fired, [])

    def test_empty_fields_escalate(self):
        # score_record([]) = 0.0 < any reasonable low threshold
        decision = self.router.route(_result(), _vs())
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertAlmostEqual(decision.confidence, 0.0)

    def test_mixed_fields_min_drives_routing(self):
        # Mix of XBRL (0.98) and NARRATIVE_LLM (0.55) => min=0.55 => ESCALATE
        fields = _xbrl_fields(2) + _narrative_fields(1)
        result = _result(fields=fields)
        decision = self.router.route(result, _vs())
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertAlmostEqual(decision.confidence, 0.55)

    def test_exact_high_threshold_routes_auto(self):
        # Boundary: confidence == high_threshold => AUTO
        router = ConfidenceRouter(high_threshold=0.85, low_threshold=0.65)
        field = ExtractedField(name="f", value=1.0, provenance=Provenance.STRUCTURED_TABLE)
        decision = router.route(_result(fields=[field]), _vs())
        self.assertEqual(decision.route, Route.AUTO)

    def test_exact_low_threshold_routes_sampled_review(self):
        # Boundary: confidence == low_threshold => SAMPLED_REVIEW
        router = ConfidenceRouter(high_threshold=0.90, low_threshold=0.55)
        field = ExtractedField(name="f", value=1.0, provenance=Provenance.NARRATIVE_LLM)
        decision = router.route(_result(fields=[field]), _vs())
        self.assertEqual(decision.route, Route.SAMPLED_REVIEW)


# ---------------------------------------------------------------------------
# Always-escalate trigger override
# ---------------------------------------------------------------------------

class TestTriggerOverride(unittest.TestCase):
    """Triggers force ESCALATE regardless of confidence score."""

    def setUp(self):
        self.router = ConfidenceRouter(high_threshold=0.90, low_threshold=0.70)

    def test_identity_violation_escalates_high_confidence_record(self):
        # XBRL score = 0.98 would normally route to AUTO, but trigger overrides
        result = _result(fields=_xbrl_fields(3))
        vs = _vs(ReasonCode.IDENTITY_VIOLATION)
        decision = self.router.route(result, vs)
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertIn("BALANCE_SHEET_IDENTITY", decision.triggers_fired)

    def test_xbrl_mismatch_escalates(self):
        result = _result(fields=_xbrl_fields(2))
        vs = _vs(ReasonCode.XBRL_MISMATCH)
        decision = self.router.route(result, vs)
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertIn("XBRL_MISMATCH", decision.triggers_fired)

    def test_amendment_escalates_regardless_of_confidence(self):
        result = _result(form_type="10-K/A", fields=_xbrl_fields(3))
        decision = self.router.route(result, _vs())
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertIn("AMENDED_RESTATEMENT", decision.triggers_fired)

    def test_multiple_triggers_all_appear_in_triggers_fired(self):
        result = _result(fields=_xbrl_fields(1))
        vs = _vs(ReasonCode.IDENTITY_VIOLATION, ReasonCode.XBRL_MISMATCH)
        decision = self.router.route(result, vs)
        self.assertEqual(decision.route, Route.ESCALATE)
        self.assertIn("BALANCE_SHEET_IDENTITY", decision.triggers_fired)
        self.assertIn("XBRL_MISMATCH", decision.triggers_fired)


# ---------------------------------------------------------------------------
# Threshold configurability (REQ-CR-04)
# ---------------------------------------------------------------------------

class TestThresholdsConfigurable(unittest.TestCase):
    def test_different_thresholds_produce_different_routes(self):
        # Same record, different router configs => different routing decisions
        field = ExtractedField(name="f", value=1.0, provenance=Provenance.STRUCTURED_TABLE)
        result = _result(fields=[field])  # confidence = 0.85

        router_tight = ConfidenceRouter(high_threshold=0.90, low_threshold=0.80)
        router_loose = ConfidenceRouter(high_threshold=0.80, low_threshold=0.60)

        tight_decision = router_tight.route(result, _vs())
        loose_decision = router_loose.route(result, _vs())

        # With tight thresholds: 0.85 < 0.90 but >= 0.80 => SAMPLED_REVIEW
        self.assertEqual(tight_decision.route, Route.SAMPLED_REVIEW)
        # With loose thresholds: 0.85 >= 0.80 => AUTO
        self.assertEqual(loose_decision.route, Route.AUTO)


if __name__ == "__main__":
    unittest.main()
