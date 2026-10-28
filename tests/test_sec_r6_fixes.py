"""tests/test_sec_r6_fixes.py — PR40 r6 review-fix regressions.

Four independent findings, each exercised through the closest production path:

1. chat/comparison routing maps displayed ``ANT`` to stored ``ANTH`` without
   promoting lowercase prose or substrings to a ticker alias;
2. a structured-ingestion failure cannot abort a filing's RAG embeddings, and
   ordinary embedding failures are still reported as embedding failures;
3. impossible calendar dates resolve to an unestablished period, never raise;
4. the finished user-facing answer is canonicalized after decorations while
   provenance/retrieval/entity keys keep the internal ``ANTH``.

No network: filing discovery/model boundaries are mocked while parsing,
extraction, reconciliation, persistence and the real ETL loop run for real.
"""
from __future__ import annotations

import re
import sys
import types
from unittest.mock import MagicMock, patch

# tests/test_scripts.py stubs bs4 in sys.modules when collected first; restore
# the real package before this module imports the ETL script.
if sys.modules.get("bs4") is not None and not isinstance(sys.modules["bs4"], types.ModuleType):
    sys.modules.pop("bs4", None)

import bs4  # noqa: E402
import duckdb  # noqa: E402
import pytest  # noqa: E402
from loguru import logger  # noqa: E402

from api.services import hybrid_retriever  # noqa: E402
from api.services import langgraph_engine  # noqa: E402
from api.services import peer_comparison  # noqa: E402
from api.services import sec_reconcile  # noqa: E402
from api.services.ticker_canon import (  # noqa: E402
    canonicalize_user_text,
    display_ticker,
    query_tickers,
)
from scripts import embed_edgar  # noqa: E402
from scripts.embed_edgar import run_embed_edgar_etl  # noqa: E402

_REAL_BS4 = bs4
ACCESSION = "0001628280-26-067168"
ANTH_CIK = "0002130357"


@pytest.fixture(autouse=True)
def _real_bs4(monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", _REAL_BS4)
    monkeypatch.setattr(embed_edgar, "BeautifulSoup", _REAL_BS4.BeautifulSoup)


# --- fix 1: displayed ANT resolves to stored ANTH ---------------------------


@pytest.mark.parametrize("query,expected", [
    ("What revenue did ANT report?", "ANTH"),
    ("What revenue did ANTH report?", "ANTH"),
    ("What revenue did Anthropic report?", "ANTH"),
    ("what revenue did anthropic report?", "ANTH"),
])
def test_chat_resolver_selects_stored_key(query, expected):
    assert langgraph_engine._resolve_query_ticker(query, "NVDA") == expected


@pytest.mark.parametrize("query", [
    "an ant colony can carry many times its own weight",
    "The ant colony expanded quickly",
    "What is ANTA's revenue?",
    "What is ANTHROPICSTYLE revenue?",
    "What is AN revenue?",
    "Tell me about arbitrary prose with no company",
])
def test_lowercase_prose_and_substrings_keep_the_fallback(query):
    assert langgraph_engine._resolve_query_ticker(query, "NVDA") == "NVDA"


def test_comparison_routing_selects_anth_for_displayed_ant():
    explicit = peer_comparison.detect_comparison("Compare ANT vs NVDA revenue", "NVDA")
    assert explicit == {
        "mode": "explicit", "subject": "ANTH", "explicit": ["ANTH", "NVDA"],
    }

    peer = peer_comparison.detect_comparison(
        "How does ANT compare with its competitors?", "NVDA"
    )
    assert peer == {"mode": "peer", "subject": "ANTH", "explicit": ["ANTH"]}

    assert peer_comparison._tickers_named_in_query("ANTA and AN") == []
    assert peer_comparison._tickers_named_in_query("an ant colony") == []
    assert peer_comparison._tickers_named_in_query("Anthropic") == ["ANTH"]


def test_peer_followup_uses_stored_key_for_display_selection():
    assert peer_comparison.detect_comparison(
        "How does it compare to peers?", "ANT"
    ) == {"mode": "peer", "subject": "ANTH", "explicit": ["ANTH"]}


def test_run_auditable_rag_routes_displayed_ant_not_fallback():
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "ok"}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag(
            "What revenue did ANT report?", "NVDA"
        )

    assert result["resolved_ticker"] == "ANTH"
    assert app.invoke.call_args[0][0]["ticker"] == "ANTH"


