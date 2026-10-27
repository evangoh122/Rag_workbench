"""
tests/test_langgraph_engine.py — Unit tests for the LangGraph engine.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
import polars as pl
from api.services.langgraph_engine import (
    retrieval_node, extraction_node, math_node, verification_node,
    eval_node, output_node, abstention_node, run_auditable_rag,
    _humanize_concept, _named_uncovered_company, _resolve_query_ticker,
    classifier_node,
)

@pytest.fixture
def base_state():
    return {
        "query": "What is the gross margin for AAPL?",
        "ticker": "AAPL",
        "retrieved_docs": [],
        "xbrl_facts": [],
        "math_result": None,
        "math_steps": [],
        "verification_status": "PENDING",
        "verification_reasoning": "",
        "final_answer": "",
        "status": {},
    }


def test_anthropic_resolves_and_is_not_out_of_universe():
    assert _resolve_query_ticker("What revenue did Anthropic report?", "NVDA") == "ANTH"
    assert _named_uncovered_company("What revenue did Anthropic report?") is None


@patch("api.services.langgraph_engine._ticker_has_xbrl", return_value=False)
def test_anthropic_numeric_query_uses_text_grounded_path(mock_has_xbrl):
    result = classifier_node({"query": "What was Anthropic revenue?", "ticker": "ANTH", "status": {}})

    mock_has_xbrl.assert_called_once_with("ANTH")
    assert result["query_type"] == "qualitative"
    assert result["numeric_text_grounded"] is True


@pytest.mark.parametrize("uncovered", ["OpenAI", "Stripe"])
def test_uncovered_company_still_abstains_when_anthropic_is_also_named(uncovered):
    result = run_auditable_rag(
        f"How does {uncovered} compare with Anthropic?",
        "ANTH",
    )

    assert result["verification_status"] == "ABSTAIN"
    assert result["resolved_ticker"] == ""
    assert uncovered.lower() in result["verification_reasoning"].lower()


@pytest.mark.parametrize("query", [
    "NVIDIA sales to Microsoft and Anthropic",
    "Microsoft and Anthropic as NVIDIA customers",
    "Does NVIDIA sell GPUs to Anthropic and OpenAI?",
])
def test_real_ticker_with_anthropic_and_uncovered_customers_does_not_abstain(query):
    class _Reached(Exception):
        pass

    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached), \
         patch("api.services.langgraph_engine._abstain_response") as mock_abstain:
        with pytest.raises(_Reached):
            run_auditable_rag(query, "MU")

    mock_abstain.assert_not_called()


@pytest.mark.parametrize("query", [
    "Compare Anthropic vs OpenAI",
    "OpenAI vs Anthropic",
    "Anthropic and Stripe",
])
def test_anthropic_alone_with_uncovered_company_abstains(query):
    result = run_auditable_rag(query, "MU")

    assert result["verification_status"] == "ABSTAIN"
    assert result["resolved_ticker"] == ""


def _alias_cases():
    from api.services.peer_comparison import _ENGLISH_WORD_TICKERS, _TICKER_TO_NAMES
    cases = []
    for ticker, names in _TICKER_TO_NAMES.items():
        if ticker == "ANTH":
            continue
        for alias in sorted(set(names) | {ticker}):
            if ticker in _ENGLISH_WORD_TICKERS and alias.upper() == ticker or alias == "on":
                # English-word symbols are only companies when written upper-case
                cases.append(alias.upper())
            elif alias.upper() == ticker:
                # ticker-equal aliases are not English words: any casing counts
                cases.extend([alias.lower(), alias.title(), alias.upper()])
            else:
                cases.append(alias.title())
    return cases


@pytest.mark.parametrize("alias", _alias_cases())
def test_every_covered_alias_with_anthropic_and_uncovered_does_not_abstain(alias):
    class _Reached(Exception):
        pass

    query = f"What were {alias}'s sales to Microsoft and Anthropic?"
    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached), \
         patch("api.services.langgraph_engine._abstain_response") as mock_abstain:
        with pytest.raises(_Reached):
            run_auditable_rag(query, "MU")

    mock_abstain.assert_not_called()


@pytest.mark.parametrize("query", [
    "Did tsm supply Anthropic and OpenAI?",
    "Did stm sell to Anthropic or Google?",
    "Does plab supply Anthropic or OpenAI?",
    "What were Amd's sales to Microsoft and Anthropic?",
])
def test_lowercase_ticker_equal_aliases_with_anthropic_do_not_abstain(query):
    class _Reached(Exception):
        pass

    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached), \
         patch("api.services.langgraph_engine._abstain_response") as mock_abstain:
        with pytest.raises(_Reached):
            run_auditable_rag(query, "MU")

    mock_abstain.assert_not_called()


def test_prose_upper_case_on_and_tsm_still_recognised():
    from api.services.peer_comparison import _tickers_named_in_query
    assert _tickers_named_in_query("Compare ON and TSM", strict_symbols=True) == ["ON", "TSM"]
    assert _tickers_named_in_query("revenue on tsm", strict_symbols=True) == ["TSM"]


def test_default_path_is_case_insensitive_and_pinned():
    from api.services.peer_comparison import _tickers_named_in_query
    assert _tickers_named_in_query("compare intc and txn") == ["INTC", "TXN"]
    assert _tickers_named_in_query("in the form of onto") == ["FORM", "ONTO"]


def test_detect_comparison_uses_default_strict_symbols():
    from api.services import peer_comparison as pc
    with patch.object(pc, "_tickers_named_in_query", wraps=pc._tickers_named_in_query) as spy:
        pc.detect_comparison("compare intc and txn", "MU")
    spy.assert_called_once_with("compare intc and txn")


@pytest.mark.parametrize("query", [
    "Compare Anthropic vs OpenAI in the form of a table",
    "Map Anthropic onto OpenAI",
    "What does Anthropic's Form S-1 say about OpenAI?",
    "Anthropic PBC vs OpenAI",
    "ANTH vs OpenAI",
    "Anthropic vs OpenAI in the form of a table",
    "Anthropic vs OpenAI onto ter",
    "Anthropic vs OpenAI on revenue",
])
def test_english_words_matching_tickers_do_not_count_as_covered(query):
    result = run_auditable_rag(query, "MU")

    assert result["verification_status"] == "ABSTAIN"


def test_spacex_anthropic_microsoft_does_not_abstain():
    # Intended behaviour: SPCX is another covered company, so the ANTH-only
    # abstain exception does not apply (same as a real ticker naming a customer).
    class _Reached(Exception):
        pass

    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached), \
         patch("api.services.langgraph_engine._abstain_response") as mock_abstain:
        with pytest.raises(_Reached):
            run_auditable_rag("SpaceX, Anthropic and Microsoft", "MU")

    mock_abstain.assert_not_called()


@pytest.mark.parametrize("query,ticker", [
    ("What share of Qualcomm revenue comes from Apple?", "QCOM"),
    ("How much does NVIDIA sell to Microsoft?", "NVDA"),
    ("Broadcom custom accelerator revenue from Google", "AVGO"),
])
def test_real_ticker_naming_uncovered_customer_does_not_abstain(query, ticker):
    class _Reached(Exception):
        pass

    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached), \
         patch("api.services.langgraph_engine._abstain_response") as mock_abstain:
        with pytest.raises(_Reached):
            run_auditable_rag(query, "MU")

    mock_abstain.assert_not_called()


@pytest.mark.parametrize("query", ["Micron revenue", "SpaceX revenue", "Tesla revenue"])
def test_plain_company_questions_unchanged(query):
    # Micron/SpaceX are covered (reach the graph); Tesla is uncovered (abstains).
    class _Reached(Exception):
        pass

    with patch("api.services.peer_comparison.detect_comparison", return_value=None), \
         patch("api.services.langgraph_engine.get_app", side_effect=_Reached):
        if "Tesla" in query:
            assert run_auditable_rag(query, "MU")["verification_status"] == "ABSTAIN"
        else:
            with pytest.raises(_Reached):
                run_auditable_rag(query, "MU")


@patch("api.services.peer_comparison.compute_metric")
def test_nvidia_investment_in_anthropic_uses_multi_company_comparison(mock_metric):
    # Known tradeoff: merely naming two covered companies selects explicit
    # comparison mode, matching the existing SPCX alias behaviour.
    mock_metric.return_value = {"value": 1.0, "period": "2026"}

    result = run_auditable_rag(
        "How does NVIDIA's investment in Anthropic affect its revenue?",
        "NVDA",
    )

    assert result["resolved_ticker"] == "NVDA"
    assert "| NVDA *(subject)* |" in result["final_answer"]
    assert "| ANTH |" in result["final_answer"]
    assert mock_metric.call_count == 2

class TestLangGraphNodes:
    @patch("api.services.langgraph_engine.EDGARHybridRetriever")
    @patch("api.services.langgraph_engine.rerank_docs")
    @patch("api.services.langgraph_engine.filter_retrieval")
    def test_retrieval_node(self, mock_filter, mock_rerank, mock_retriever_cls, base_state):
        mock_retriever = mock_retriever_cls.return_value
        mock_doc = MagicMock()
        mock_doc.page_content = "Apple revenue was $383B"
        mock_doc.metadata = {"source": "10-K"}
        mock_retriever.invoke.return_value = [mock_doc]

        mock_rerank.return_value = [mock_doc]

        mock_filter.return_value.filtered_chunks = [
            {"chunk_text": "Apple revenue was $383B", "metadata": {"source": "10-K"}}
        ]
        mock_filter.return_value.dropped_count = 0
        
        result = retrieval_node(base_state)
        assert len(result["retrieved_docs"]) == 1
        assert result["retrieved_docs"][0]["chunk_text"] == "Apple revenue was $383B"
        assert result["status"]["retrieval"] == "success"

    @patch("api.services.langgraph_engine.get_latest_10k_facts")
    def test_extraction_node(self, mock_get_facts, base_state):
        df = pl.DataFrame({
            "concept": ["Revenues"],
            "value": [383000000000.0]
        })
        mock_get_facts.return_value = df
        
        result = extraction_node(base_state)
        assert len(result["xbrl_facts"]) == 1
        assert result["xbrl_facts"][0]["concept"] == "Revenues"
        assert result["status"]["extraction"] == "success"

    def test_math_node_gross_margin(self, base_state):
        base_state["xbrl_facts"] = [
            {"concept": "Revenues", "value": 1000.0, "period": "2023-12-31"},
            {"concept": "CostOfRevenue", "value": 600.0, "period": "2023-12-31"}
        ]
        base_state["query"] = "What is the gross margin?"
        
        result = math_node(base_state)
        assert result["math_result"] == 40.0
        assert any("Gross Margin" in step for step in result["math_steps"])

    @patch("api.services.langgraph_engine.verifier.verify_entailment")
    def test_verification_node_pass(self, mock_verify, base_state):
        base_state["retrieved_docs"] = [{"chunk_text": "Revenue was $1000"}]
        base_state["math_result"] = 1000.0
        mock_verify.return_value = ("PASS", "Values match.")
        
        result = verification_node(base_state)
        assert result["verification_status"] == "PASS"
        assert result["verification_reasoning"] == "Values match."

    @patch("api.services.langgraph_engine.validate_extraction")
    @patch("api.services.langgraph_engine.score_and_route")
    def test_eval_node(self, mock_score, mock_validate, base_state):
        base_state["xbrl_facts"] = [{"concept": "Revenues", "value": 1000.0}]
        
        mock_validate.return_value.is_valid = True
        mock_score.return_value.route.value = "AUTO"
        mock_score.return_value.confidence = 0.95
        mock_score.return_value.triggers_fired = []
        
        result = eval_node(base_state)
        assert result["eval_route"] == "AUTO"
        assert result["eval_confidence"] == 0.95

    def test_output_node(self, base_state):
        base_state["math_result"] = 40.0
        base_state["verification_status"] = "PASS"
        base_state["verification_reasoning"] = "Verified."
        
        result = output_node(base_state)
        assert "40.0" in result["final_answer"]
        assert "Verified." in result["final_answer"]

    def test_abstention_node(self, base_state):
        result = abstention_node(base_state)
        assert "cannot answer" in result["final_answer"]

class TestLangGraphFullFlow:
    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_run_auditable_rag(self, mock_get_app, _mock_layers):
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "Mocked Answer"}

        result = run_auditable_rag("What is revenue?", "AAPL")
        assert result["final_answer"] == "Mocked Answer"
        # Educational-layer keys are always present (additive, default empty).
        assert result["what_it_means"] == ""
        assert result["how_to_interpret"] == ""
        assert result["follow_ups"] == []

    @patch("api.services.langgraph_engine.get_app")
    def test_run_auditable_rag_attaches_layers(self, mock_get_app):
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "Revenue was $37.4B."}
        with patch(
            "api.services.langgraph_engine._generate_educational_layers",
            return_value={
                "what_it_means": "It earned 37.4B.",
                "how_to_interpret": "Revenue is sales before costs.",
                "follow_ups": ["How did it grow?"],
            },
        ):
            result = run_auditable_rag("What is revenue?", "AAPL")
        assert result["what_it_means"] == "It earned 37.4B."
        assert result["follow_ups"] == ["How did it grow?"]

    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_resolved_ticker_overrides_when_company_named(self, mock_get_app, _layers):
        """A question naming a company resolves to it, not the UI default — and
        this is generic across the covered universe, not just NVDA/MU."""
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "ok"}

        # caller passes the stale UI default; the named company must win.
        for query, expected in [
            ("What was NVIDIA's revenue?", "NVDA"),
            ("Tell me about Broadcom margins", "AVGO"),
            ("Intel risk factors?", "INTC"),
            ("Texas Instruments gross profit", "TXN"),
        ]:
            result = run_auditable_rag(query, "MU")
            assert result["resolved_ticker"] == expected, query
            assert mock_app.invoke.call_args[0][0]["ticker"] == expected

    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_resolved_ticker_persists_on_generic_followup(self, mock_get_app, _layers):
        """A follow-up naming no company stays on the persisted ticker the UI
        sends — for any company, so follow-ups don't fall back to the default."""
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "ok"}

        for persisted in ["AVGO", "INTC", "AMD", "TXN"]:
            result = run_auditable_rag("What about its gross margin?", persisted)
            assert result["resolved_ticker"] == persisted
            assert mock_app.invoke.call_args[0][0]["ticker"] == persisted


