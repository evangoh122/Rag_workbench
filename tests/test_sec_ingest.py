"""tests/test_sec_ingest.py — end-to-end structured SEC ingestion proofs.

No network. Every test uses a tmp DuckDB database and fixture HTML; filing
discovery/model calls are mocked while parsing, extraction, continuation
resolution, reconciliation and persistence run for real.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# tests/test_scripts.py stubs bs4 in sys.modules when collected first; restore
# the real package before this module (and its embed_edgar import) runs.
if sys.modules.get("bs4") is not None and not isinstance(sys.modules["bs4"], types.ModuleType):
    sys.modules.pop("bs4", None)

import bs4  # noqa: E402
import duckdb  # noqa: E402
import pytest  # noqa: E402

from api.services import sec_reconcile  # noqa: E402
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


def _context(period_xml: str, context_id: str = "c1", dimensions: str = "",
             issuer: str = "0002130357") -> str:
    return (
        f'<xbrli:context id="{context_id}"><xbrli:entity>'
        f"<xbrli:identifier scheme=\"http://www.sec.gov/CIK\">{issuer}</xbrli:identifier>"
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


# --- r3: Sol B1/B2/B4 regressions (identity, periods, acquisition) ---------


def _r3_html(
    *,
    header: str = "Year 2026",
    caption: str = "",
    table_rows=(("Revenue", "100"),),
    xbrl_rows=(("us-gaap:Revenues", "100"),),
    issuer: str = "1",
    measure: str = "iso4217:USD",
    period_xml: str | None = None,
    dimensions: str = "",
) -> str:
    if period_xml is None:
        period_xml = (
            "<xbrli:startDate>2026-01-01</xbrli:startDate>"
            "<xbrli:endDate>2026-12-31</xbrli:endDate>"
        )
    caption_html = f"<caption>{caption}</caption>" if caption else ""
    table = (
        f"<table>{caption_html}<tr><th>Item</th><th>{header}</th></tr>"
        + "".join(
            f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in table_rows
        )
        + "</table>"
    )
    facts = "".join(
        f'<p><ix:nonFraction name="{name}" contextRef="c1" unitRef="usd" '
        f'decimals="0">{value}</ix:nonFraction></p>'
        for name, value in xbrl_rows
    )
    return (
        "<html><body>"
        + _header(
            _context(period_xml, issuer=issuer, dimensions=dimensions),
            _unit(measure=measure),
        )
        + table
        + facts
        + _filler()
        + "</body></html>"
    )


def _r3_ingest(tmp_path, html, *, cik: str = "1", name: str = "r3.duckdb"):
    sec_ingest = _sec_ingest()
    db_path = tmp_path / name
    conn = duckdb.connect(str(db_path))
    try:
        sec_ingest.ingest_filing_structured(
            conn, ticker="ANT", cik=cik, accession="a", form_type="10-K",
            primary_html=html, primary_origin_doc="a.htm",
        )
    finally:
        conn.close()
    return db_path


def test_r3_eur_table_never_matches_usd_xbrl(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(caption="Amounts in EUR", header="Year 2026"),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        units = conn.execute(
            "SELECT source, unit, issuer FROM sec_financial_facts ORDER BY source"
        ).fetchall()

    assert {row[0] for row in statuses} == {"UNAVAILABLE"}
    assert all(row[0] != "MATCH" for row in statuses)
    assert ("table", "EUR", "1") in units
    assert ("xbrl", "USD", "1") in units


def test_r3_typed_dimension_fact_never_matches_aggregate_table(tmp_path):
    typed = (
        '<xbrli:segment><xbrldi:typedMember dimension="custom:CustomerAxis">'
        "<custom:Customer>Customer A</custom:Customer>"
        "</xbrldi:typedMember></xbrli:segment>"
    )
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(caption="Amounts in USD", dimensions=typed),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        facts = conn.execute(
            "SELECT source, dimensions FROM sec_financial_facts ORDER BY source"
        ).fetchall()

    assert {row[0] for row in statuses} == {"UNAVAILABLE"}
    assert all(row[0] != "MATCH" for row in statuses)
    by_source = dict(facts)
    assert by_source["table"] == ""
    assert "custom:CustomerAxis=Customer A" in by_source["xbrl"]


def test_r3_caller_cik_never_replaces_context_issuer(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(caption="Amounts in USD", issuer="999"),
        cik="1",
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        facts = conn.execute(
            "SELECT source, issuer FROM sec_financial_facts ORDER BY source"
        ).fetchall()

    assert {row[0] for row in statuses} == {"UNAVAILABLE"}
    assert all(row[0] != "MATCH" for row in statuses)
    by_source = dict(facts)
    assert by_source["xbrl"] == "999"
    assert by_source["table"] != "1"


def test_r3_ambiguous_concept_labels_are_not_inferred(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(
            caption="Amounts in USD",
            xbrl_rows=(("us-gaap:Revenues", "100"), ("dei:Revenues", "100")),
        ),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        table_concepts = conn.execute(
            "SELECT DISTINCT concept FROM sec_financial_facts WHERE source = 'table'"
        ).fetchall()

    assert all(row[0] != "MATCH" for row in statuses)
    assert table_concepts == [("Revenue",)]


def test_r3_year_ended_header_matches_equivalent_annual_xbrl(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(
            caption="Amounts in USD",
            header="Year ended December 31, 2026",
            period_xml=(
                "<xbrli:startDate>2026-01-01</xbrli:startDate>"
                "<xbrli:endDate>2026-12-31</xbrli:endDate>"
            ),
        ),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT status, duration, table_value, xbrl_value "
            "FROM sec_reconciliation"
        ).fetchall()

    assert rows == [("MATCH", "2026-01-01..2026-12-31", "100", "100")]


def test_r3_quarter_header_without_end_date_is_not_promoted_to_annual(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(
            caption="Amounts in USD",
            header="Three months ended 2026",
            period_xml=(
                "<xbrli:startDate>2026-01-01</xbrli:startDate>"
                "<xbrli:endDate>2026-12-31</xbrli:endDate>"
            ),
        ),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        table_fact = conn.execute(
            "SELECT duration FROM sec_financial_facts WHERE source = 'table'"
        ).fetchall()

    assert all(row[0] != "MATCH" for row in statuses)
    assert {row[0] for row in statuses} == {"UNAVAILABLE"}
    assert table_fact == [("",)]


def test_r3_quarter_header_with_end_date_resolves_true_duration(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(
            caption="Amounts in USD",
            header="Three months ended March 31, 2026",
            period_xml=(
                "<xbrli:startDate>2026-01-01</xbrli:startDate>"
                "<xbrli:endDate>2026-03-31</xbrli:endDate>"
            ),
        ),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT status, duration FROM sec_reconciliation"
        ).fetchall()

    assert rows == [("MATCH", "2026-01-01..2026-03-31")]


def _write_full_submission(
    primary: Path,
    exhibit_html: str = "",
    *,
    primary_html: str | None = None,
    exhibit_name: str = "exfilingfees.htm",
    form_type: str = "10-K",
) -> Path:
    """Write the exact sec-edgar-downloader accession artifact layout."""
    primary_content = primary.read_text(encoding="utf-8") if primary_html is None else primary_html
    blocks = [
        "<DOCUMENT>\n<TYPE>%s\n<SEQUENCE>1\n<FILENAME>%s\n<TEXT>\n%s\n</TEXT>\n</DOCUMENT>"
        % (form_type, primary.name, primary_content)
    ]
    if exhibit_html:
        blocks.append(
            "<DOCUMENT>\n<TYPE>EX-FILING FEES\n<SEQUENCE>2\n<FILENAME>%s\n"
            "<TEXT>\n%s\n</TEXT>\n</DOCUMENT>" % (exhibit_name, exhibit_html)
        )
    submission = "<SEC-DOCUMENT>\n%s\n</SEC-DOCUMENT>\n" % "\n".join(blocks)
    path = primary.parent / "full-submission.txt"
    path.write_text(submission, encoding="utf-8")
    return path


def test_r3_full_submission_fee_exhibit_is_acquired_and_persisted(tmp_path):
    primary = _write_filing(tmp_path, _fee_only_primary())
    _write_full_submission(primary, _fee_exhibit())

    exhibits = _find_exhibits(str(primary))
    assert [name for _html, name in exhibits] == ["exfilingfees.htm"]

    db_path = tmp_path / "r3-fee.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        fees = conn.execute(
            "SELECT concept, origin_doc, issuer, unit, fact_id FROM sec_fee_facts "
            "WHERE ticker = 'ANTH'"
        ).fetchall()
        financial = conn.execute(
            "SELECT concept, origin_doc FROM sec_financial_facts WHERE ticker = 'ANTH'"
        ).fetchall()
        recon = conn.execute(
            "SELECT concept, status FROM sec_reconciliation WHERE ticker = 'ANTH'"
        ).fetchall()

    assert ("ffd:FilingFee", "exfilingfees.htm", ANTH_CIK, "USD") in [
        row[:4] for row in fees
    ]
    assert all(str(row[4]).startswith("exfilingfees.htm#") for row in fees)
    assert all(not str(row[0]).lower().startswith("ffd") for row in financial)
    assert {row[1] for row in recon} == {"UNAVAILABLE"}
    assert {row[0] for row in recon} == {"Revenue", "Net Income"}


def test_r3_full_submission_supplies_structured_primary_when_sibling_flattened(tmp_path):
    primary = _write_filing(tmp_path, "FLATTENED PLAIN TEXT ONLY")
    _write_full_submission(primary, _fee_exhibit(), primary_html=_financial_html())

    db_path = tmp_path / "r3-structured.duckdb"
    _run_etl(tmp_path, db_path, primary)

    assert "<table" in primary.read_text(encoding="utf-8").lower()
    with duckdb.connect(str(db_path)) as conn:
        xbrl = conn.execute(
            "SELECT concept, unit, duration, issuer, origin_doc "
            "FROM sec_financial_facts WHERE source = 'xbrl' AND ticker = 'ANTH'"
        ).fetchall()
        fee = conn.execute(
            "SELECT concept, origin_doc FROM sec_fee_facts WHERE ticker = 'ANTH'"
        ).fetchall()

    assert ("us-gaap:Revenues", "USD", "2026-01-01..2026-12-31", ANTH_CIK,
            "primary-document.html") in xbrl
    assert ("ffd:FilingFee", "exfilingfees.htm") in fee


def test_r3_full_submission_end_to_end_identity_and_provenance(tmp_path):
    primary = _write_filing(tmp_path, _financial_html())
    _write_full_submission(primary, _fee_exhibit())

    db_path = tmp_path / "r3-e2e.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        xbrl = conn.execute(
            "SELECT issuer, unit, duration, dimensions, value, origin_doc, "
            "document_id, fact_id FROM sec_financial_facts "
            "WHERE source = 'xbrl' AND concept = 'us-gaap:Revenues' "
            "AND duration = '2026-01-01..2026-12-31'"
        ).fetchone()
        table = conn.execute(
            "SELECT issuer, unit, duration, dimensions, value, origin_doc "
            "FROM sec_financial_facts WHERE source = 'table' "
            "AND concept = 'us-gaap:Revenues' "
            "AND duration = '2026-01-01..2026-12-31'"
        ).fetchone()
        recon = conn.execute(
            "SELECT status, table_value, xbrl_value FROM sec_reconciliation "
            "WHERE concept = 'us-gaap:Revenues' "
            "AND duration = '2026-01-01..2026-12-31'"
        ).fetchone()
        fee = conn.execute(
            "SELECT concept, origin_doc FROM sec_fee_facts WHERE ticker = 'ANTH'"
        ).fetchall()

    assert xbrl == (
        ANTH_CIK, "USD", "2026-01-01..2026-12-31", "", "1234000",
        "primary-document.html", "primary-document.html",
        "primary-document.html#fact0",
    )
    assert table == (
        ANTH_CIK, "USD", "2026-01-01..2026-12-31", "", "1234000",
        "primary-document.html",
    )
    assert recon == ("MATCH", "1234000", "1234000")
    assert ("ffd:FilingFee", "exfilingfees.htm") in fee


def test_r3_full_submission_artifact_path_rolls_back_and_reruns(tmp_path):
    primary = _write_filing(tmp_path, _fee_only_primary())
    _write_full_submission(primary, _fee_exhibit())
    db_path = tmp_path / "r3-rollback.duckdb"

    assert _run_etl(tmp_path, db_path, primary) >= 0

    def _snapshot():
        with duckdb.connect(str(db_path)) as conn:
            return [
                conn.execute(
                    f"SELECT * FROM {name} WHERE ticker = 'ANTH' ORDER BY ALL"
                ).fetchall()
                for name in (
                    "sec_financial_facts", "sec_fee_facts", "sec_reconciliation",
                )
            ]

    prior = _snapshot()
    assert prior[1], "fee provenance must be acquired through full-submission.txt"

    def _flaky_insert(conn, payloads):
        conn.executemany(sec_reconcile._INSERT_SQL, list(payloads)[:1])
        raise RuntimeError("r3 injected mid-write")

    with patch.object(sec_reconcile, "_insert_rows", _flaky_insert):
        assert _run_etl(tmp_path, db_path, primary) >= 0
    assert _snapshot() == prior

    assert _run_etl(tmp_path, db_path, primary) >= 0
    assert _snapshot() == prior


def test_r3_edgartools_fallback_preserves_structured_html(tmp_path, monkeypatch):
    import edgar

    structured = (
        "<html><body><ix:nonFraction name=\"us-gaap:Revenues\" contextRef=\"c1\" "
        "unitRef=\"u1\">1</ix:nonFraction></body></html>"
    )

    class _FakeFiling:
        accession_number = ACCESSION

        def html(self):
            return structured

        def text(self):
            return "FLATTENED PLAIN TEXT"

    class _FakeFilings:
        empty = False

        def latest(self, limit):
            return _FakeFiling()

    class _FakeCompany:
        def __init__(self, key):
            self.key = key

        def get_filings(self, form):
            return _FakeFilings()

    monkeypatch.setattr(edgar, "Company", _FakeCompany)
    monkeypatch.setattr(
        "api.services._edgar_identity.ensure_edgar_identity", lambda: None
    )
    monkeypatch.setattr(embed_edgar, "_DOWNLOAD_DIR", tmp_path / "dl")

    path, form, accession = embed_edgar._fetch_filing_with_edgartools("ANTH", ["10-K"])
    content = Path(path).read_text(encoding="utf-8")

    assert form == "10-K"
    assert accession == ACCESSION
    assert "<ix:nonFraction" in content
    assert "FLATTENED" not in content


def test_r3_unestablished_identity_is_never_a_match(tmp_path):
    missing_issuer = _r3_ingest(
        tmp_path,
        _r3_html(caption="Amounts in USD", issuer=""),
        cik="",
        name="r3-no-issuer.duckdb",
    )
    with duckdb.connect(str(missing_issuer)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
    assert all(row[0] != "MATCH" for row in statuses)
    assert {row[0] for row in statuses} == {"UNAVAILABLE"}

    missing_unit = _r3_ingest(
        tmp_path,
        _r3_html(header="Year 2026", measure=""),
        name="r3-no-unit.duckdb",
    )
    with duckdb.connect(str(missing_unit)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
    assert all(row[0] != "MATCH" for row in statuses)


def test_r3_quarter_ended_header_resolves_true_duration(tmp_path):
    db_path = _r3_ingest(
        tmp_path,
        _r3_html(
            caption="Amounts in USD",
            header="Quarter ended March 31, 2026",
            period_xml=(
                "<xbrli:startDate>2026-01-01</xbrli:startDate>"
                "<xbrli:endDate>2026-03-31</xbrli:endDate>"
            ),
        ),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT status, duration FROM sec_reconciliation"
        ).fetchall()

    assert rows == [("MATCH", "2026-01-01..2026-03-31")]


def _dimensioned_primary() -> str:
    explicit = (
        '<xbrli:segment><xbrli:explicitMember '
        'dimension="us-gaap:ProductOrServiceAxis">'
        "us-gaap:WidgetsMember</xbrli:explicitMember></xbrli:segment>"
    )
    return (
        "<html><body>"
        + _header(
            _duration("2026-01-01", "2026-12-31", context_id="c1"),
            _duration(
                "2026-01-01", "2026-12-31", context_id="c2", dimensions=explicit,
            ),
            _unit(),
        )
        + "<table><caption>Amounts in USD</caption>"
        "<tr><th>Item</th><th>Year 2026</th></tr>"
        "<tr><td>Revenue</td><td>100</td></tr></table>"
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usd" decimals="0">100</ix:nonFraction></p>'
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c2" '
        'unitRef="usd" decimals="0">100</ix:nonFraction></p>'
        + _filler()
        + "</body></html>"
    )


def test_r3_acquisition_path_preserves_dimensions_without_collapsing(tmp_path):
    primary = _write_filing(tmp_path, "FLATTENED PLAIN TEXT ONLY")
    _write_full_submission(primary, primary_html=_dimensioned_primary())

    db_path = tmp_path / "r3-dims.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        facts = conn.execute(
            "SELECT source, dimensions, issuer, unit, duration "
            "FROM sec_financial_facts WHERE ticker = 'ANTH' "
            "AND concept = 'us-gaap:Revenues' ORDER BY source, dimensions"
        ).fetchall()
        recon = conn.execute(
            "SELECT dimensions, status FROM sec_reconciliation "
            "WHERE ticker = 'ANTH' ORDER BY dimensions"
        ).fetchall()

    assert ("table", "", ANTH_CIK, "USD", "2026-01-01..2026-12-31") in facts
    assert (
        "xbrl", "us-gaap:ProductOrServiceAxis=us-gaap:WidgetsMember",
        ANTH_CIK, "USD", "2026-01-01..2026-12-31",
    ) in facts
    assert recon == [
        ("", "MATCH"),
        ("us-gaap:ProductOrServiceAxis=us-gaap:WidgetsMember", "UNAVAILABLE"),
    ]


# --- r4: table identity, compound units, inclusive durations ---------------

_R4_CUSTOMER_SEGMENT = (
    '<xbrli:segment><xbrldi:explicitMember dimension="custom:CustomerAxis">'
    "custom:CustomerA</xbrldi:explicitMember></xbrli:segment>"
)


def _r4_unit_divide(unit_id: str = "usdshare",
                    numerator: str = "iso4217:USD",
                    denominator: str = "xbrli:shares") -> str:
    return (
        f'<xbrli:unit id="{unit_id}"><xbrli:divide>'
        f"<xbrli:unitNumerator><xbrli:measure>{numerator}</xbrli:measure>"
        "</xbrli:unitNumerator>"
        f"<xbrli:unitDenominator><xbrli:measure>{denominator}</xbrli:measure>"
        "</xbrli:unitDenominator></xbrli:divide></xbrli:unit>"
    )


def _r4_inline_cell(value: str, *, context: str = "c1", unit: str = "usd",
                    name: str = "us-gaap:Revenues",
                    fact_id: str | None = None) -> str:
    id_attr = f' id="{fact_id}"' if fact_id else ""
    return (
        f'<td><ix:nonFraction{id_attr} name="{name}" contextRef="{context}" '
        f'unitRef="{unit}">{value}</ix:nonFraction></td>'
    )


def _r4_table(*, caption: str = "", header: str = "Year 2026",
              rows) -> str:
    caption_html = f"<caption>{caption}</caption>" if caption else ""
    rows_html = "".join(
        f"<tr><td>{label}</td>{cells}</tr>" for label, cells in rows
    )
    return (
        f"<table>{caption_html}<tr><th>Item</th><th>{header}</th></tr>"
        f"{rows_html}</table>"
    )


def _r4_document(*, header_parts, table_html: str,
                 facts_html: str = "") -> str:
    return (
        "<html><body>"
        + _header(*header_parts)
        + table_html
        + facts_html
        + _filler()
        + "</body></html>"
    )


def _r4_etl(tmp_path, html: str, *, name: str = "r4.duckdb"):
    primary = _write_filing(tmp_path, html)
    db_path = tmp_path / name
    _run_etl(tmp_path, db_path, primary)
    return db_path


def test_r4_dimensioned_table_cell_never_matches_aggregate_xbrl(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="aggregate"),
        _duration("2026-01-01", "2026-12-31", context_id="segment",
                  dimensions=_R4_CUSTOMER_SEGMENT),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts in USD",
        rows=[("Revenue", _r4_inline_cell("100", context="segment"))],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="aggregate" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT dimensions, status, table_value, xbrl_value "
            "FROM sec_reconciliation ORDER BY dimensions"
        ).fetchall()
        table_dims = conn.execute(
            "SELECT dimensions FROM sec_financial_facts WHERE source = 'table'"
        ).fetchall()

    by_dims = {row[0]: row for row in rows}
    assert table_dims == [("custom:CustomerAxis=custom:CustomerA",)]
    assert by_dims[""][1] == "UNAVAILABLE"
    assert by_dims[""][2] is None
    assert by_dims["custom:CustomerAxis=custom:CustomerA"][1] == "MATCH"


def test_r4_per_share_table_never_matches_total_currency_xbrl(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="c1"),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts in USD per share",
        rows=[("Revenue", "<td>100</td>")],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT unit, status, table_value, xbrl_value "
            "FROM sec_reconciliation ORDER BY unit"
        ).fetchall()
        units = conn.execute(
            "SELECT source, unit FROM sec_financial_facts ORDER BY source"
        ).fetchall()

    assert "MATCH" not in {row[1] for row in rows}
    assert {row[1] for row in rows} == {"UNAVAILABLE"}
    assert ("table", "USD/SHARES") in units
    assert ("xbrl", "USD") in units


def test_r4_quarter_ending_june_30_matches_true_april_start(tmp_path):
    header_parts = [
        _duration("2026-04-01", "2026-06-30", context_id="c1"),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts in USD",
        header="Three months ended June 30, 2026",
        rows=[("Revenue", "<td>100</td>")],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT status, duration, table_value, xbrl_value "
            "FROM sec_reconciliation"
        ).fetchall()

    assert rows == [("MATCH", "2026-04-01..2026-06-30", "100", "100")]


def test_r4_same_sourced_dimension_matches_same_dimension(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="segment",
                  dimensions=_R4_CUSTOMER_SEGMENT),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts in USD",
        rows=[("Revenue", _r4_inline_cell("100", context="segment"))],
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT dimensions, status, table_value, xbrl_value "
            "FROM sec_reconciliation"
        ).fetchall()

    assert rows == [(
        "custom:CustomerAxis=custom:CustomerA", "MATCH", "100", "100",
    )]


def test_r4_same_compound_unit_matches_same_compound_unit(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="c1"),
        _r4_unit_divide(),
    ]
    table = _r4_table(
        caption="Amounts in USD per share",
        rows=[("Revenue", "<td>100</td>")],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usdshare">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT unit, status, table_value, xbrl_value "
            "FROM sec_reconciliation"
        ).fetchall()

    assert rows == [("USD/SHARES", "MATCH", "100", "100")]


def test_r4_inline_cell_with_missing_context_stays_unavailable(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="c1"),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts in USD",
        rows=[("Revenue", _r4_inline_cell("100", context="missing"))],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        table_identity = conn.execute(
            "SELECT issuer, unit, duration FROM sec_financial_facts "
            "WHERE source = 'table'"
        ).fetchall()

    assert {row[0] for row in statuses} == {"UNAVAILABLE"}
    assert table_identity == [("", "", "")]


def test_r4_conflicting_inline_cell_bindings_stay_unavailable(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="aggregate"),
        _duration("2026-01-01", "2026-12-31", context_id="s1",
                  dimensions=_R4_CUSTOMER_SEGMENT),
        _duration("2026-01-01", "2026-12-31", context_id="s2",
                  dimensions=(
                      '<xbrli:segment><xbrldi:explicitMember '
                      'dimension="custom:CustomerAxis">'
                      "custom:CustomerB</xbrldi:explicitMember>"
                      "</xbrli:segment>"
                  )),
        _unit(),
    ]
    conflicting_cell = (
        "<td>"
        '<ix:nonFraction name="us-gaap:Revenues" contextRef="s1" '
        'unitRef="usd">100</ix:nonFraction>'
        '<ix:nonFraction name="us-gaap:Revenues" contextRef="s2" '
        'unitRef="usd">100</ix:nonFraction>'
        "</td>"
    )
    table = _r4_table(
        caption="Amounts in USD",
        rows=[("Revenue", conflicting_cell)],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="aggregate" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()

    assert "MATCH" not in {row[0] for row in statuses}
    assert {row[0] for row in statuses} == {"UNAVAILABLE"}


def test_r4_per_share_without_currency_never_becomes_total_usd(tmp_path):
    header_parts = [
        _duration("2026-01-01", "2026-12-31", context_id="c1"),
        _unit(),
    ]
    table = _r4_table(
        caption="Amounts per share",
        rows=[("Revenue", "<td>100</td>")],
    )
    facts = (
        '<p><ix:nonFraction name="us-gaap:Revenues" contextRef="c1" '
        'unitRef="usd">100</ix:nonFraction></p>'
    )
    db_path = _r4_etl(
        tmp_path,
        _r4_document(header_parts=header_parts, table_html=table,
                     facts_html=facts),
    )
    with duckdb.connect(str(db_path)) as conn:
        statuses = conn.execute(
            "SELECT status FROM sec_reconciliation"
        ).fetchall()
        table_unit = conn.execute(
            "SELECT unit FROM sec_financial_facts WHERE source = 'table'"
        ).fetchall()

    assert "MATCH" not in {row[0] for row in statuses}
    assert table_unit != [("USD",)]


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Three months ended June 30, 2026", "2026-04-01..2026-06-30"),
        ("Six months ended June 30, 2026", "2026-01-01..2026-06-30"),
        ("Quarter ended June 30, 2026", "2026-04-01..2026-06-30"),
        ("Half-year ended June 30, 2026", "2026-01-01..2026-06-30"),
        ("Three months ended September 30, 2026", "2026-07-01..2026-09-30"),
        ("Six months ended December 31, 2026", "2026-07-01..2026-12-31"),
        ("Quarter ended March 31, 2026", "2026-01-01..2026-03-31"),
        ("Year ended December 31, 2026", "2026-01-01..2026-12-31"),
        ("Three months ended February 29, 2024", "2023-12-01..2024-02-29"),
        ("Six months ended February 29, 2024", "2023-09-01..2024-02-29"),
        ("Three months ended February 28, 2023", "2022-12-01..2023-02-28"),
        ("Six months ended February 28, 2023", "2022-09-01..2023-02-28"),
    ],
)
def test_r4_period_boundaries_are_inclusive_and_calendar_correct(header, expected):
    sec_ingest = _sec_ingest()
    assert sec_ingest._period_from_header(header) == expected


@pytest.mark.parametrize(
    "header",
    [
        "Three months ended 2026",
        "Six months ended 2026",
        "Quarter ended 2026",
        "Half-year ended 2026",
        "Three months ended June 2026",
        "As of 2026",
    ],
)
def test_r4_ambiguous_duration_headers_stay_unresolved(header):
    sec_ingest = _sec_ingest()
    assert sec_ingest._period_from_header(header) == ""
