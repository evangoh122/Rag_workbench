"""
tests/test_edgar_adapter.py

Unit tests (fixture-based, no network) and an optional integration smoke test
for api/services/edgar_adapter.py.

Run unit tests only:
    python -m pytest tests/test_edgar_adapter.py -v -k "not smoke"

Run all tests (requires EDGAR_USER_AGENT env var set):
    EDGAR_USER_AGENT="Your Name your@email.com" python -m pytest tests/test_edgar_adapter.py -v
"""
import os
import unittest

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
)
from api.services.edgar_adapter import EdgarAdapterError, _xbrl_dataframe_to_fields


def _make_fixture_result(provenance: Provenance, n: int = 3) -> ExtractionResult:
    """Build a fixture ExtractionResult with n fields of the given provenance."""
    fields = [
        ExtractedField(
            name=f"Field{i}",
            value=float(i * 1_000_000),
            provenance=provenance,
            concept=f"us-gaap/Concept{i}" if provenance == Provenance.XBRL else None,
        )
        for i in range(1, n + 1)
    ]
    return ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000064",
        form_type="10-K",
        period="2023-09-30",
        fields=fields,
    )


class TestAdapterError(unittest.TestCase):
    def test_adapter_error_is_exception(self):
        err = EdgarAdapterError("test error")
        self.assertIsInstance(err, Exception)

    def test_adapter_error_message(self):
        err = EdgarAdapterError("something broke")
        self.assertEqual(str(err), "something broke")


class TestProvenanceTagging(unittest.TestCase):
    def test_xbrl_fields_tagged_xbrl(self):
        result = _make_fixture_result(Provenance.XBRL)
        for f in result.fields:
            self.assertEqual(
                f.provenance,
                Provenance.XBRL,
                msg=f"Field '{f.name}' should be XBRL-tagged but got {f.provenance}",
            )

    def test_table_fields_tagged_structured_table(self):
        result = _make_fixture_result(Provenance.STRUCTURED_TABLE)
        for f in result.fields:
            self.assertEqual(f.provenance, Provenance.STRUCTURED_TABLE)

    def test_no_untagged_fields(self):
        xbrl_result = _make_fixture_result(Provenance.XBRL, n=2)
        table_result = _make_fixture_result(Provenance.STRUCTURED_TABLE, n=2)
        combined_fields = xbrl_result.fields + table_result.fields
        mixed = ExtractionResult(
            cik="0000320193",
            accession="0000320193-23-000064",
            form_type="10-K",
            period="2023-09-30",
            fields=combined_fields,
        )
        for f in mixed.fields:
            self.assertIsNotNone(
                f.provenance,
                msg=f"Field '{f.name}' has no provenance tag",
            )
            self.assertIsInstance(f.provenance, Provenance)


class TestExtractionResultShape(unittest.TestCase):
    def test_fixture_result_shape(self):
        result = _make_fixture_result(Provenance.XBRL, n=5)
        self.assertEqual(result.cik, "0000320193")
        self.assertEqual(result.form_type, "10-K")
        self.assertGreater(len(result.fields), 0)

    def test_fields_list_is_list(self):
        result = _make_fixture_result(Provenance.XBRL)
        self.assertIsInstance(result.fields, list)


class TestXbrlDataframeToFields(unittest.TestCase):
    """Unit-test the internal XBRL DataFrame → fields converter without a network call."""

    def _make_df(self):
        import pandas as pd
        return pd.DataFrame(
            {
                "concept": ["us-gaap/Revenue", "us-gaap/Assets"],
                "value": [383_285_000_000, 352_755_000_000],
                "units": ["USD", "USD"],
            }
        )

    def test_returns_extracted_fields(self):
        fields = _xbrl_dataframe_to_fields(self._make_df())
        self.assertEqual(len(fields), 2)
        self.assertIsInstance(fields[0], ExtractedField)

    def test_provenance_is_xbrl(self):
        fields = _xbrl_dataframe_to_fields(self._make_df())
        for f in fields:
            self.assertEqual(f.provenance, Provenance.XBRL)

    def test_concept_is_set(self):
        fields = _xbrl_dataframe_to_fields(self._make_df())
        self.assertEqual(fields[0].concept, "us-gaap/Revenue")

    def test_empty_dataframe_returns_empty_list(self):
        import pandas as pd
        result = _xbrl_dataframe_to_fields(pd.DataFrame())
        self.assertEqual(result, [])

    def test_none_dataframe_returns_empty_list(self):
        result = _xbrl_dataframe_to_fields(None)  # type: ignore[arg-type]
        self.assertEqual(result, [])


@unittest.skipUnless(
    os.getenv("EDGAR_USER_AGENT"),
    "EDGAR_USER_AGENT not set — skipping live network smoke test",
)
class TestFetchFilingSmoke(unittest.TestCase):
    """Integration smoke test — requires EDGAR_USER_AGENT env var and network access."""

    CIK = "0000320193"
    ACCESSION = "0000320193-23-000064"  # Apple 10-K FY2023

    def test_fetch_real_filing_returns_extraction_result(self):
        from api.services.edgar_adapter import fetch_filing

        result = fetch_filing(self.CIK, self.ACCESSION)
        self.assertIsInstance(result, ExtractionResult)

    def test_fetch_real_filing_has_fields(self):
        from api.services.edgar_adapter import fetch_filing

        result = fetch_filing(self.CIK, self.ACCESSION)
        self.assertGreater(len(result.fields), 0, "Expected at least one extracted field")

    def test_all_fields_provenance_tagged(self):
        from api.services.edgar_adapter import fetch_filing

        result = fetch_filing(self.CIK, self.ACCESSION)
        for f in result.fields:
            self.assertIsNotNone(f.provenance, f"Field '{f.name}' has no provenance tag")
            self.assertIsInstance(f.provenance, Provenance)


if __name__ == "__main__":
    unittest.main()