class TestEducationalLayers:
    """Sections 3–5 of the Standard Response Framework (additive, best-effort)."""

    def test_guard_refusal_returns_empty(self):
        from api.services.langgraph_engine import _generate_educational_layers
        out = _generate_educational_layers(
            "q", "I cannot answer this with sufficient confidence.", "MU")
        assert out == {}

    def test_guard_empty_answer_returns_empty(self):
        from api.services.langgraph_engine import _generate_educational_layers
        assert _generate_educational_layers("q", "", "MU") == {}

    def test_disabled_flag_returns_empty(self, monkeypatch):
        from api.services.langgraph_engine import _generate_educational_layers
        monkeypatch.setenv("ANSWER_FRAMEWORK_ENABLED", "false")
        assert _generate_educational_layers("q", "Revenue was $37.4B.", "MU") == {}

    def test_happy_path_parses_json(self, monkeypatch):
        from api.services import langgraph_engine as eng
        monkeypatch.delenv("ANSWER_FRAMEWORK_ENABLED", raising=False)
        payload = (
            '{"what_it_means": "plain english", '
            '"how_to_interpret": "context", '
            '"follow_ups": ["a", "b", "c"]}'
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=payload))]
        )
        with patch.object(eng.Config, "get_provider_config",
                          return_value={"api_key": "k", "base_url": "http://x", "model": "m"}), \
             patch("openai.OpenAI", return_value=mock_client):
            out = eng._generate_educational_layers("What is revenue?", "Revenue was $37.4B.", "MU")
        assert out["what_it_means"] == "plain english"
        assert out["how_to_interpret"] == "context"
        assert out["follow_ups"] == ["a", "b", "c"]

    def test_malformed_json_returns_empty(self, monkeypatch):
        from api.services import langgraph_engine as eng
        monkeypatch.delenv("ANSWER_FRAMEWORK_ENABLED", raising=False)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json at all"))]
        )
        with patch.object(eng.Config, "get_provider_config",
                          return_value={"api_key": "k", "base_url": "http://x", "model": "m"}), \
             patch("openai.OpenAI", return_value=mock_client):
            out = eng._generate_educational_layers("q", "Revenue was $37.4B.", "MU")
        assert out == {}


