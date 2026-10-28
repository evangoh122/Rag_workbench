"""
tests/test_sec_reconcile.py — fixture regressions for SEC structure-aware
financial parsing / XBRL reconciliation.

No network. Persistence tests use a tmp DuckDB database.
"""
from __future__ import annotations

from decimal import Decimal

import duckdb
import lxml.html
import pytest

from api.models.eval_types import Provenance
from api.services import sec_reconcile
from api.services.sec_reconcile import (
    ContinuationNode,
    FactKey,
    ReconciliationRow,
    ReconcileStatus,
    StatementFact,
    extract_fact_text,
    extract_ix_facts,
    is_fee_fact,
    normalize_numeric,
    parse_statement_tables,
    reconcile,
    resolve_continuations,
    split_fee_vs_financial,
    store_reconciliation,
)

CIK = "0002130357"
ACCESSION = "0001628280-26-067168"


def _fact(concept: str, value: str, **kw) -> StatementFact:
    base = dict(
        issuer=CIK,
        concept=concept,
        unit="USD",
        duration="2025-01-01..2025-12-31",
        accession=ACCESSION,
        dimensions={},
        ticker="ANTH",
    )
    base.update(kw)
    return StatementFact(value=Decimal(value), **base)


# --- 1. numeric normalization (finding 1) ----------------------------------

def test_normalize_numeric_applies_scale_and_sign():
    f = normalize_numeric("12,345", scale=6)
    assert f.supported is True
    assert f.value == Decimal("12345000000")
    assert f.raw == "12,345"
    assert f.scale == 6

    g = normalize_numeric("500", scale=3, sign="-")
    assert g.value == Decimal("-500000")
    assert g.raw == "500"
    assert g.sign == "-"


def test_normalize_numeric_zerodash_is_exact_zero():
    f = normalize_numeric("—", fmt="ixt:zerodash")
    assert f.value == Decimal(0)
    assert f.raw == "—"
    assert f.supported is True


def test_normalize_numeric_unsupported_format_is_explicit():
    f = normalize_numeric("1,234", fmt="ixt:unsupported-format")
    assert f.supported is False
    assert f.value is None
    assert f.raw == "1,234"


# --- 2. ix:exclude stripped; ix:hidden facts stay valid (finding 2) -------

def test_ix_exclude_stripped_and_ix_hidden_facts_stay_present():
    html = (
        "<html><body>"
        '<ix:hidden><ix:nonFraction id="h1" name="us-gaap:Assets" contextRef="c1">'
        "42</ix:nonFraction></ix:hidden>"
        '<p><ix:nonFraction id="f1" name="us-gaap:Revenue" contextRef="c1">'
        "Acme <ix:exclude>(see note 1)</ix:exclude> Corp</ix:nonFraction></p>"
        "</body></html>"
    )
    facts = extract_ix_facts(html, document_id="doc-1")
    by_id = {f.fact_id: f for f in facts}

    assert "h1" in by_id  # ix:hidden fact stays present
    assert by_id["h1"].hidden is True
    assert by_id["h1"].text == "42"  # and valid / extracted
    assert by_id["h1"].document_id == "doc-1"

    assert by_id["f1"].hidden is False
    assert by_id["f1"].text == "Acme Corp"  # ix:exclude text stripped

    frag = lxml.html.fragment_fromstring(
        "<div>Acme <ix:exclude>(see note 1)</ix:exclude> Corp</div>"
    )
    assert extract_fact_text(frag) == "Acme Corp"


# --- 3. rowspan/colspan header flattening (finding 3) ---------------------

def test_multirow_header_flattens_without_column_shift():
    html = (
        "<table>"
        '<tr><th rowspan="2">Item</th><th colspan="2">Year</th></tr>'
        "<tr><th>2026</th><th>2025</th></tr>"
        "<tr><td>Revenue</td><td>100</td><td>90</td></tr>"
        "</table>"
    )
    tables = parse_statement_tables(html)
    assert len(tables) == 1
    t = tables[0]
    assert t.columns == ("Item", "Year | 2026", "Year | 2025")

    row = t.rows[0]
    assert row.label == "Revenue"  # label stays in its column
    assert [c.column for c in row.cells] == ["Year | 2026", "Year | 2025"]
    assert [c.value for c in row.cells] == [Decimal(100), Decimal(90)]


# --- 4. header detection + header_ambiguity (finding 4) -------------------