def test_selected_display_ticker_is_routed_as_corpus_key():
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "ok"}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag(
            "What about its revenue?", "ANT"
        )

    assert result["resolved_ticker"] == "ANTH"
    assert app.invoke.call_args[0][0]["ticker"] == "ANTH"


def test_internal_identity_keys_stay_anth():
    assert query_tickers("ANT") == {"ANT", "ANTH"}
    assert query_tickers("ant") == {"ANT", "ANTH"}
    assert query_tickers("ANTH") == {"ANTH"}
    for symbol in ("ANTA", "AN", "ANTHROPIC", "NVDA"):
        assert query_tickers(symbol) == {symbol}
    assert display_ticker("ANTH") == "ANT"


# --- fix 2: structured failures cannot abort RAG embedding ------------------


def _context(period_xml: str, context_id: str = "c1") -> str:
    return (
        f'<xbrli:context id="{context_id}"><xbrli:entity>'
        f'<xbrli:identifier scheme="http://www.sec.gov/CIK">{ANTH_CIK}</xbrli:identifier>'
        f"</xbrli:entity><xbrli:period>{period_xml}</xbrli:period></xbrli:context>"
    )


def _unit() -> str:
    return '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'


def _filler() -> str:
    return "<p>" + ("Acme designs compute hardware for enterprise customers. " * 12) + "</p>"


def _inline_revenue_html() -> str:
    return (
        "<html><body>"
        '<ix:header>'
        + _context(
            "<xbrli:startDate>2026-01-01</xbrli:startDate>"
            "<xbrli:endDate>2026-12-31</xbrli:endDate>"
        )
        + _unit()
        + "</ix:header>"
        "<table><tr><th>Item</th><th>Year 2026</th></tr>"
        "<tr><td>Revenue</td><td>"
        '<ix:nonFraction name="us-gaap:Revenues" contextRef="c1" unitRef="usd" '
        'scale="0" decimals="0">12,345</ix:nonFraction>'
        "</td></tr></table>"
        + _filler()
        + "</body></html>"
    )


def _write_filing(tmp_path):
    filing = tmp_path / "sec-edgar-filings" / "ANTH" / "10-K" / ACCESSION
    filing.mkdir(parents=True)
    primary = filing / "primary-document.html"
    primary.write_text(_inline_revenue_html(), encoding="utf-8")
    return primary


def _run_etl(tmp_path, db_path, primary_path, model=None):
    if model is None:
        model = MagicMock()
        model.embed_documents.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    with patch.object(embed_edgar, "DB_PATH", str(db_path)), \
         patch.object(embed_edgar, "_DOWNLOAD_DIR", tmp_path / "dl"), \
         patch.object(embed_edgar, "_get_model", return_value=model), \
         patch.object(
             embed_edgar, "_fetch_filing_with_downloader",
             return_value=(str(primary_path), "10-K"),
         ):
        return run_embed_edgar_etl(tickers=["ANTH"], batch_size=10)


def _capture_logs(level="WARNING"):
    messages: list[str] = []
    handler = logger.add(lambda m: messages.append(str(m)), level=level)
    return messages, handler


def test_structured_exception_does_not_skip_committed_embeddings(tmp_path):
    primary = _write_filing(tmp_path)
    db_path = tmp_path / "structured-fail.duckdb"
    messages, handler = _capture_logs()
    try:
        with patch.object(
            embed_edgar, "ingest_filing_structured",
            side_effect=RuntimeError("injected structured failure"),
        ):
            stored = _run_etl(tmp_path, db_path, primary)
    finally:
        logger.remove(handler)

    assert stored > 0
    assert any(
        "Structured ingestion failed" in m
        and "ANTH" in m and ACCESSION in m
        and "injected structured failure" in m
        for m in messages
    )

    with duckdb.connect(str(db_path)) as conn:
        embeddings = conn.execute(
            "SELECT count(*) FROM edgar_embeddings WHERE ticker = 'ANTH'"
        ).fetchone()[0]
        tables = {
            row[0] for row in conn.execute(
                "SELECT table_name FROM duckdb_tables()"
            ).fetchall()
        }
    assert embeddings > 0
    assert "sec_financial_facts" not in tables


