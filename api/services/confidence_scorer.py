"""
Confidence scorer for the SEC Filing Eval & HITL pipeline.

Computes per-field and record-level confidence from provenance base scores.
LLM self-reported confidence is never used (REQ-CR-01).
"""
from api.models.eval_types import ExtractionResult, ExtractedField, Provenance

# Provenance base scores (REQ-CR-01)
PROVENANCE_BASE_SCORES: dict[Provenance, float] = {
    Provenance.XBRL: 0.98,
    Provenance.STRUCTURED_TABLE: 0.85,
    Provenance.NARRATIVE_LLM: 0.55,
}


def score_field(f: ExtractedField) -> float:
    """Return the base confidence score for a single extracted field.

    Raises ValueError on an unknown Provenance variant so schema evolution
    fails fast rather than silently crashing with a KeyError.
    """
    score = PROVENANCE_BASE_SCORES.get(f.provenance)
    if score is None:
        raise ValueError(
            f"Unknown provenance variant: {f.provenance!r}. "
            "Add it to PROVENANCE_BASE_SCORES with an appropriate base score."
        )
    return score


def score_record(result: ExtractionResult) -> float:
    """Return record-level confidence as the minimum of all per-field scores (REQ-CR-02).

    Returns 0.0 if the record has no fields.
    """
    if not result.fields:
        return 0.0
    return min(score_field(f) for f in result.fields)