class TestQueryClassification:
    """Numeric vs qualitative routing — segment/breakdown questions must NOT be
    answered with a single top-line XBRL number (the breakdown lives in the
    filing narrative, only the qualitative path reads it)."""

    def test_breakdown_questions_route_qualitative(self):
        from api.services.langgraph_engine import _is_numeric_query
        for q in [
            "How does Micron's revenue break down by product segment, such as memory chips or storage?",
            "What is the revenue breakdown by segment?",
            "Revenue by product category",
            "segment revenue composition",
            "revenue by geography",
            "data center segment revenue",
            # "Where does the revenue come from" follow-ups want the breakdown,
            # not the top-line total.
            "What were the main sources of this revenue, such as data center or gaming?",
            "What are NVIDIA's sources of revenue?",
            "Where does the revenue come from?",
            "What is its revenue driven by?",
        ]:
            assert _is_numeric_query(q) is False, q

    def test_plain_numeric_questions_stay_numeric(self):
        from api.services.langgraph_engine import _is_numeric_query
        for q in [
            "What was total revenue in 2023?",
            "What is the gross margin?",
            "net income last year",
            "free cash flow",
            "revenue year over year growth",
        ]:
            assert _is_numeric_query(q) is True, q


class TestQualitativeGrounding:
    """The qualitative path must not invent competitor/company names from the
    model's general knowledge — only names present in the filing context are
    allowed. We assert the grounding instruction is in the system prompt the
    LLM actually receives."""

    @patch("api.services.langgraph_engine._text_grounded_decorations",
           return_value={"note": "", "reasoning": "", "badge": ""})
    @patch("openai.OpenAI")
    def test_system_prompt_grounds_competitor_names(self, mock_openai_cls, _mock_deco):
        from api.services.langgraph_engine import qualitative_output_node

        captured: dict = {}

        def _create(**kwargs):
            captured["messages"] = kwargs.get("messages")
            msg = MagicMock()
            msg.tool_calls = None
            msg.content = "The filings under review do not enumerate specific competitors."
            resp = MagicMock()
            resp.choices = [MagicMock(message=msg)]
            return resp

        mock_openai_cls.return_value.chat.completions.create.side_effect = _create

        state = {
            "query": "Who are NVIDIA's competitors?",
            "ticker": "NVDA",
            "retrieved_docs": [
                {"chunk_text": "NVIDIA designs GPUs for data centers and gaming.",
                 "metadata": {"source": "10-K", "ticker": "NVDA"}}
            ],
            "xbrl_facts": [],
            "query_intent": "general",
            "history": [],
            "status": {},
        }

        result = qualitative_output_node(state)

        sys_msg = captured["messages"][0]
        assert sys_msg["role"] == "system"
        content = sys_msg["content"].lower()
        # The guardrail must (1) restrict company/competitor names to the context
        # and (2) explicitly forbid general-knowledge names.
        assert "only name competitors" in content
        assert "general knowledge" in content
        assert "do not enumerate specific competitors" in content
        assert result["status"]["output"] == "success"