def test_bold_td_header_detected_with_reported_ambiguity():
    html = (
        "<table>"
        "<tr><td><b>Item</b></td><td><b>2026</b></td><td><b>2025</b></td></tr>"
        "<tr><td>Revenue</td><td>100</td><td>90</td></tr>"
        "</table>"
    )
    t = parse_statement_tables(html)[0]
    assert t.columns == ("Item", "2026", "2025")  # not col_1/col_2
    assert t.header_ambiguity is True  # reported, not guessed silently
    assert t.rows[0].label == "Revenue"


def test_th_only_header_reports_no_ambiguity():
    html = (
        "<table>"
        "<tr><th>Item</th><th>2026</th><th>2025</th></tr>"
        "<tr><td>Revenue</td><td>100</td><td>90</td></tr>"
        "</table>"
    )
    t = parse_statement_tables(html)[0]
    assert t.columns == ("Item", "2026", "2025")
    assert t.header_ambiguity is False


# --- 5. scale note, parenthesized negatives, period columns ---------------

def test_table_parsing_preserves_scale_note_negatives_and_periods():
    html = (
        "<table>"
        "<caption>Consolidated Statements of Operations (In thousands)</caption>"
        "<tr><th>Item</th><th>Year 2026</th><th>Year 2025</th></tr>"
        "<tr><td>Revenue</td><td>1,234</td><td>(1,234)</td></tr>"
        "</table>"
    )
    t = parse_statement_tables(html)[0]
    assert t.scale_note == "(In thousands)"
    assert t.scale == 3
    assert t.columns == ("Item", "Year 2026", "Year 2025")  # period columns kept

    row = t.rows[0]
    assert row.provenance is Provenance.STRUCTURED_TABLE
    assert row.cells[0].value == Decimal(1234)
    assert row.cells[1].value == Decimal(-1234)  # parentheses -> negative
    assert row.cells[1].raw == "(1,234)"


# --- 6. fee facts are never financials ------------------------------------

def test_fee_facts_split_away_and_never_reconcile_as_financials():
    assert is_fee_fact("ffd:FilingFee") is True
    assert is_fee_fact(_fact("us-gaap:FeeTable", "15000")) is True
    assert is_fee_fact("us-gaap:Revenues") is False

    table = [_fact("us-gaap:Revenues", "100")]
    xbrl = [_fact("ffd:FilingFee", "15000"), _fact("us-gaap:FeeTable", "15000")]
    fee, fin = split_fee_vs_financial(xbrl)
    assert [f.concept for f in fee] == ["ffd:FilingFee", "us-gaap:FeeTable"]
    assert fin == []

    rows = reconcile(table, xbrl)
    assert len(rows) == 1
    assert rows[0].status is ReconcileStatus.UNAVAILABLE
    assert rows[0].xbrl_value is None  # no fee amount ever a financial value


# --- 7. fee-only XBRL filing reports UNAVAILABLE explicitly ---------------

def test_fee_only_xbrl_reports_unavailable_for_statement_table():
    # Financial statement table present for CIK 0002130357, accession
    # 0001628280-26-067168; its XBRL carries filing-fee facts only.
    html = (
        "<table>"
        "<tr><th>Item</th><th>2026</th></tr>"
        "<tr><td>Revenue</td><td>1,234</td></tr>"
        "<tr><td>Net Income</td><td>500</td></tr>"
        "</table>"
    )
    parsed = parse_statement_tables(html)[0]
    assert [r.label for r in parsed.rows] == ["Revenue", "Net Income"]

    table_facts = [
        StatementFact(
            issuer=CIK,
            concept=r.label,
            unit="USD",
            duration="2025-01-01..2025-12-31",
            value=r.cells[0].value,
            accession=ACCESSION,
            ticker="ANTH",
        )
        for r in parsed.rows
    ]
    xbrl_facts = [
        _fact("ffd:FilingFee", "15000", duration="2026-03-31"),
        _fact("ffd:FeeTable", "15000", duration="2026-03-31"),
    ]

    rows = reconcile(table_facts, xbrl_facts)
    assert {r.key.concept for r in rows} == {"Revenue", "Net Income"}
    assert {r.status for r in rows} == {ReconcileStatus.UNAVAILABLE}  # explicit
    assert all(r.xbrl_value is None for r in rows)  # fee facts never financials
    assert all(r.xbrl_value != Decimal("15000") for r in rows)


# --- 8. mismatches and non-equivalent keys -------------------------------

