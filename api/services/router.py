"""
Confidence-based router for the SEC Filing Eval & HITL pipeline.

Produces a Decision for each ExtractionResult:
  1. Evaluate all always-escalate triggers — any firing overrides routing.
  2. Compute record-level confidence from provenance scores.
  3. Map confidence to AUTO / SAMPLED_REVIEW / ESCALATE using configurable thresholds.

Routing thresholds must not be hard-coded (CONSTRAINT-003, REQ-CR-04).
Defaults are Phase 5 placeholders; real values come from Phase 6 calibration.
"""
from api.config import Config
from api.models.eval_types import Decision, ExtractionResult, Route, ValidationResult
from api.services.confidence_scorer import score_record
from api.services.escalate_triggers import evaluate_triggers


class ConfidenceRouter:
    """Routes an ExtractionResult to a Decision.

    Thresholds are read from Config at construction time so tests can inject
    custom values without monkey-patching global state.
    """

    def __init__(
        self,
        high_threshold: float | None = None,
        low_threshold: float | None = None,
    ) -> None:
        self.high_threshold = high_threshold if high_threshold is not None else Config.ROUTING_HIGH_THRESHOLD
        self.low_threshold = low_threshold if low_threshold is not None else Config.ROUTING_LOW_THRESHOLD
        if self.low_threshold >= self.high_threshold:
            raise ValueError(
                f"ROUTING_LOW_THRESHOLD ({self.low_threshold}) must be strictly less than "
                f"ROUTING_HIGH_THRESHOLD ({self.high_threshold})."
            )

    def route(self, result: ExtractionResult, vs: ValidationResult) -> Decision:
        """Produce a routing Decision for the given extraction result and validation state."""
        triggers = evaluate_triggers(result, vs)
        confidence = score_record(result)

        if triggers:
            return Decision(
                route=Route.ESCALATE,
                confidence=confidence,
                validation=vs,
                triggers_fired=triggers,
            )

        if confidence >= self.high_threshold:
            route = Route.AUTO
        elif confidence >= self.low_threshold:
            route = Route.SAMPLED_REVIEW
        else:
            route = Route.ESCALATE

        return Decision(
            route=route,
            confidence=confidence,
            validation=vs,
            triggers_fired=[],
        )
