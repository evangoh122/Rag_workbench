"""
tests/test_eval_types.py

Round-trip serialisation and provenance enforcement tests for eval_types.py.
Run with: python -m pytest tests/test_eval_types.py -v
      or:  python -m unittest tests.test_eval_types
"""
import dataclasses
import unittest

from api.models.eval_types import (
    Decision,
    ExtractedField,
    ExtractionResult,
    Provenance,
    ReasonCode,
    Route,
    ValidationResult,
)


class TestProvenanceEnum(unittest.TestCase):
    def test_provenance_values(self):
        self.assertEqual(Provenance.XBRL.value, "xbrl")
        self.assertEqual(Provenance.STRUCTURED_TABLE.value, "table")
        self.assertEqual(Provenance.NARRATIVE_LLM.value, "narrative")

    def test_provenance_is_str_enum(self):
        self.assertIsInstance(Provenance.XBRL, str)


class TestReasonCodeEnum(unittest.TestCase):
    def test_reason_code_values(self):
        self.assertEqual(ReasonCode.OK.value, "ok")
        self.assertEqual(ReasonCode.XBRL_MISMATCH.value, "xbrl_mismatch")
        self.assertEqual(ReasonCode.IDENTITY_VIOLATION.value, "identity_violation")

    def test_reason_codes_are_str_enum(self):
        self.assertIsInstance(ReasonCode.XBRL_MISMATCH, str)


class TestRouteEnum(unittest.TestCase):
    def test_route_values(self):
        self.assertEqual(Route.AUTO.value, "auto")
        self.assertEqual(Route.SAMPLED_REVIEW.value, "sampled_review")
        self.assertEqual(Route.ESCALATE.value, "escalate")

    def test_route_is_str_enum(self):
        self.assertIsInstance(Route.ESCALATE, str)


class TestExtractedField(unittest.TestCase):
    def test_requires_provenance(self):
        """ExtractedField must not be constructable without a provenance tag."""
        with self.assertRaises(TypeError):
            # Missing provenance positional arg
            ExtractedField(name="Revenue", value=1_000_000)  # type: ignore[call-arg]

    def test_optional_defaults(self):
        f = ExtractedField(name="Revenue", value=1_000_000, provenance=Provenance.XBRL)
        self.assertIsNone(f.concept)
        self.assertIsNone(f.source_span)

    def test_concept_and_span_set(self):
        f = ExtractedField(
            name="Revenue",
            value=1_000_000,
            provenance=Provenance.XBRL,
            concept="us-gaap/Revenues",
            source_span="span[2]",
        )
        self.assertEqual(f.concept, "us-gaap/Revenues")
        self.assertEqual(f.source_span, "span[2]")


class TestExtractionResultRoundTrip(unittest.TestCase):
    def _make_result(self) -> ExtractionResult:
        return ExtractionResult(
            cik="0000320193",
            accession="0000320193-23-000064",
            form_type="10-K",
            period="2023-09-30",
            fields=[
                ExtractedField(
                    name="Revenue",
                    value=383_285_000_000,
                    provenance=Provenance.XBRL,
                    concept="us-gaap/Revenues",
                ),
                ExtractedField(
                    name="NetIncomeLoss",
                    value=96_995_000_000,
                    provenance=Provenance.STRUCTURED_TABLE,
                ),
            ],
        )

    def test_round_trip_scalars(self):
        original = self._make_result()
        as_dict = dataclasses.asdict(original)

        # Reconstruct — fields list must be rebuilt manually because
        # dataclasses.asdict converts nested dataclasses to dicts too.
        fields = [
            ExtractedField(
                name=f["name"],
                value=f["value"],
                provenance=Provenance(f["provenance"]),
                concept=f.get("concept"),
                source_span=f.get("source_span"),
            )
            for f in as_dict["fields"]
        ]
        reconstructed = ExtractionResult(
            cik=as_dict["cik"],
            accession=as_dict["accession"],
            form_type=as_dict["form_type"],
            period=as_dict["period"],
            fields=fields,
        )

        self.assertEqual(reconstructed.cik, original.cik)
        self.assertEqual(reconstructed.accession, original.accession)
        self.assertEqual(reconstructed.form_type, original.form_type)
        self.assertEqual(reconstructed.period, original.period)
        self.assertEqual(len(reconstructed.fields), len(original.fields))
        self.assertEqual(reconstructed.fields[0].provenance, original.fields[0].provenance)

    def test_all_fields_tagged(self):
        result = self._make_result()
        for f in result.fields:
            self.assertIsInstance(
                f.provenance, Provenance,
                msg=f"Field '{f.name}' is missing a valid Provenance tag",
            )


class TestValidationResultDefaults(unittest.TestCase):
    def test_defaults(self):
        vr = ValidationResult(is_valid=True)
        self.assertEqual(vr.reason_codes, [])
        self.assertEqual(vr.details, {})

    def test_mutable_defaults_are_independent(self):
        """Each instance must have its own list/dict, not a shared reference."""
        a = ValidationResult(is_valid=True)
        b = ValidationResult(is_valid=False)
        a.reason_codes.append(ReasonCode.MISSING_FIELD)
        self.assertEqual(b.reason_codes, [])


class TestDecisionDefaults(unittest.TestCase):
    def test_triggers_fired_defaults_empty(self):
        d = Decision(
            route=Route.AUTO,
            confidence=0.99,
            validation=ValidationResult(is_valid=True),
        )
        self.assertEqual(d.triggers_fired, [])

    def test_mutable_defaults_are_independent(self):
        a = Decision(route=Route.AUTO, confidence=0.9, validation=ValidationResult(is_valid=True))
        b = Decision(route=Route.AUTO, confidence=0.8, validation=ValidationResult(is_valid=True))
        a.triggers_fired.append("balance_sheet_identity_failure")
        self.assertEqual(b.triggers_fired, [])


if __name__ == "__main__":
    unittest.main()
