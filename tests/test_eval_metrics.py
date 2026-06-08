"""
tests/test_eval_metrics.py

Unit tests for eval_metrics module (api/services/eval_metrics.py).
Covers:
  - ValidationMetrics dataclass (precision, recall, f1 properties)
  - RoutingMetrics dataclass (escalation_rate, auto_rate properties)
  - AgreementMetrics dataclass (agreement_rate, meets_production_bar properties)
  - compute_validation_metrics()
  - compute_routing_metrics()
  - compute_agreement_metrics()

Run with: python -m pytest tests/test_eval_metrics.py -v
      or:  python -m unittest tests.test_eval_metrics
"""
import unittest

from api.models.eval_types import ValidationResult, Decision, Route, ReasonCode
from api.services.eval_metrics import (
    ValidationMetrics,
    RoutingMetrics,
    AgreementMetrics,
    compute_validation_metrics,
    compute_routing_metrics,
    compute_agreement_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision(route: Route, is_valid: bool = True, confidence: float = 0.95) -> Decision:
    return Decision(
        route=route,
        confidence=confidence,
        validation=ValidationResult(is_valid=is_valid),
    )


def _valid_result() -> ValidationResult:
    return ValidationResult(is_valid=True)


def _invalid_result() -> ValidationResult:
    return ValidationResult(is_valid=False, reason_codes=[ReasonCode.MISSING_FIELD])


# ---------------------------------------------------------------------------
# ValidationMetrics
# ---------------------------------------------------------------------------

class TestValidationMetrics(unittest.TestCase):
    """Tests for the ValidationMetrics dataclass and its computed properties."""

    def test_validation_metrics_precision_recall(self):
        """2 TP, 1 FP, 1 TN, 1 FN => precision=2/3, recall=2/3, f1=2/3."""
        m = ValidationMetrics(
            true_positives=2,
            false_positives=1,
            true_negatives=1,
            false_negatives=1,
        )
        expected = 2 / 3
        self.assertAlmostEqual(m.precision, expected, places=9)
        self.assertAlmostEqual(m.recall, expected, places=9)
        self.assertAlmostEqual(m.f1, expected, places=9)

    def test_validation_metrics_zero_division(self):
        """All zero counts => precision, recall, f1 are all None."""
        m = ValidationMetrics(
            true_positives=0,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
        )
        self.assertIsNone(m.precision)
        self.assertIsNone(m.recall)
        self.assertIsNone(m.f1)

    def test_perfect_precision_and_recall(self):
        """5 TP, 0 FP, 5 TN, 0 FN => precision=1.0, recall=1.0, f1=1.0."""
        m = ValidationMetrics(
            true_positives=5,
            false_positives=0,
            true_negatives=5,
            false_negatives=0,
        )
        self.assertAlmostEqual(m.precision, 1.0)
        self.assertAlmostEqual(m.recall, 1.0)
        self.assertAlmostEqual(m.f1, 1.0)

    def test_zero_tp_nonzero_fp(self):
        """0 TP, 3 FP => precision=0.0, recall=None (no positives in ground truth)."""
        m = ValidationMetrics(
            true_positives=0,
            false_positives=3,
            true_negatives=2,
            false_negatives=0,
        )
        self.assertAlmostEqual(m.precision, 0.0)
        # recall = TP / (TP + FN) = 0 / (0 + 0) => None
        self.assertIsNone(m.recall)


# ---------------------------------------------------------------------------
# RoutingMetrics
# ---------------------------------------------------------------------------

class TestRoutingMetrics(unittest.TestCase):
    """Tests for the RoutingMetrics dataclass and its computed properties."""

    def test_routing_metrics_counts(self):
        """5 AUTO, 3 SAMPLED_REVIEW, 2 ESCALATE => escalation_rate=0.2, auto_rate=0.5."""
        m = RoutingMetrics(
            total=10,
            auto_count=5,
            sampled_review_count=3,
            escalate_count=2,
        )
        self.assertAlmostEqual(m.escalation_rate, 0.2)
        self.assertAlmostEqual(m.auto_rate, 0.5)

    def test_routing_metrics_empty(self):
        """Zero total decisions => escalation_rate=None, auto_rate=None."""
        m = RoutingMetrics(
            total=0,
            auto_count=0,
            sampled_review_count=0,
            escalate_count=0,
        )
        self.assertIsNone(m.escalation_rate)
        self.assertIsNone(m.auto_rate)

    def test_all_escalated(self):
        """All decisions escalated => escalation_rate=1.0, auto_rate=0.0."""
        m = RoutingMetrics(
            total=4,
            auto_count=0,
            sampled_review_count=0,
            escalate_count=4,
        )
        self.assertAlmostEqual(m.escalation_rate, 1.0)
        self.assertAlmostEqual(m.auto_rate, 0.0)


# ---------------------------------------------------------------------------
# AgreementMetrics
# ---------------------------------------------------------------------------

class TestAgreementMetrics(unittest.TestCase):
    """Tests for the AgreementMetrics dataclass and its computed properties."""

    def test_agreement_rate_above_bar(self):
        """97/100 agreed => agreement_rate=0.97, meets_production_bar=True."""
        m = AgreementMetrics(total_reviewed=100, agreed=97)
        self.assertAlmostEqual(m.agreement_rate, 0.97)
        self.assertTrue(m.meets_production_bar)

    def test_agreement_rate_below_bar(self):
        """90/100 agreed => agreement_rate=0.90, meets_production_bar=False."""
        m = AgreementMetrics(total_reviewed=100, agreed=90)
        self.assertAlmostEqual(m.agreement_rate, 0.90)
        self.assertFalse(m.meets_production_bar)

    def test_agreement_rate_exactly_at_bar(self):
        """95/100 agreed => agreement_rate=0.95, meets_production_bar=True (boundary)."""
        m = AgreementMetrics(total_reviewed=100, agreed=95)
        self.assertAlmostEqual(m.agreement_rate, 0.95)
        self.assertTrue(m.meets_production_bar)

    def test_agreement_rate_zero_reviewed(self):
        """No reviews => agreement_rate=None, meets_production_bar=False."""
        m = AgreementMetrics(total_reviewed=0, agreed=0)
        self.assertIsNone(m.agreement_rate)
        self.assertFalse(m.meets_production_bar)


# ---------------------------------------------------------------------------
# compute_validation_metrics
# ---------------------------------------------------------------------------

class TestComputeValidationMetrics(unittest.TestCase):
    """Tests for compute_validation_metrics(results: list[tuple[ValidationResult, bool]])."""

    def test_compute_validation_metrics_from_results(self):
        """
        Pairs of (ValidationResult, ground_truth_bool) where:
          - (invalid, True)  = FN  (validator said invalid, truth is valid)
          - (valid, False)   = FP  (validator said valid, truth is invalid)
          - (invalid, False) = TN  (both say invalid)
          - (valid, True)    = TP  (both say valid)
          - (valid, True)    = TP

        => TP=2, FP=1, TN=1, FN=1
        """
        results = [
            (_invalid_result(), True),   # FN
            (_valid_result(), False),    # FP
            (_invalid_result(), False),  # TN
            (_valid_result(), True),     # TP
            (_valid_result(), True),     # TP
        ]
        m = compute_validation_metrics(results)

        self.assertEqual(m.true_positives, 2)
        self.assertEqual(m.false_positives, 1)
        self.assertEqual(m.true_negatives, 1)
        self.assertEqual(m.false_negatives, 1)

    def test_compute_validation_metrics_all_correct(self):
        """All predictions match ground truth."""
        results = [
            (_valid_result(), True),
            (_valid_result(), True),
            (_invalid_result(), False),
        ]
        m = compute_validation_metrics(results)
        self.assertEqual(m.true_positives, 2)
        self.assertEqual(m.false_positives, 0)
        self.assertEqual(m.true_negatives, 1)
        self.assertEqual(m.false_negatives, 0)

    def test_compute_validation_metrics_empty(self):
        """Empty list => all zeros."""
        m = compute_validation_metrics([])
        self.assertEqual(m.true_positives, 0)
        self.assertEqual(m.false_positives, 0)
        self.assertEqual(m.true_negatives, 0)
        self.assertEqual(m.false_negatives, 0)


# ---------------------------------------------------------------------------
# compute_routing_metrics
# ---------------------------------------------------------------------------

class TestComputeRoutingMetrics(unittest.TestCase):
    """Tests for compute_routing_metrics(decisions: list[Decision])."""

    def test_routing_metrics_counts(self):
        """5 AUTO, 3 SAMPLED_REVIEW, 2 ESCALATE."""
        decisions = (
            [_decision(Route.AUTO)] * 5
            + [_decision(Route.SAMPLED_REVIEW)] * 3
            + [_decision(Route.ESCALATE)] * 2
        )
        m = compute_routing_metrics(decisions)

        self.assertEqual(m.total, 10)
        self.assertEqual(m.auto_count, 5)
        self.assertEqual(m.sampled_review_count, 3)
        self.assertEqual(m.escalate_count, 2)
        self.assertAlmostEqual(m.escalation_rate, 0.2)
        self.assertAlmostEqual(m.auto_rate, 0.5)

    def test_routing_metrics_empty(self):
        """Empty list => all zeros, rates None."""
        m = compute_routing_metrics([])
        self.assertEqual(m.total, 0)
        self.assertIsNone(m.escalation_rate)
        self.assertIsNone(m.auto_rate)

    def test_routing_metrics_all_auto(self):
        """All AUTO decisions."""
        decisions = [_decision(Route.AUTO)] * 4
        m = compute_routing_metrics(decisions)
        self.assertEqual(m.auto_count, 4)
        self.assertEqual(m.escalate_count, 0)
        self.assertAlmostEqual(m.auto_rate, 1.0)
        self.assertAlmostEqual(m.escalation_rate, 0.0)


# ---------------------------------------------------------------------------
# compute_agreement_metrics
# ---------------------------------------------------------------------------

class TestComputeAgreementMetrics(unittest.TestCase):
    """Tests for compute_agreement_metrics(reviews: list[tuple[Decision, bool]])."""

    def test_agreement_rate_above_bar(self):
        """97 out of 100 reviews agreed."""
        agreed_reviews = [(_decision(Route.AUTO), True)] * 97
        disagreed_reviews = [(_decision(Route.AUTO), False)] * 3
        reviews = agreed_reviews + disagreed_reviews

        m = compute_agreement_metrics(reviews)
        self.assertEqual(m.total_reviewed, 100)
        self.assertEqual(m.agreed, 97)
        self.assertAlmostEqual(m.agreement_rate, 0.97)
        self.assertTrue(m.meets_production_bar)

    def test_agreement_rate_below_bar(self):
        """90 out of 100 reviews agreed."""
        agreed_reviews = [(_decision(Route.AUTO), True)] * 90
        disagreed_reviews = [(_decision(Route.AUTO), False)] * 10
        reviews = agreed_reviews + disagreed_reviews

        m = compute_agreement_metrics(reviews)
        self.assertEqual(m.total_reviewed, 100)
        self.assertEqual(m.agreed, 90)
        self.assertAlmostEqual(m.agreement_rate, 0.90)
        self.assertFalse(m.meets_production_bar)

    def test_agreement_metrics_empty(self):
        """Empty review list => agreement_rate=None."""
        m = compute_agreement_metrics([])
        self.assertEqual(m.total_reviewed, 0)
        self.assertEqual(m.agreed, 0)
        self.assertIsNone(m.agreement_rate)
        self.assertFalse(m.meets_production_bar)

    def test_agreement_metrics_perfect(self):
        """All reviews agree => agreement_rate=1.0, meets bar."""
        reviews = [(_decision(Route.SAMPLED_REVIEW), True)] * 10
        m = compute_agreement_metrics(reviews)
        self.assertAlmostEqual(m.agreement_rate, 1.0)
        self.assertTrue(m.meets_production_bar)


if __name__ == "__main__":
    unittest.main()