def test_structured_persist_failure_rolls_back_and_embeddings_still_commit(tmp_path):
    primary = _write_filing(tmp_path)
    db_path = tmp_path / "structured-rollback.duckdb"
    _run_etl(tmp_path, db_path, primary)

    with duckdb.connect(str(db_path)) as conn:
        before = conn.execute(
            "SELECT concept, value, source FROM sec_financial_facts "
            "WHERE ticker = 'ANTH' ORDER BY concept, source"
        ).fetchall()
        before_recon = conn.execute(
            "SELECT concept, status FROM sec_reconciliation "
            "WHERE ticker = 'ANTH' ORDER BY concept"
        ).fetchall()
    assert before

    with patch.object(
        sec_reconcile, "delete_and_insert_reconciliation",
        side_effect=RuntimeError("injected persist failure"),
    ):
        stored = _run_etl(tmp_path, db_path, primary)

    assert stored > 0
    with duckdb.connect(str(db_path)) as conn:
        after = conn.execute(
            "SELECT concept, value, source FROM sec_financial_facts "
            "WHERE ticker = 'ANTH' ORDER BY concept, source"
        ).fetchall()
        after_recon = conn.execute(
            "SELECT concept, status FROM sec_reconciliation "
            "WHERE ticker = 'ANTH' ORDER BY concept"
        ).fetchall()
        embeddings = conn.execute(
            "SELECT count(*) FROM edgar_embeddings WHERE ticker = 'ANTH'"
        ).fetchone()[0]

    # The failed rerun rolled back to the prior, complete structured state.
    assert after == before
    assert after_recon == before_recon
    assert embeddings > 0


def test_ordinary_embedding_failure_is_not_reported_as_structured(tmp_path):
    primary = _write_filing(tmp_path)
    db_path = tmp_path / "embedding-fail.duckdb"
    model = MagicMock()
    model.embed_documents.side_effect = RuntimeError("injected embedding failure")
    messages, handler = _capture_logs(level="ERROR")
    try:
        stored = _run_etl(tmp_path, db_path, primary, model=model)
    finally:
        logger.remove(handler)

    assert stored == 0
    assert any(
        "Failed to process ANTH" in m and "injected embedding failure" in m
        for m in messages
    )
    assert not any("Structured ingestion failed" in m for m in messages)


# --- fix 3: impossible calendar dates never raise ---------------------------


@pytest.mark.parametrize("header", [
    "As of June 31, 2026",
    "Balance sheet as of February 30, 2026",
    "As of February 29, 2023",
    "Three months ended June 31, 2026",
    "Six months ended February 30, 2026",
    "Nine months ended April 31, 2026",
    "Quarter ended June 31, 2026",
    "Half-year ended June 31, 2026",
    "Year ended February 30, 2026",
    "Year ended February 29, 2026",
])
def test_impossible_calendar_dates_are_unresolved(header):
    from api.services.sec_ingest import _period_from_header

    assert _period_from_header(header) == ""


@pytest.mark.parametrize("header,expected", [
    ("As of February 29, 2024", "2024-02-29"),
    ("As of December 31, 2026", "2026-12-31"),
    ("Three months ended February 29, 2024", "2023-12-01..2024-02-29"),
    ("Three months ended February 28, 2023", "2022-12-01..2023-02-28"),
    ("Six months ended February 29, 2024", "2023-09-01..2024-02-29"),
    ("Nine months ended February 29, 2024", "2023-06-01..2024-02-29"),
    ("Quarter ended February 29, 2024", "2023-12-01..2024-02-29"),
    ("Half-year ended February 29, 2024", "2023-09-01..2024-02-29"),
    ("Year ended February 29, 2024", "2023-03-01..2024-02-29"),
    ("Year ended December 31, 2026", "2026-01-01..2026-12-31"),
])
def test_valid_leap_and_non_leap_controls_still_resolve(header, expected):
    from api.services.sec_ingest import _period_from_header

    assert _period_from_header(header) == expected


# --- fix 4: canonicalize the finished answer before educational layers ------


