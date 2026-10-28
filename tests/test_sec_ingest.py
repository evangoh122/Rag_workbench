"""tests/test_sec_ingest.py — end-to-end structured SEC ingestion proofs.

No network. Every test uses a tmp DuckDB database and fixture HTML; filing
discovery/model calls are mocked while parsing, extraction, continuation
resolution, reconciliation and persistence run for real.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

# tests/test_scripts.py stubs bs4 in sys.modules when collected first; restore
# the real package before this module (and its embed_edgar import) runs.
if sys.modules.get("bs4") is not None and not isinstance(sys.modules["bs4"], types.ModuleType):
    sys.modules.pop("bs4", None)

import bs4  # noqa: E402
import duckdb  # noqa: E402
import pytest  # noqa: E402

from scripts import embed_edgar  # noqa: E402
from scripts.embed_edgar import (  # noqa: E402
    parse_html_file,
    parse_prospectus_file,
    run_embed_edgar_etl,
)

_REAL_BS4 = bs4

ACCESSION = "0001628280-26-067168"
ANTH_CIK = "0002130357"


@pytest.fixture(autouse=True)
def _real_bs4(monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", _REAL_BS4)
    monkeypatch.setattr(embed_edgar, "BeautifulSoup", _REAL_BS4.BeautifulSoup)


def _sec_ingest():
    """Import the new module lazily so the old head fails behaviorally."""
    try:
        from api.services import sec_ingest
    except ModuleNotFoundError:
        pytest.fail(
            "api.services.sec_ingest is missing — structured ingestion is not wired"
        )
    return sec_ingest


def _find_exhibits(path):
    finder = getattr(embed_edgar, "_find_ixbrl_exhibits", None)
    if finder is None:
        pytest.fail("scripts.embed_edgar has no iXBRL exhibit discovery")
    return finder(path)


def _context(period_xml: str, context_id: str = "c1", dimensions: str = "") -> str:
    return (
        f'<xbrli:context id="{context_id}"><xbrli:entity>'
        "<xbrli:identifier scheme=\"http://www.sec.gov/CIK\">0002130357</xbrli:identifier>"
        f"{dimensions}</xbrli:entity>"
        f"<xbrli:period>{period_xml}</xbrli:period></xbrli:context>"
    )


def _instant(date: str = "2026-12-31", **kw) -> str:
    return _context(f"<xbrli:instant>{date}</xbrli:instant>", **kw)


def _duration(start: str, end: str, **kw) -> str:
    return _context(
        f"<xbrli:startDate>{start}</xbrli:startDate>"
        f"<xbrli:endDate>{end}</xbrli:endDate>",
        **kw,
    )


def _unit(unit_id: str = "usd", measure: str = "iso4217:USD") -> str:
    return (
        f'<xbrli:unit id="{unit_id}"><xbrli:measure>{measure}</xbrli:measure></xbrli:unit>'
    )


def _header(*parts: str) -> str:
    return "<ix:header>" + "".join(parts) + "</ix:header>"


def _write_filing(tmp_path, primary_html: str, *, form: str = "10-K",
                  ticker: str = "ANTH", accession: str = ACCESSION,
                  exhibits: dict | None = None):
    filing = tmp_path / "sec-edgar-filings" / ticker / form / accession
    filing.mkdir(parents=True)
    primary = filing / "primary-document.html"
    primary.write_text(primary_html, encoding="utf-8")
    for name, html in (exhibits or {}).items():
        (filing / name).write_text(html, encoding="utf-8")
    return primary


def _run_etl(tmp_path, db_path, primary_path, *, ticker: str = "ANTH",
             form: str = "10-K"):
    model = MagicMock()
    model.embed_documents.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    with patch.object(embed_edgar, "DB_PATH", str(db_path)), \
         patch.object(embed_edgar, "_DOWNLOAD_DIR", tmp_path / "dl"), \
         patch.object(embed_edgar, "_get_model", return_value=model), \
         patch.object(
             embed_edgar, "_fetch_filing_with_downloader",
             return_value=(str(primary_path), form),
         ):
        return run_embed_edgar_etl(tickers=[ticker], batch_size=10)


def _filler() -> str:
    return "<p>" + ("Acme designs compute hardware for enterprise customers. " * 12) + "</p>"


def _inline_revenue_html() -> str:
    return (
        "<html><body>"
        + _header(_duration("2026-01-01", "2026-12-31"), _unit())
        + "<table><tr><th>Item</th><th>Year 2026</th></tr>"
        "<tr><td>Revenue</td><td>"
        '<ix:nonFraction name="us-gaap:Revenues" contextRef="c1" unitRef="usd" '
        'scale="0" decimals="0">12,345</ix:nonFraction>'
        "</td></tr></table>"
        + _filler()
        + "</body></html>"
    )


# --- 1. inline-value survival through the real parsers + entrypoint --------


def test_inline_values_survive_parsers_and_real_etl(tmp_path):
    primary = _write_filing(tmp_path, _inline_revenue_html())

    html_text, _ = parse_html_file(str(primary))
    assert "Revenue" in html_text and "12,345" in html_text

    prospectus_text, _ = parse_prospectus_file(str(primary))
    assert "Revenue" in prospectus_text and "12,345" in prospectus_text

    db_path = tmp_path / "inline.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT concept, raw_text, value, source FROM sec_financial_facts "
            "WHERE ticker = 'ANTH'"
        ).fetchall()
    assert any(r[0] == "us-gaap:Revenues" and r[1] == "12,345" for r in rows)
    assert any(r[2] == "12345" for r in rows)


# --- 2. fee-only XBRL end-to-end: UNAVAILABLE + no financial fee -----------


def _fee_only_primary() -> str:
    return (
        "<html><body>"
        "<table><tr><th>Item</th><th>2026</th></tr>"
        "<tr><td>Revenue</td><td>1,234</td></tr>"
        "<tr><td>Net Income</td><td>500</td></tr>"
        "</table>"
        + _filler()
        + "</body></html>"
    )


def _fee_exhibit() -> str:
    return (
        "<html><body>"
        + _header(_instant("2026-03-31"), _unit())
        + '<p><ix:nonFraction name="ffd:FilingFee" contextRef="c1" unitRef="usd" '
        'decimals="0">15,000</ix:nonFraction></p>'
        "</body></html>"
    )


def test_fee_only_filing_is_unavailable_and_never_a_financial(tmp_path):
    primary = _write_filing(
        tmp_path, _fee_only_primary(), exhibits={"exfilingfees.htm": _fee_exhibit()},
    )
    exhibits = _find_exhibits(str(primary))
    assert [name for _html, name in exhibits] == ["exfilingfees.htm"]

    db_path = tmp_path / "fee.duckdb"
    _run_etl(tmp_path, db_path, primary)

    def _snapshot():
        with duckdb.connect(str(db_path)) as conn:
            recon = conn.execute(
                "SELECT concept, status, table_value, xbrl_value "
                "FROM sec_reconciliation WHERE ticker = 'ANTH' AND accession = ? "
                "ORDER BY concept",
                [ACCESSION],
            ).fetchall()
            financial = conn.execute(
                "SELECT concept, source, origin_doc FROM sec_financial_facts "
                "WHERE ticker = 'ANTH'"
            ).fetchall()
            fees = conn.execute(
                "SELECT concept, origin_doc FROM sec_fee_facts WHERE ticker = 'ANTH'"
            ).fetchall()
        return recon, financial, fees

    recon, financial, fees = _snapshot()
    assert recon, "statement table keys must be reconciled explicitly"
    assert {r[0] for r in recon} == {"Revenue", "Net Income"}
    assert {r[1] for r in recon} == {"UNAVAILABLE"}
    assert all(r[2] is not None and r[3] is None for r in recon)

    assert ("ffd:FilingFee", "exfilingfees.htm") in fees
    assert all(not str(r[0]).lower().startswith("ffd") for r in financial)
    assert all("filingfee" not in str(r[0]).lower().replace(":", "") for r in financial)
    assert ("Revenue", "table", "primary-document.html") in financial

    assert _run_etl(tmp_path, db_path, primary) >= 0
    assert _snapshot() == (recon, financial, fees)


# --- 3. real financial XBRL: MATCH, negative sign, MISMATCH delta ----------


def _financial_html() -> str:
    return (
        "<html><body>"
        + _header(
            _duration("2026-01-01", "2026-12-31", context_id="c2026"),
            _duration("2025-01-01", "2025-12-31", context_id="c2025"),
            _unit(),
        )
        + "<table><caption>Consolidated Statements (In thousands)</caption>"
        "<tr><th>Item</th><th>Year 2026</th><th>Year 2025</th></tr>"
        "<tr><td>Revenue</td>"
        '<td><ix:nonFraction name="us-gaap:Revenues" contextRef="c2026" '
        'unitRef="usd" scale="3" decimals="-3">1,234</ix:nonFraction></td>'
        '<td>(<ix:nonFraction name="us-gaap:Revenues" contextRef="c2025" '
        'unitRef="usd" scale="3" sign="-" decimals="-3">1,234</ix:nonFraction>)</td>'
        "</tr>"
        "<tr><td>Net Income</td><td>500</td><td></td></tr>"
        "</table>"
        '<div style="display:none"><ix:nonFraction name="us-gaap:NetIncomeLoss" '
        'contextRef="c2026" unitRef="usd" scale="3" decimals="-3">600</ix:nonFraction></div>'
        + _filler()
        + "</body></html>"
    )


def test_financial_xbrl_matches_and_mismatch_carries_values(tmp_path):
    primary = _write_filing(tmp_path, _financial_html())
    db_path = tmp_path / "financial.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT concept, duration, status, table_value, xbrl_value, delta "
            "FROM sec_reconciliation WHERE ticker = 'ANTH' AND accession = ?",
            [ACCESSION],
        ).fetchall()
    by_key = {(r[0], r[1]): r for r in rows}

    rev_2026 = by_key[("us-gaap:Revenues", "2026-01-01..2026-12-31")]
    assert rev_2026[2] == "MATCH"
    assert rev_2026[3] == rev_2026[4] == "1234000"

    rev_2025 = by_key[("us-gaap:Revenues", "2025-01-01..2025-12-31")]
    assert rev_2025[2] == "MATCH"
    assert rev_2025[3] == rev_2025[4] == "-1234000"

    mismatch = by_key[("us-gaap:NetIncomeLoss", "2026-01-01..2026-12-31")]
    assert mismatch[2] == "MISMATCH"
    assert mismatch[3] == "500000" and mismatch[4] == "600000"
    assert mismatch[5] == "100000"


# --- 4. continuation chains from real HTML ---------------------------------


def test_continuation_chain_from_html_is_fully_resolved():
    from api.services.sec_reconcile import extract_ix_facts

    html = (
        "<html><body>"
        '<p><ix:nonNumeric id="f1" name="dei:EntityRegistrantName" '
        'continuedAt="c1">Acme </ix:nonNumeric></p>'
        '<ix:continuation id="c1" continuedAt="c2">Corporation </ix:continuation>'
        '<ix:continuation id="c2">Holdings</ix:continuation>'
        "</body></html>"
    )
    facts = extract_ix_facts(html, document_id="doc1")
    assert facts[0].text == "Acme Corporation Holdings"

    # Cycle terminates instead of looping forever.
    cycle = (
        "<html><body>"
        '<p><ix:nonNumeric id="f1" continuedAt="a">Acme </ix:nonNumeric></p>'
        '<ix:continuation id="a" continuedAt="b">Corporation </ix:continuation>'
        '<ix:continuation id="b" continuedAt="a">Holdings</ix:continuation>'
        "</body></html>"
    )
    assert extract_ix_facts(cycle, document_id="doc1")[0].text == (
        "Acme Corporation Holdings"
    )

    # Missing target stops cleanly.
    missing = (
        "<html><body>"
        '<p><ix:nonNumeric id="f1" continuedAt="nope">Acme </ix:nonNumeric></p>'
        "</body></html>"
    )
    assert extract_ix_facts(missing, document_id="doc1")[0].text == "Acme"

    # ix:exclude inside a continuation is never included.
    excluded = (
        "<html><body>"
        '<p><ix:nonNumeric id="f1" continuedAt="c1">Acme </ix:nonNumeric></p>'
        '<ix:continuation id="c1">Corporation '
        "<ix:exclude>SECRET</ix:exclude>Holdings</ix:continuation>"
        "</body></html>"
    )
    text = extract_ix_facts(excluded, document_id="doc1")[0].text
    assert text == "Acme Corporation Holdings"
    assert "SECRET" not in text


def test_numeric_continuation_reaches_persistence(tmp_path):
    sec_ingest = _sec_ingest()
    html = (
        "<html><body>"
        + _header(_instant(), _unit())
        + '<p><ix:nonFraction id="f1" name="us-gaap:Assets" contextRef="c1" '
        'unitRef="usd" continuedAt="c1next">12</ix:nonFraction></p>'
        '<ix:continuation id="c1next">345</ix:continuation>'
        "</body></html>"
    )
    conn = duckdb.connect(str(tmp_path / "cont.duckdb"))
    try:
        sec_ingest.ingest_filing_structured(
            conn, ticker="ANTH", cik=ANTH_CIK, accession=ACCESSION,
            form_type="10-K", primary_html=html,
            primary_origin_doc="primary-document.html",
        )
        rows = conn.execute(
            "SELECT value, raw_text, fact_id FROM sec_financial_facts "
            "WHERE concept = 'us-gaap:Assets'"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("12345", "12345", "primary-document.html#f1")]


# --- 5. conflicting duplicates -> AMBIGUOUS end-to-end --------------------


def _duplicate_facts_html(values: list[str]) -> str:
    facts = "".join(
        '<p><ix:nonFraction id="f%d" name="us-gaap:Assets" contextRef="c1" '
        'unitRef="usd" decimals="0">%s</ix:nonFraction></p>' % (i, value)
        for i, value in enumerate(values)
    )
    return "<html><body>" + _header(_instant(), _unit()) + facts + "</body></html>"


def test_ambiguous_duplicate_xbrl_facts_both_orders(tmp_path):
    sec_ingest = _sec_ingest()

    def _reconcile(values):
        conn = duckdb.connect(str(tmp_path / ("amb-%s.duckdb" % "".join(values))))
        try:
            sec_ingest.ingest_filing_structured(
                conn, ticker="ANTH", cik=ANTH_CIK, accession=ACCESSION,
                form_type="10-K", primary_html=_duplicate_facts_html(values),
                primary_origin_doc="primary-document.html",
            )
            return conn.execute(
                "SELECT status, table_value, xbrl_value, xbrl_candidates "
                "FROM sec_reconciliation WHERE concept = 'us-gaap:Assets'"
            ).fetchone()
        finally:
            conn.close()

    first = _reconcile(["100", "200"])
    second = _reconcile(["200", "100"])
    assert first == second
    assert first[0] == "AMBIGUOUS"
    assert first[1] is None and first[2] is None
    assert first[3] == "100;200"


# --- 6. full provenance from an exhibit ------------------------------------


def test_exhibit_fact_provenance_is_persisted(tmp_path):
    sec_ingest = _sec_ingest()
    exhibit = (
        "<html><body>"
        + _header(
            _instant(dimensions=(
                '<xbrli:segment><xbrli:explicitMember dimension="us-gaap:ProductOrServiceAxis">'
                "us-gaap:WidgetsMember</xbrli:explicitMember></xbrli:segment>"
            )),
            _unit("u1"),
        )
        + '<ix:hidden><ix:nonFraction id="f1" name="us-gaap:Revenues" '
        'contextRef="c1" unitRef="u1" scale="3" sign="-" decimals="-3" '
        'format="ixt:num-dot-decimal">1,000</ix:nonFraction></ix:hidden>'
        "</body></html>"
    )
    primary = "<html><body>" + _filler() + "</body></html>"
    conn = duckdb.connect(str(tmp_path / "prov.duckdb"))
    try:
        sec_ingest.ingest_filing_structured(
            conn, ticker="ANTH", cik=ANTH_CIK, accession=ACCESSION,
            form_type="10-K", primary_html=primary,
            exhibits=[(exhibit, "exhibit107.htm")],
            primary_origin_doc="primary-document.html",
        )
        row = conn.execute(
            "SELECT issuer, concept, unit, duration, dimensions, value, source, "
            "origin_doc, document_id, fact_id, context_ref, unit_ref, scale, sign, "
            "decimals, fmt, raw_text, hidden FROM sec_financial_facts "
            "WHERE concept = 'us-gaap:Revenues'"
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        ANTH_CIK, "us-gaap:Revenues", "USD", "2026-12-31",
        "us-gaap:ProductOrServiceAxis=us-gaap:WidgetsMember", "-1000000", "xbrl",
        "exhibit107.htm", "exhibit107.htm", "exhibit107.htm#f1", "c1", "u1",
        3, "-", "-3", "ixt:num-dot-decimal", "1,000", True,
    )