def test_true_value_mismatch_carries_both_values_and_delta():
    rows = reconcile([_fact("us-gaap:Revenues", "100")], [_fact("us-gaap:Revenues", "90")])
    assert [r.status for r in rows] == [ReconcileStatus.MISMATCH]
    assert rows[0].table_value == Decimal(100)
    assert rows[0].xbrl_value == Decimal(90)
    assert rows[0].delta == Decimal(-10)  # xbrl_value - table_value

    matched = reconcile([_fact("us-gaap:Revenues", "100")], [_fact("us-gaap:Revenues", "100")])
    assert [r.status for r in matched] == [ReconcileStatus.MATCH]
    assert matched[0].table_value == matched[0].xbrl_value == Decimal(100)


def test_non_equivalent_keys_are_never_compared():
    variants = [
        dict(unit="EUR"),  # different unit
        dict(duration="2024-01-01..2024-12-31"),  # different duration
        dict(duration="2025-12-31"),  # instant vs period
        dict(dimensions={"srt:ProductAxis": "Widgets"}),  # different dimensions
        dict(accession="0001628280-26-999999"),  # different accession
    ]
    table = [_fact("us-gaap:Revenues", "100")]
    xbrl = [_fact("us-gaap:Revenues", "90", **v) for v in variants]
    rows = reconcile(table, xbrl)
    assert not any(r.status is ReconcileStatus.MISMATCH for r in rows)
    assert all(r.status is ReconcileStatus.UNAVAILABLE for r in rows)


# --- 9. persistence: rollback + idempotent rerun (finding 6) --------------

def test_store_reconciliation_rolls_back_and_reruns_idempotent(tmp_path, monkeypatch):
    conn = duckdb.connect(str(tmp_path / "recon.duckdb"))
    key_rev = FactKey(
        issuer=CIK, concept="us-gaap:Revenues", unit="USD",
        duration="2025-01-01..2025-12-31", accession=ACCESSION,
    )
    key_ni = FactKey(
        issuer=CIK, concept="us-gaap:NetIncomeLoss", unit="USD",
        duration="2025-01-01..2025-12-31", accession=ACCESSION,
    )
    prior = [
        ReconciliationRow(key=key_rev, status=ReconcileStatus.MATCH, ticker="ANTH",
                          table_value=Decimal(100), xbrl_value=Decimal(100), delta=Decimal(0)),
        ReconciliationRow(key=key_ni, status=ReconcileStatus.MISMATCH, ticker="ANTH",
                          table_value=Decimal(5), xbrl_value=Decimal(4), delta=Decimal(-1)),
    ]
    assert store_reconciliation(conn, prior) == 2

    def _snapshot():
        return conn.execute(
            "SELECT concept, status, table_value, xbrl_value, delta, ticker, accession "
            "FROM sec_reconciliation ORDER BY concept"
        ).fetchall()

    assert len(_snapshot()) == 2
    before = _snapshot()

    replacement = [
        ReconciliationRow(key=key_rev, status=ReconcileStatus.MATCH, ticker="ANTH",
                          table_value=Decimal(100), xbrl_value=Decimal(100), delta=Decimal(0)),
        ReconciliationRow(key=key_ni, status=ReconcileStatus.UNAVAILABLE, ticker="ANTH",
                          table_value=Decimal(7), xbrl_value=None, delta=None),
    ]

    def _flaky_insert(cn, payloads):
        cn.executemany(sec_reconcile._INSERT_SQL, list(payloads)[:1])  # mid-write...
        raise RuntimeError("injected mid-write failure")

    with monkeypatch.context() as m:
        m.setattr(sec_reconcile, "_insert_rows", _flaky_insert)
        with pytest.raises(RuntimeError):
            store_reconciliation(conn, replacement)

    # rollback: prior rows intact, mid-write insert gone
    assert _snapshot() == before

    # rerun succeeds and is idempotent (delete-before-insert is safe)
    assert store_reconciliation(conn, replacement) == 2
    after = _snapshot()
    assert [r[0] for r in after] == ["us-gaap:NetIncomeLoss", "us-gaap:Revenues"]
    assert store_reconciliation(conn, replacement) == 2
    assert _snapshot() == after
    conn.close()


# --- 10. continuation chains (finding 7) ---------------------------------

def test_continuation_cycle_terminates():
    nodes = {
        "a": ContinuationNode(text="one ", continued_at="b", document_id="doc1"),
        "b": ContinuationNode(text="two ", continued_at="a", document_id="doc1"),
    }
    assert resolve_continuations(nodes, "a", "doc1") == "one two "


def test_continuation_missing_id_stops_cleanly():
    nodes = {"a": ContinuationNode(text="one ", continued_at="zzz", document_id="doc1")}
    assert resolve_continuations(nodes, "a", "doc1") == "one "
    assert resolve_continuations(nodes, "missing", "doc1") == ""


