"""
tests/test_confidence_scorer.py

Unit tests for confidence_scorer (api/services/confidence_scorer.py).
Covers per-field scoring and record-level minimum aggregation.

Run with: python -m pytest tests/test_confidence_scorer.py -v
"""
import unittest

from api.models.eval_types import ExtractionResult, ExtractedField, Provenance
from api.services.confidence_scorer import (
    PROVENANCE_BASE_SCORES,
    score_field,
    score_record,
)


def _field(provenance: Provenance, name: str = "field") -> ExtractedField:
    return ExtractedField(name=name, value=100.0, provenance=provenance)


def _result(fields: list[ExtractedField]) -> ExtractionResult:
    return ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000064",
        form_type="10-K",
        period="2023-09-30",
        fields=fields,
    )


class TestScoreField(unittest.TestCase):
    """Per-field provenance base scores."""

    def test_xbrl_score(self):
        self.assertAlmostEqual(score_field(_field(Provenance.XBRL)), 0.98)

    def test_structured_table_score(self):
        self.assertAlmostEqual(score_field(_field(Provenance.STRUCTURED_TABLE)), 0.85)

    def test_narrative_llm_score(self):
        self.assertAlmostEqual(score_field(_field(Provenance.NARRATIVE_LLM)), 0.55)

    def test_base_scores_dict_matches_functions(self):
        for prov in Provenance:
            self.assertAlmostEqual(
                score_field(_field(prov)), PROVENANCE_BASE_SCORES[prov]
            )


class TestScoreRecord(unittest.TestCase):
    """Record-level confidence = minimum of all field scores."""

    def test_empty_fields_returns_zero(self):
        self.assertAlmostEqual(score_record(_result([])), 0.0)

    def test_single_xbrl_field(self):
        self.assertAlmostEqual(score_record(_result([_field(Provenance.XBRL)])), 0.98)

    def test_min_is_narrative_llm(self):
        fields = [
            _field(Provenance.XBRL),
            _field(Provenance.STRUCTURED_TABLE),
            _field(Provenance.NARRATIVE_LLM),
        ]
        self.assertAlmostEqual(score_record(_result(fields)), 0.55)

    def test_all_xbrl_returns_xbrl_score(self):
        fields = [_field(Provenance.XBRL) for _ in range(5)]
        self.assertAlmostEqual(score_record(_result(fields)), 0.98)

    def test_mixed_xbrl_and_table(self):
        fields = [
            _field(Provenance.XBRL),
            _field(Provenance.STRUCTURED_TABLE),
        ]
        self.assertAlmostEqual(score_record(_result(fields)), 0.85)


if __name__ == "__main__":
    unittest.main()
