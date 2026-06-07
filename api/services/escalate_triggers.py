"""
Always-escalate trigger predicates (REQ-CR-05, REQ-CR-06).

Each predicate is a pure function: (ExtractionResult, ValidationResult) -> Optional[str].
Returns the trigger name when fired, None otherwise.

The eight mandated triggers (CONSTRAINT-004):
  1. BALANCE_SHEET_IDENTITY  — balance sheet identity failure
  2. AMENDED_RESTATEMENT     — amended filing or restatement signal
  3. 8K_CRITICAL_ITEM        — 8-K items 1.03, 4.02, or 4.01
  4. GOING_CONCERN           — going-concern language in narrative fields
  5. XBRL_MISMATCH           — XBRL fact does not match extracted value
  6. UNRECOGNIZED_CONCEPT    — unrecognized us-gaap concept or new taxonomy season
  7. OUT_OF_HISTORICAL_RANGE — value outside historical range
  8. DOWNSTREAM_ACTION_FIELD — extraction feeding user-facing figure or downstream action
"""
from typing import Optional

from api.models.eval_types import ExtractionResult, ExtractedField, ValidationResult, ReasonCode, Provenance

# 8-K item codes that always escalate (SEC Form 8-K item taxonomy — regulatory constant,
# not an operational threshold; update only if SEC amends the 8-K item taxonomy)
_8K_CRITICAL_ITEMS = {"1.03", "4.01", "4.02"}

# Pre-computed search strings for source_span scanning (MIMO perf review — avoids
# repeated f-string construction inside inner loop)
_8K_CRITICAL_SPANS = frozenset(f"item {code}" for code in _8K_CRITICAL_ITEMS)

# Phrases that indicate going-concern doubt (case-insensitive substring match)
_GOING_CONCERN_PHRASES = (
    "going concern",
    "substantial doubt",
    "ability to continue as a going concern",
)

# source_span prefix that adapter layer sets on fields feeding downstream actions.
# SECURITY NOTE: this prefix MUST be set only by adapter code, never copied verbatim
# from raw filing text (Gemini security review finding 9).
_DOWNSTREAM_MARKER = "DOWNSTREAM:"

# Maximum narrative field length inspected for keyword checks.
# Guards against megabyte-scale narrative values causing unbounded allocations
# across multiple predicates (Gemini security review finding 6).
_MAX_NARRATIVE_LEN = 10_000


def _narrative_text(f: ExtractedField) -> str:
    """Return a length-capped, lowercased string from a field value."""
    return str(f.value)[:_MAX_NARRATIVE_LEN].lower()


def check_balance_sheet_identity_failure(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    if ReasonCode.IDENTITY_VIOLATION in vs.reason_codes:
        return "BALANCE_SHEET_IDENTITY"
    return None


def check_amended_or_restatement(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    # Form type suffix "/A" signals an amendment (e.g. 10-K/A, 10-Q/A)
    if result.form_type.upper().endswith("/A"):
        return "AMENDED_RESTATEMENT"
    # Narrative field containing restatement language
    for f in result.fields:
        if f.provenance == Provenance.NARRATIVE_LLM and f.value is not None:
            text = _narrative_text(f)
            if "restatement" in text or "restated" in text:
                return "AMENDED_RESTATEMENT"
    return None


def check_8k_critical_items(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    if result.form_type.upper() != "8-K":
        return None
    for f in result.fields:
        if f.name in ("ItemNumber", "item_number") and str(f.value) in _8K_CRITICAL_ITEMS:
            return "8K_CRITICAL_ITEM"
        # Also catch item numbers embedded in source_span hints.
        # Hoist .lower() outside the inner loop (MIMO perf review finding 2b/8).
        if f.source_span is not None:
            span_lower = f.source_span.lower()
            if any(span in span_lower for span in _8K_CRITICAL_SPANS):
                return "8K_CRITICAL_ITEM"
    return None


def check_going_concern(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    for f in result.fields:
        if f.provenance == Provenance.NARRATIVE_LLM and f.value is not None:
            text = _narrative_text(f)
            if any(phrase in text for phrase in _GOING_CONCERN_PHRASES):
                return "GOING_CONCERN"
    return None


def check_xbrl_mismatch(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    if ReasonCode.XBRL_MISMATCH in vs.reason_codes:
        return "XBRL_MISMATCH"
    return None


def check_unrecognized_concept(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    if ReasonCode.UNKNOWN_CONCEPT in vs.reason_codes:
        return "UNRECOGNIZED_CONCEPT"
    return None


def check_out_of_historical_range(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    if ReasonCode.OUT_OF_RANGE in vs.reason_codes:
        return "OUT_OF_HISTORICAL_RANGE"
    return None


def check_downstream_action_field(
    result: ExtractionResult, vs: ValidationResult
) -> Optional[str]:
    for f in result.fields:
        if f.source_span is not None and f.source_span.startswith(_DOWNSTREAM_MARKER):
            return "DOWNSTREAM_ACTION_FIELD"
    return None


# Ordered registry — all eight triggers
_ALL_TRIGGERS = [
    check_balance_sheet_identity_failure,
    check_amended_or_restatement,
    check_8k_critical_items,
    check_going_concern,
    check_xbrl_mismatch,
    check_unrecognized_concept,
    check_out_of_historical_range,
    check_downstream_action_field,
]


def evaluate_triggers(
    result: ExtractionResult, vs: ValidationResult
) -> list[str]:
    """Run all eight always-escalate predicates and return the list of fired trigger names."""
    fired = []
    for predicate in _ALL_TRIGGERS:
        name = predicate(result, vs)
        if name is not None:
            fired.append(name)
    return fired
