"""Real-bs4 tests for direct Inline XBRL parsing and its ingestion wiring."""
import sys

import bs4
import duckdb
import pytest

from api.services.ixbrl_parser import parse_ixbrl

_REAL_BS4 = bs4


@pytest.fixture(autouse=True)
def _real_bs4(monkeypatch):
    # tests/test_scripts.py replaces sys.modules["bs4"] with a MagicMock when it
    # is collected; keep the real library for this module's tests.
    monkeypatch.setitem(sys.modules, "bs4", _REAL_BS4)


FEE_EXHIBIT = """
<html><body>
<div style="display:none">
<ix:header>
  <ix:hidden>
    <xbrli:context id="rc">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0002130357</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period><xbrli:instant>2026-10-20</xbrli:instant></xbrli:period>
    </xbrli:context>
    <xbrli:context id="offrl_1">
      <xbrli:entity>
        <xbrli:identifier scheme="http://www.sec.gov/CIK">0002130357</xbrli:identifier>
      </xbrli:entity>
      <xbrli:period><xbrli:instant>2026-10-20</xbrli:instant></xbrli:period>
    </xbrli:context>
  </ix:hidden>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
</ix:header>
</div>
<p>Filing Fee Table</p>
<table>
  <tr><th>Line</th><th>Amount</th></tr>
  <tr>
    <td>Proposed Maximum Aggregate Offering Price</td>
    <td><ix:nonFraction name="ffd:MaxAggtOfferingPric" contextRef="offrl_1"
        unitRef="usd" decimals="0">$1,000,000,000.00</ix:nonFraction></td>
  </tr>
  <tr>
    <td>Total Fee</td>
    <td><ix:nonFraction name="ffd:TtlFeeAmt" contextRef="rc"
        unitRef="usd" decimals="0">$87,000.00</ix:nonFraction></td>
  </tr>
  <tr>
    <td>Fee Rate</td>
    <td><ix:nonFraction name="ffd:FeeRate" contextRef="offrl_1"
        unitRef="pure" decimals="-5">0.000087</ix:nonFraction></td>
  </tr>
  <tr>
    <td>Offset</td>
    <td><ix:nonFraction name="ffd:TtlOffsetAmt" contextRef="rc"
        unitRef="usd" decimals="0">($500.00)</ix:nonFraction></td>
  </tr>
</table>
<ix:nonNumeric name="dei:EntityRegistrantName" contextRef="rc"
  continuedAt="cont1">Anthropic,</ix:nonNumeric>
<ix:continuation id="cont1" continuedAt="cont2">PBC</ix:continuation>
<ix:continuation id="cont2">Class A</ix:continuation>
<ix:exclude>
  <ix:nonNumeric name="dei:Hidden" contextRef="rc">should-not-appear</ix:nonNumeric>
</ix:exclude>
</body></html>
"""


@pytest.fixture(scope="module")
def fee_doc():
    return parse_ixbrl(FEE_EXHIBIT)


def test_parses_all_visible_facts(fee_doc):
    names = [f.name for f in fee_doc.facts]
    assert names == [
        "ffd:MaxAggtOfferingPric",
        "ffd:TtlFeeAmt",
        "ffd:FeeRate",
        "ffd:TtlOffsetAmt",
        "dei:EntityRegistrantName",
    ]


def test_taxonomy_concept_split(fee_doc):
    fact = fee_doc.facts[0]
    assert fact.taxonomy == "ffd"
    assert fact.concept == "MaxAggtOfferingPric"


def test_numeric_values_parse_from_rendered_text(fee_doc):
    by_name = {f.name: f for f in fee_doc.facts}
    assert by_name["ffd:MaxAggtOfferingPric"].value == 1_000_000_000.0
    assert by_name["ffd:TtlFeeAmt"].value == 87_000.0
    assert by_name["ffd:FeeRate"].value == pytest.approx(0.000087)
    assert by_name["ffd:TtlOffsetAmt"].value == -500.0  # parenthesised
    assert by_name["dei:EntityRegistrantName"].value is None


def test_contexts_carry_period_and_entity(fee_doc):
    ctx = fee_doc.contexts["rc"]
    assert ctx.entity == "0002130357"
    assert ctx.instant == "2026-10-20"
    assert ctx.period == "2026-10-20"
    assert fee_doc.units["usd"].measures == ("iso4217:USD",)


def test_structure_aware_row_and_column_labels(fee_doc):
    by_name = {f.name: f for f in fee_doc.facts}
    price = by_name["ffd:MaxAggtOfferingPric"]
    assert price.row_labels == ("Proposed Maximum Aggregate Offering Price",)
    assert price.col_labels == ("Amount",)
    fee = by_name["ffd:TtlFeeAmt"]
    assert fee.row_labels == ("Total Fee",)


def test_fact_rows_group_by_row_label(fee_doc):
    rows = fee_doc.fact_rows()
    row_names = [r["row"] for r in rows]
    assert "Total Fee" in row_names
    total = next(r for r in rows if r["row"] == "Total Fee")
    assert [f.name for f in total["facts"]] == ["ffd:TtlFeeAmt"]


def test_nonnumeric_continuation_chain_resolves(fee_doc):
    fact = next(f for f in fee_doc.facts if f.name == "dei:EntityRegistrantName")
    assert fact.text_value == "Anthropic, PBC Class A"
    assert fact.continued_at == "cont1"


def test_ix_exclude_skips_hidden_facts(fee_doc):
    assert all(f.name != "dei:Hidden" for f in fee_doc.facts)


# ── Ingestion wiring ─────────────────────────────────────────────────────────

def test_parse_html_file_keeps_ix_values_and_pipe_tables(tmp_path):
    from scripts.embed_edgar import parse_html_file

    path = tmp_path / "exfilingfees-s1.htm"
    path.write_text(FEE_EXHIBIT, encoding="utf-8")
    text, raw = parse_html_file(str(path))

    assert "$87,000.00" in text            # iXBRL value preserved (was deleted before)
    assert "Anthropic," in text            # nonNumeric value preserved
    assert "should-not-appear" not in text  # ix:exclude hidden content still dropped
    assert "| Total Fee | $87,000.00 |" in text  # table serialized structurally
    assert raw == FEE_EXHIBIT


def test_store_ixbrl_facts_upserts_rows_and_replaces(tmp_path):
    from scripts.embed_edgar import _store_ixbrl_facts

    conn = duckdb.connect()
    try:
        n = _store_ixbrl_facts(
            conn,
            ticker="ANTH",
            cik="0002130357",
            accession="0001628280-26-067168",
            form_type="S-1",
            raw_html=FEE_EXHIBIT,
            extra_docs=[],
        )
        assert n == 5
        rows = conn.execute(
            "SELECT concept, value, row_labels, col_labels FROM edgar_ixbrl_facts "
            "WHERE concept = 'TtlFeeAmt'"
        ).fetchall()
        assert rows == [("TtlFeeAmt", 87000.0, "Total Fee", "Amount")]

        # Re-ingesting the same accession replaces, not duplicates.
        n2 = _store_ixbrl_facts(
            conn,
            ticker="ANTH",
            cik="0002130357",
            accession="0001628280-26-067168",
            form_type="S-1",
            raw_html=FEE_EXHIBIT,
            extra_docs=[],
        )
        assert n2 == 5
        count = conn.execute("SELECT COUNT(*) FROM edgar_ixbrl_facts").fetchone()[0]
        assert count == 5
    finally:
        conn.close()