def test_continuation_cross_document_id_is_refused():
    nodes = {
        "a": ContinuationNode(text="one ", continued_at="b", document_id="doc1"),
        "b": ContinuationNode(text="FORBIDDEN", continued_at=None, document_id="doc2"),
    }
    out = resolve_continuations(nodes, "a", "doc1")
    assert out == "one "
    assert "FORBIDDEN" not in out
    assert resolve_continuations(nodes, "b", "doc1") == ""  # start id refused too


# --- 11. exact numerics / nonfinite safety (finding 4) ---------------------

def test_normalize_numeric_35_digit_value_is_exact_at_scale_zero():
    raw = "12345678901234567890123456789012345"
    f = normalize_numeric(raw, scale=0)
    assert f.supported is True
    assert f.value == Decimal(raw)
    assert str(f.value) == raw  # no scientific notation, no rounding
    assert f.raw == raw

    scaled = normalize_numeric(raw, scale=3)
    assert scaled.value == Decimal(raw + "000")  # exact, not default-context rounded
    from api.services.sec_reconcile import decimal_text
    assert decimal_text(scaled.value) == raw + "000"


@pytest.mark.parametrize("raw", ["Infinity", "-Infinity", "NaN", "sNaN"])
def test_normalize_numeric_rejects_nonfinite_values(raw):
    f = normalize_numeric(raw)
    assert f.supported is False
    assert f.value is None
    assert f.raw == raw


# --- 12. conflicting duplicates -> AMBIGUOUS (finding 3) ------------------

def test_conflicting_duplicates_are_ambiguous_order_independent():
    table = [_fact("us-gaap:Revenues", "100")]
    xbrl = [_fact("us-gaap:Revenues", "100"), _fact("us-gaap:Revenues", "200")]

    forward = reconcile(table, xbrl)
    backward = reconcile(table, list(reversed(xbrl)))
    assert [r.status for r in forward] == [ReconcileStatus.AMBIGUOUS]
    assert [r.status for r in backward] == [ReconcileStatus.AMBIGUOUS]
    assert forward[0].table_candidates == backward[0].table_candidates == (Decimal(100),)
    assert forward[0].xbrl_candidates == backward[0].xbrl_candidates == (
        Decimal(100), Decimal(200),
    )
    # Never silently choose a candidate, never a false MATCH.
    assert forward[0].table_value is None and forward[0].xbrl_value is None
    assert forward[0].delta is None


def test_identical_duplicates_collapse_to_one_fact():
    table = [_fact("us-gaap:Revenues", "100"), _fact("us-gaap:Revenues", "100")]
    xbrl = [_fact("us-gaap:Revenues", "100")]
    rows = reconcile(table, xbrl)
    assert len(rows) == 1
    assert rows[0].status is ReconcileStatus.MATCH
    assert rows[0].delta == Decimal(0)


def test_conflicting_duplicates_on_table_side_also_ambiguous():
    table = [_fact("us-gaap:Revenues", "100"), _fact("us-gaap:Revenues", "200")]
    xbrl = [_fact("us-gaap:Revenues", "100")]
    rows = reconcile(table, xbrl)
    assert [r.status for r in rows] == [ReconcileStatus.AMBIGUOUS]


# --- r3: exact negative/parenthesis normalization (Sol B3) -----------------


def test_r3_negative_and_parenthesized_35_digit_values_are_exact():
    from api.services.sec_reconcile import decimal_text

    raw = "12345678901234567890123456789012345"
    expected = "-" + raw

    for text, sign in ((raw, "-"), ("(" + raw + ")", None)):
        fact = normalize_numeric(text, scale=0, sign=sign)
        assert fact.supported is True
        assert fact.value == Decimal(expected)
        assert decimal_text(fact.value) == expected
        assert str(fact.value) == expected

    for text, sign in ((raw, "-"), ("(" + raw + ")", None)):
        scaled = normalize_numeric(text, scale=3, sign=sign)
        assert scaled.value == Decimal(expected + "000")
        assert decimal_text(scaled.value) == expected + "000"


def test_r3_reconcile_delta_is_exact_for_35_digit_values():
    from api.services.sec_reconcile import decimal_text

    low = "12345678901234567890123456789012345"
    high = "12345678901234567890123456789012346"
    rows = reconcile(
        [_fact("us-gaap:Revenues", low)],
        [_fact("us-gaap:Revenues", high)],
    )
    assert [row.status for row in rows] == [ReconcileStatus.MISMATCH]
    assert decimal_text(rows[0].delta) == "1"
    assert decimal_text(rows[0].table_value) == low
    assert decimal_text(rows[0].xbrl_value) == high