class TestHumanizeConcept:
    """`_humanize_concept` turns raw XBRL concepts into readable table labels.
    Guards against the NameError regression where the helper was referenced but
    never defined."""

    def test_mapped_concept_uses_display_name(self):
        assert _humanize_concept("NetIncomeLoss") == "Net Income"
        assert _humanize_concept("GrossProfit") == "Gross Profit"
        assert _humanize_concept("CostOfGoodsAndServicesSold") == "COGS"
        assert (
            _humanize_concept("RevenueFromContractWithCustomerExcludingAssessedTax")
            == "Revenue"
        )

    def test_unmapped_concept_splits_pascal_case(self):
        assert _humanize_concept("SomeUnmappedConceptValue") == "Some Unmapped Concept Value"

    def test_empty_concept_is_passthrough(self):
        assert _humanize_concept("") == ""


class TestOutputNodeComparisonTable:
    """The comparison path renders a wide (pivoted) GFM markdown table — one row
    per period, one column per metric — with humanized concept labels."""

    def _comparison_state(self, facts, query="compare net income across the years"):
        return {
            "query": query,
            "ticker": "AAPL",
            "query_intent": "comparison",
            "retrieved_docs": [],
            "xbrl_facts": facts,
            "math_result": None,
            "math_steps": [],
            "verification_status": "PASS",
            "verification_reasoning": "Verified.",
            "final_answer": "",
            "status": {},
        }

    def _period_rows(self, answer):
        """Table body rows (start with a | + a date)."""
        return [ln for ln in answer.splitlines()
                if ln.startswith("| ") and ln[2:6].isdigit()]

    def test_concept_is_humanized_in_wide_header(self):
        facts = [
            {"concept": "NetIncomeLoss", "period_end": "2023-12-31", "value": 5_000_000_000.0},
            {"concept": "NetIncomeLoss", "period_end": "2024-12-31", "value": 6_000_000_000.0},
        ]
        answer = output_node(self._comparison_state(facts))["final_answer"]
        # Metric appears once, as a column header (wide pivot), not per row.
        assert "| Period | Net Income |" in answer
        assert "NetIncomeLoss" not in answer
        # Two period rows, one per fiscal year, compact-formatted.
        rows = self._period_rows(answer)
        assert len(rows) == 2
        assert "5.00B" in answer and "6.00B" in answer

    def test_duplicates_collapsed_and_capped_by_period(self):
        # 7 distinct periods, each duplicated (amended-filing style) = 14 rows.
        # Cap is on PERIODS: keep the last 6 distinct periods, one row each.
        years = [f"{y}-12-31" for y in range(2018, 2025)]  # 2018..2024
        facts = []
        for y in years:
            for _ in range(2):
                facts.append({"concept": "NetIncomeLoss", "period_end": y, "value": 1_000.0})

        answer = output_node(self._comparison_state(facts))["final_answer"]
        rows = self._period_rows(answer)
        assert len(rows) == 6
        periods = [ln.split("|")[1].strip() for ln in rows]
        assert len(periods) == len(set(periods))          # no repeats
        assert "2024-12-31" in periods                     # most recent kept
        assert "2019-12-31" in periods
        assert "2018-12-31" not in periods                 # oldest dropped

    def test_gross_margin_query_derives_margin_column(self):
        # Filer tags only Gross Profit + COGS (no Revenue). Revenue is derived as
        # GP + COGS; Gross Margin % = GP / Revenue * 100.
        facts = [
            {"concept": "GrossProfit", "period_end": "2024-08-29", "value": 5_613_000_000.0},
            {"concept": "CostOfGoodsAndServicesSold", "period_end": "2024-08-29", "value": 19_498_000_000.0},
        ]
        answer = output_node(
            self._comparison_state(facts, query="what is the gross margin")
        )["final_answer"]
        assert "| Period | Revenue | Gross Profit | Gross Margin |" in answer
        # Revenue derived = 25.111B; GM = 5.613 / 25.111 = 22.4%.
        assert "25.11B" in answer
        assert "22.4%" in answer

    def test_negative_gross_profit_margin(self):
        facts = [
            {"concept": "GrossProfit", "period_end": "2023-08-31", "value": -1_416_000_000.0},
            {"concept": "CostOfRevenue", "period_end": "2023-08-31", "value": 16_956_000_000.0},
        ]
        answer = output_node(
            self._comparison_state(facts, query="gross margin trend")
        )["final_answer"]
        # Revenue = -1.416 + 16.956 = 15.54B; GM = -1.416/15.54 = -9.1%.
        assert "-1.42B" in answer
        assert "-9.1%" in answer


class TestScalarAnswerFormatting:
    """Single-number answers get thousand separators, not a raw float repr."""

    def _scalar_state(self, math_result, intent="general"):
        return {
            "query": "what was NVDA revenue",
            "ticker": "NVDA",
            "query_intent": intent,
            "retrieved_docs": [],
            "xbrl_facts": [],
            "math_result": math_result,
            "math_steps": [],
            "verification_status": "PASS",
            "verification_reasoning": "Verified.",
            "final_answer": "",
            "status": {},
        }

    def test_large_scalar_gets_thousand_separators(self):
        answer = output_node(self._scalar_state(215_938_000_000.0))["final_answer"]
        assert "215,938,000,000" in answer
        assert "215938000000.0" not in answer
