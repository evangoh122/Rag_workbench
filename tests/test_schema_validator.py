import pytest
from api.services.schema_validator import SchemaValidator
from api.models.eval_types import ExtractionResult, ExtractedField, Provenance, ReasonCode

def test_valid_extraction_result():
    result = ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000106",
        form_type="10-K",
        period="2023-09-30",
        fields=[
            ExtractedField(name="Revenue", value=383285000000, provenance=Provenance.XBRL),
            ExtractedField(name="NetIncomeLoss", value=96995000000, provenance=Provenance.XBRL),
            ExtractedField(name="Assets", value=352583000000, provenance=Provenance.XBRL),
        ]
    )
    validation = SchemaValidator.validate(result)
    assert validation.is_valid is True
    assert not validation.reason_codes

def test_missing_required_fields():
    # Missing Assets and period
    result = ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000106",
        form_type="10-K",
        period=None,
        fields=[
            ExtractedField(name="Revenue", value=383285000000, provenance=Provenance.XBRL),
            ExtractedField(name="NetIncomeLoss", value=96995000000, provenance=Provenance.XBRL),
        ]
    )
    validation = SchemaValidator.validate(result)
    assert validation.is_valid is False
    assert ReasonCode.MISSING_FIELD in validation.reason_codes

def test_invalid_formats():
    result = ExtractionResult(
        cik="320193", # Too short
        accession="000032019323000106", # Missing dashes
        form_type="10-K",
        period="2023-09-30",
        fields=[
            ExtractedField(name="Revenue", value=383285000000, provenance=Provenance.XBRL),
            ExtractedField(name="NetIncomeLoss", value=96995000000, provenance=Provenance.XBRL),
            ExtractedField(name="Assets", value=352583000000, provenance=Provenance.XBRL),
        ]
    )
    validation = SchemaValidator.validate(result)
    assert validation.is_valid is False
    assert ReasonCode.BAD_TYPE in validation.reason_codes

def test_revenue_unit_sanity_failure():
    result = ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000106",
        form_type="10-K",
        period="2023-09-30",
        fields=[
            ExtractedField(name="Revenue", value=999999, provenance=Provenance.XBRL), # < 1M
            ExtractedField(name="NetIncomeLoss", value=96995000000, provenance=Provenance.XBRL),
            ExtractedField(name="Assets", value=352583000000, provenance=Provenance.XBRL),
        ]
    )
    validation = SchemaValidator.validate(result)
    assert validation.is_valid is False
    assert ReasonCode.OUT_OF_RANGE in validation.reason_codes

def test_enrichment_manifest_generation():
    result = ExtractionResult(
        cik="0000320193",
        accession="0000320193-23-000106",
        form_type="10-K",
        period="2023-09-30",
        fields=[
            ExtractedField(name="Revenue", value=383285000000, provenance=Provenance.XBRL),
            ExtractedField(name="NetIncomeLoss", value=96995000000, provenance=Provenance.XBRL),
            ExtractedField(name="Assets", value=352583000000, provenance=Provenance.STRUCTURED_TABLE),
        ]
    )
    validation = SchemaValidator.validate(result)
    manifest = validation.details.get("enrichment_manifest", {})
    assert manifest["Revenue"] == Provenance.XBRL
    assert manifest["NetIncomeLoss"] == Provenance.XBRL
    assert "Assets" not in manifest
