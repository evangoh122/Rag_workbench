"""8-K / 6-K rows must never become the 'latest/prior filing' in sentiment queries."""
from unittest.mock import patch

import duckdb
import pytest

import api.services.sentiment as sent


def _db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE edgar_embeddings (ticker VARCHAR, accession VARCHAR, text VARCHAR, "
        "section_id VARCHAR, section_type VARCHAR, form_type VARCHAR, "
        "period_of_report VARCHAR, chunk_index INTEGER, embedding FLOAT[])"
    )
    rows = [
        # domestic: periodic rows carry synthetic YYYY-12-31; a January 8-K carries a real date
        ("DOM", "0000000001-25-000001", "Revenue improved strongly, gains and growth.", "Item 7", "narrative", "10-K", "2025-12-31", 0),
        ("DOM", "0000000001-24-000001", "Losses, impairment, decline and litigation risk.", "Item 7", "narrative", "10-K", "2024-12-31", 0),
        ("DOM", "0000000001-26-000005", "Unexpected loss and weak results.", "item_2.02", "narrative", "8-K", "2026-01-15", 0),
        # foreign: 6-K with a later real date than the 20-F rows
        ("FOR", "0000000002-25-000001", "Strong growth and profit gains.", "full_text", "narrative", "20-F", "2025-12-31", 0),
        ("FOR", "0000000002-24-000001", "Losses and decline and risk.", "full_text", "narrative", "20-F", "2024-12-31", 0),
        ("FOR", "0000000002-26-000009", "Interim report text.", "full_text", "narrative", "6-K", "2026-03-01", 0),
        # legacy NULL form_type + prospectus row stay selectable
        ("OLD", "0000000003-25-000001", "Good gains.", "Item 7", "narrative", None, "2025-12-31", 0),
        ("OLD", "0000000003-24-000001", "Bad losses.", "Item 7", "narrative", "S-1", "2024-12-31", 0),
    ]
    rows = [
        r + ([1.0, 0.0, 0.0] if r[0] == "DOM" and r[2].startswith("Revenue") else [0.6, 0.8, 0.0],)
        for r in rows
    ]
    conn.executemany("INSERT INTO edgar_embeddings VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return conn


class _Mgr:
    def __init__(self, conn):
        self.conn = conn

    def get_connection(self):
        return self.conn


@pytest.fixture
def mgr():
    with patch("api.db.database.db_manager", _Mgr(_db())):
        yield


@pytest.mark.parametrize(
    "ticker,latest,prior",
    [
        ("DOM", "0000000001-25-000001", "0000000001-24-000001"),
        ("FOR", "0000000002-25-000001", "0000000002-24-000001"),
    ],
)
def test_event_forms_do_not_change_latest_prior(mgr, ticker, latest, prior):
    cmp_ = sent.compare_filing_sentiment(ticker)
    assert cmp_ is not None
    assert cmp_["filing_b"]["accession"] == latest
    assert cmp_["filing_a"]["accession"] == prior
    assert sent.get_filing_sentiment(ticker)["accession"] == latest
    hist = sent.get_sentiment_history(ticker)
    assert {h.get("accession") for h in hist} == {latest, prior}


def test_tone_shift_unaffected_by_event_forms(mgr):
    base = sent.compute_tone_shift("DOM")
    assert base is not None
    # removing the 8-K row must not change the answer
    from api.db import database
    c = database.db_manager.get_connection()
    c.execute("DELETE FROM edgar_embeddings WHERE form_type IN ('8-K','6-K')")
    assert sent.compute_tone_shift("DOM") == base


def test_legacy_null_and_prospectus_rows_still_selected(mgr):
    cmp_ = sent.compare_filing_sentiment("OLD")
    assert cmp_["filing_b"]["accession"] == "0000000003-25-000001"
    assert cmp_["filing_a"]["accession"] == "0000000003-24-000001"


def test_tests_fail_without_the_filter(mgr, monkeypatch):
    """Guard against vacuous tests: disabling the filter must change the latest filing."""
    monkeypatch.setattr(sent, "_EXCLUDE_EVENT_FORMS_SQL", "(1=1)", raising=True)
    # the SQL is f-string-evaluated at call time, so patching the module constant suffices
    assert sent.get_filing_sentiment("DOM")["accession"] == "0000000001-26-000005"
    assert sent.get_filing_sentiment("FOR")["accession"] == "0000000002-26-000009"


def test_explicit_accessions_compare_even_with_one_periodic_filing(mgr):
    """Explicit accessions must not be gated on the periodic-filing count."""
    from api.db import database
    c = database.db_manager.get_connection()
    c.execute("DELETE FROM edgar_embeddings WHERE accession = '0000000001-24-000001'")
    # DOM now has 1 periodic filing + 1 8-K; auto-selection cannot pick two
    assert sent.compare_filing_sentiment("DOM") is None
    cmp_ = sent.compare_filing_sentiment(
        "DOM", "0000000001-25-000001", "0000000001-26-000005"
    )
    assert cmp_ is not None
    assert cmp_["filing_a"]["accession"] == "0000000001-25-000001"
    assert cmp_["filing_b"]["accession"] == "0000000001-26-000005"