def test_text_grounded_decoration_is_canonicalized_before_layers():
    with patch("openai.OpenAI") as mock_openai_cls:
        def _create(**_kwargs):
            msg = MagicMock()
            msg.tool_calls = None
            msg.content = "Anthropic reported revenue of $1.2 billion."
            resp = MagicMock()
            resp.choices = [MagicMock(message=msg)]
            return resp

        mock_openai_cls.return_value.chat.completions.create.side_effect = _create

        state = {
            "query": "What revenue did ANT report?",
            "ticker": "ANTH",
            "retrieved_docs": [{
                "chunk_text": "Anthropic reported revenue of $1.2 billion.",
                "metadata": {"ticker": "ANTH", "source": "S-1"},
            }],
            "xbrl_facts": [],
            "query_intent": "general",
            "history": [],
            "numeric_text_grounded": True,
            "status": {},
        }
        node_result = langgraph_engine.qualitative_output_node(state)
        # The raw decoration still names the internal corpus key before output.
        assert re.search(r"\bANTH\b", node_result["final_answer"])

        node_result["resolved_ticker"] = "ANTH"
        node_result["lineage"] = {"source_docs": ["ANTH:acc:0"]}
        app = MagicMock()
        app.invoke.return_value = node_result

        with patch.object(langgraph_engine, "get_app", return_value=app), \
             patch.object(
                 langgraph_engine, "_generate_educational_layers", return_value={}
             ) as layers, \
             patch.object(langgraph_engine, "_spawn_consensus"):
            result = langgraph_engine.run_auditable_rag(
                "What revenue did ANT report?", "NVDA"
            )

    answer = result["final_answer"]
    assert re.search(r"\bANTH\b", answer) is None
    assert "ANT's filing narrative" in answer
    assert "Anthropic reported" in answer  # prose word untouched
    assert "ANT" in answer  # already-canonical token not double-transformed
    # Educational layers see the canonical answer.
    assert re.search(r"\bANTH\b", layers.call_args[0][1]) is None
    # Raw provenance/retrieval keys stay internal.
    assert result["resolved_ticker"] == "ANTH"
    assert result["lineage"]["source_docs"] == ["ANTH:acc:0"]


def test_peer_comparison_answer_is_canonical_after_decorations():
    shaped = {
        "final_answer": "**Revenue — ANTH vs. peers**\n| Company | Revenue |\n| ANTH | $1 |\n| NVDA | $2 |",
        "retrieved_docs": [{"metadata": {"ticker": "ANTH"}, "chunk_text": "ANTH"}],
        "lineage": {"ticker": "ANTH"},
    }
    with patch.object(
        peer_comparison, "detect_comparison",
        return_value={"mode": "explicit", "subject": "ANTH", "explicit": ["ANTH", "NVDA"]},
    ), patch.object(peer_comparison, "run_peer_comparison", return_value=shaped):
        result = langgraph_engine.run_auditable_rag("Compare ANT vs NVDA revenue", "NVDA")

    assert re.search(r"\bANTH\b", result["final_answer"]) is None
    assert "| ANT |" in result["final_answer"]
    assert result["resolved_ticker"] == "ANTH"
    assert result["retrieved_docs"][0]["metadata"]["ticker"] == "ANTH"
    assert result["lineage"]["ticker"] == "ANTH"


def test_graph_rag_answer_is_canonical_but_entities_stay_internal():
    from api.services import graph_rag_engine

    with patch.object(graph_rag_engine, "_get_llm") as get_llm:
        get_llm.return_value.invoke.return_value.content = "ANTH disclosed the figures."
        result = graph_rag_engine.generate_answer({
            "query": "What did ANTH disclose?",
            "ticker": "ANTH",
            "extracted_triples": [],
        })

    assert result["final_answer"] == "ANT disclosed the figures."


def test_canonicalization_preserves_anthropic_and_arbitrary_text():
    assert canonicalize_user_text(
        "ANTHROPIC filed its S-1; Anthropic PBC and ANTH ticker are distinct."
    ) == "ANTHROPIC filed its S-1; Anthropic PBC and ANT ticker are distinct."
    assert canonicalize_user_text("an ant colony") == "an ant colony"
    assert canonicalize_user_text("") == ""


def test_hybrid_retriever_still_resolves_anthropic_name():
    assert hybrid_retriever.resolve_ticker_from_query(
        "What revenue did Anthropic report?", ""
    ) == "ANTH"
