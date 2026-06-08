"""
Evaluation metrics for the SEC Filing Eval & HITL Framework.

Covers:
- ValidationMetrics: precision/recall/F1 for the validator against a labeled set
- RoutingMetrics: routing distribution and escalation rate
- AgreementMetrics: human-agreement rate on sampled AUTO decisions
"""
from dataclasses import dataclass, field
from typing import Optional

from api.models.eval_types import Decision, Route, ValidationResult

# Production readiness bar (CONSTRAINT-007)
PRODUCTION_AGREEMENT_BAR = 0.95


@dataclass
class ValidationMetrics:
    """Precision/recall/F1 computed against a ground-truth labeled set.

    Positive class = valid record (is_valid=True).
    TP: predicted valid, ground truth valid.
    FP: predicted valid, ground truth invalid.
    TN: predicted invalid, ground truth invalid.
    FN: predicted invalid, ground truth valid.
    """

    true_positives: int = 0   # correctly predicted valid
    false_positives: int = 0  # predicted valid, actually invalid
    true_negatives: int = 0   # correctly predicted invalid
    false_negatives: int = 0  # predicted invalid, actually valid

    @property
    def precision(self) -> Optional[float]:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else None

    @property
    def recall(self) -> Optional[float]:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


@dataclass
class RoutingMetrics:
    """Distribution across the three routing tiers."""

    total: int = 0
    auto_count: int = 0
    sampled_review_count: int = 0
    escalate_count: int = 0

    @property
    def escalation_rate(self) -> Optional[float]:
        return self.escalate_count / self.total if self.total > 0 else None

    @property
    def auto_rate(self) -> Optional[float]:
        return self.auto_count / self.total if self.total > 0 else None

    @property
    def sampled_review_rate(self) -> Optional[float]:
        return self.sampled_review_count / self.total if self.total > 0 else None


@dataclass
class AgreementMetrics:
    """Human-agreement rate for the AUTO tier (headline trust metric)."""

    total_reviewed: int = 0
    agreed: int = 0

    @property
    def agreement_rate(self) -> Optional[float]:
        return self.agreed / self.total_reviewed if self.total_reviewed > 0 else None

    @property
    def meets_production_bar(self) -> bool:
        """True when agreement_rate >= 95% — required before AUTO tier goes to production."""
        rate = self.agreement_rate
        return rate is not None and rate >= PRODUCTION_AGREEMENT_BAR


def compute_validation_metrics(
    results: list[tuple[ValidationResult, bool]],
) -> ValidationMetrics:
    """
    Args:
        results: list of (predicted_ValidationResult, ground_truth_is_valid)
                 where True means the record is genuinely valid.
    Returns:
        ValidationMetrics with TP/FP/TN/FN populated.
        Positive class = valid record (is_valid=True).
    """
    m = ValidationMetrics()
    for vr, gt_valid in results:
        predicted_valid = vr.is_valid
        if predicted_valid and gt_valid:
            m.true_positives += 1
        elif predicted_valid and not gt_valid:
            m.false_positives += 1
        elif not predicted_valid and not gt_valid:
            m.true_negatives += 1
        else:
            m.false_negatives += 1
    return m


def compute_routing_metrics(decisions: list[Decision]) -> RoutingMetrics:
    """Aggregate routing distribution from a batch of Decisions."""
    m = RoutingMetrics(total=len(decisions))
    for d in decisions:
        if d.route == Route.AUTO:
            m.auto_count += 1
        elif d.route == Route.SAMPLED_REVIEW:
            m.sampled_review_count += 1
        elif d.route == Route.ESCALATE:
            m.escalate_count += 1
    return m


def compute_agreement_metrics(
    reviews: list[tuple[Decision, bool]],
) -> AgreementMetrics:
    """
    Args:
        reviews: list of (Decision, human_agreed) for sampled AUTO decisions.
    Returns:
        AgreementMetrics with agreement_rate and production_bar status.
    """
    m = AgreementMetrics(total_reviewed=len(reviews))
    m.agreed = sum(1 for _, agreed in reviews if agreed)
    return m
