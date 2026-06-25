from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
from loguru import logger
from api.services.chat_engine import chat_sql
from api.services.rag_engine import ask_rag
from api.services.langgraph_engine import run_auditable_rag
from api.services.graph_rag_engine import run_graph_rag
from api.services.sec_client import chunk_filing_sections
from api.services.sec_analyzer import analyze_filing
from api.services.xbrl_relevance import (
    filter_facts_for_query,
    format_fact_for_display,
    get_relevant_facts,
)
from api.models.schemas import (
    ChatRequest, ChatResponse, SourceItem,
    VerificationResult, PipelineStatus,
)
from api.services.guardrails.input_rails import check_input
from api.services.guardrails.dialog_rails import check_dialog
from api.services.guardrails.output_rails import check_output
from api.db.database import db_manager
from api.services.llm_health import get_llm_tracker

router = APIRouter(prefix="/api/chat", tags=["chat"])

_tracker = get_llm_tracker()

_IS_DEV = os.getenv("ENVIRONMENT", "production").lower() == "development"


def _error_detail(e: Exception, context: str = "") -> str:
    """Return detailed error in dev, generic in production."""
    if _IS_DEV:
        return f"{context}: {type(e).__name__}: {e}" if context else f"{type(e).__name__}: {e}"
    return "Internal server error"

# ── Conversational detection ─────────────────────────────────────────────────
_CONVERSATIONAL_KEYWORDS = {
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "how are you", "what's up", "thanks", "thank you", "bye", "goodbye",
    "who are you", "what can you do", "help me", "what is this",
}
_MAX_CONVERSATIONAL_WORDS = 6


def _is_conversational(message: str) -> bool:
    """Detect greetings, thanks, and simple questions that don't need RAG."""
    msg = message.strip().lower()
    if not msg:
        return False
    if any(msg == kw or msg.startswith(kw + " ") or msg.startswith(kw + ",") or msg.startswith(kw + "!")
           for kw in _CONVERSATIONAL_KEYWORDS):
        return True
    if len(msg.split()) <= _MAX_CONVERSATIONAL_WORDS and not any(
        c.isupper() for c in message.split() if len(c) > 2
    ):
        financial_signals = {"revenue", "margin", "profit", "income", "earnings", "stock", "price", "10-k", "10-q", "sec", "filing"}
        if not any(w in msg for w in financial_signals):
            return True
    return False


def _apply_input_rails(message: str) -> None:
    """Apply input + dialog rails. Raises 400 if blocked."""
    input_verdict = check_input(message)
    if input_verdict.blocked:
        raise HTTPException(status_code=400, detail=input_verdict.reason)
    dialog_verdict = check_dialog(message)
    if dialog_verdict.off_topic:
        raise HTTPException(status_code=400, detail=dialog_verdict.refusal_message)


def _apply_output_rails(answer: str, context: str = "") -> str:
    """Apply output rails. Returns masked answer if PII detected."""
    verdict = check_output(answer, context)
    if verdict.masked_answer:
        return verdict.masked_answer
    return answer


# ── Shared LLM call for conversational fast path ─────────────────────────────

def _conversational_llm_call(message: str) -> str:
    """Call LLM directly for conversational messages (no RAG)."""
    from openai import OpenAI
    from api.config import Config
    cfg = Config.get_provider_config()
    client = OpenAI(api_key=cfg["api_key"] or "local", base_url=cfg["base_url"], timeout=15.0)
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": "You are a helpful financial analysis assistant. Be concise and friendly."},
            {"role": "user", "content": message},
        ],
        temperature=0.7,
        max_tokens=200,
        timeout=15.0,
    )
    return resp.choices[0].message.content.strip()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/sql", response_model=ChatResponse)
async def chat_sql_endpoint(req: ChatRequest):
    _apply_input_rails(req.message)
    try:
        result = chat_sql(req.message, req.history)
        if "answer" in result:
            result["answer"] = _apply_output_rails(result["answer"])
        _tracker.record_success()
        return ChatResponse(
            type=result.get("type", "text"),
            answer=result.get("answer", ""),
            sql=result.get("sql"),
            data=result.get("data"),
        )
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/sql")
        raise HTTPException(status_code=500, detail=_error_detail(e, "SQL query failed"))


@router.post("/rag", response_model=ChatResponse)
async def chat_rag_endpoint(req: ChatRequest):
    _apply_input_rails(req.message)
    try:
        answer = ask_rag(req.message)
        answer = _apply_output_rails(answer)
        _tracker.record_success()
        return ChatResponse(
            type="text",
            answer=answer,
            pipeline_status=PipelineStatus(
                input="success", retrieval="success", extraction="success",
                math="success", verification="success", output="success",
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/rag")
        raise HTTPException(status_code=500, detail=_error_detail(e, "RAG failed"))


@router.post("/graph-rag", response_model=ChatResponse)
async def chat_graph_rag_endpoint(req: ChatRequest):
    _apply_input_rails(req.message)
    try:
        if not req.ticker:
            raise HTTPException(status_code=400, detail="Ticker is required for Graph RAG")
        result = run_graph_rag(req.message, req.ticker)
        answer = _apply_output_rails(result["final_answer"])
        _tracker.record_success()
        return ChatResponse(
            type="text",
            answer=answer,
            entities=result["search_entities"],
            triples=result["extracted_triples"],
            pipeline_status=PipelineStatus(
                input="success", retrieval="success", extraction="success",
                math="success", verification="success", output="success",
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/graph-rag")
        raise HTTPException(status_code=500, detail=_error_detail(e, "Graph RAG failed"))


@router.post("/auditable-rag", response_model=ChatResponse)
async def chat_auditable_rag_endpoint(req: ChatRequest):
    _apply_input_rails(req.message)
    try:
        # Fast path: conversational messages bypass the full RAG pipeline
        if _is_conversational(req.message):
            answer = _conversational_llm_call(req.message)
            answer = _apply_output_rails(answer)
            _tracker.record_success()
            return ChatResponse(
                type="text",
                answer=answer,
                verification=VerificationResult(
                    status="SKIPPED",
                    reasoning="Conversational query — no RAG pipeline",
                ),
                pipeline_status=PipelineStatus(
                    input="success", retrieval="skipped", extraction="skipped",
                    math="skipped", verification="skipped", output="success",
                ),
            )

        from api.routes.conjoint import role_guidance_for
        result = run_auditable_rag(
            req.message, req.ticker, history=req.history,
            role_guidance=role_guidance_for(req.role),
        )
        answer = _apply_output_rails(result["final_answer"])
        _tracker.record_success()

        # ── Reduce XBRL facts to what's relevant for THIS question ──────────────
        # The raw xbrl_facts list (a) repeats the same concept across multiple
        # XBRL frames/contexts and (b) only some terminal nodes populate the
        # relevant subset. Normalise it here, at the single response chokepoint,
        # so every query path (numeric / qualitative / comparison) shows a
        # deduped, query-relevant, properly-labelled fact set.
        raw_facts = filter_facts_for_query(req.message, result.get("xbrl_facts") or [])
        seen: set = set()
        deduped_facts = []
        for f in raw_facts:
            normalised = format_fact_for_display(f)
            key = (normalised["concept"], normalised["value"], normalised["period"])
            if key in seen:
                continue
            seen.add(key)
            deduped_facts.append(normalised)

        relevant_xbrl = result.get("relevant_xbrl") or []
        xbrl_badge = result.get("xbrl_badge", "")
        xbrl_group = result.get("xbrl_group", "")
        if not relevant_xbrl and deduped_facts:
            rel = get_relevant_facts(
                req.message,
                deduped_facts,
                filter_by_period=False,
            )
            relevant_xbrl = [format_fact_for_display(f) for f in rel["relevant"]]
            xbrl_badge = rel["badge_text"]
            xbrl_group = rel["group"]

        # Full list (collapsed in the UI) shows the deduped, normalised facts —
        # not 180+ raw rows with blank Period/Label.
        display_facts = deduped_facts

        # Map retrieved docs to flat SourceItem matching frontend expectations
        sources = []
        for d in result["retrieved_docs"]:
            meta = d.get("metadata", {})
            sources.append(SourceItem(
                text=d.get("chunk_text", ""),
                ticker=meta.get("ticker", ""),
                accession=meta.get("accession_number", meta.get("accession", "")),
                section=meta.get("section_id", meta.get("section", "")),
                edgar_url=meta.get("edgar_url", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={meta.get('ticker', '')}"),
                distance=meta.get("distance"),
            ))

        return ChatResponse(
            type="text",
            answer=answer,
            ticker=result.get("resolved_ticker", req.ticker or ""),
            sources=sources,
            xbrl_facts=display_facts,
            relevant_xbrl=relevant_xbrl,
            xbrl_badge=xbrl_badge,
            xbrl_group=xbrl_group,
            polygon_data=result.get("polygon_data", []),
            what_it_means=result.get("what_it_means", ""),
            how_to_interpret=result.get("how_to_interpret", ""),
            follow_ups=result.get("follow_ups", []),
            verification=VerificationResult(
                status=result["verification_status"],
                reasoning=result["verification_reasoning"],
            ),
            math_steps=result["math_steps"],
            pipeline_status=PipelineStatus(**result["status"]),
            confidence=result.get("eval_confidence"),
            eval_route=result.get("eval_route"),
            lineage=result.get("lineage"),
            chart=result.get("chart"),
            tone_analysis=result.get("tone_analysis"),
            consensus=result.get("consensus"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat route failed")
        _tracker.record_failure(str(e), context="chat/auditable-rag")
        raise HTTPException(status_code=500, detail=_error_detail(e, "Auditable RAG failed"))


@router.post("/sec-analyzer")
async def chat_sec_analyzer_endpoint(req: ChatRequest):
    """
    Structured signal extraction from SEC filing chunks for bank analysts.
    """
    try:
        if not req.ticker:
            raise HTTPException(status_code=400, detail="Ticker is required for SEC Analyzer")
            
        # Strict Ticker Validation to prevent injection
        import re
        if not re.match(r"^[A-Z0-9.-]{1,10}$", req.ticker.upper()):
            raise HTTPException(status_code=400, detail="Invalid Ticker format")
            
        chunks = chunk_filing_sections(req.ticker)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"No filing data found for {req.ticker}")
        chunk_texts = [c["chunk_text"] for c in chunks]
        result = analyze_filing(chunk_texts, req.ticker)
        _tracker.record_success()
        # Apply output rails to text-bearing fields in the structured result
        if isinstance(result, dict):
            for flag in result.get("risk_flags", []):
                if isinstance(flag, dict) and "excerpt" in flag:
                    flag["excerpt"] = _apply_output_rails(flag["excerpt"])
            for fwd in result.get("forward_looking", []):
                if isinstance(fwd, dict) and "text" in fwd:
                    fwd["text"] = _apply_output_rails(fwd["text"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/sec-analyzer")
        raise HTTPException(status_code=500, detail=_error_detail(e, "SEC Analyzer failed"))


class FeedbackRequest(BaseModel):
    message_id: str = ""
    query: str = Field(default="", max_length=1000)
    answer: str = Field(default="", max_length=10000)
    agrees: bool


@router.post("/feedback", status_code=204)
async def chat_feedback_endpoint(req: FeedbackRequest):
    import uuid
    vid = str(uuid.uuid4())
    did = req.message_id or vid
    try:
        conn = db_manager.get_review_connection()
        conn.execute("""
            INSERT INTO reviewer_verdicts (id, decision_id, reviewer_agrees, notes)
            VALUES (?, ?, ?, ?)
        """, (
            vid,
            did,
            1 if req.agrees else 0,
            f"Query: {req.query[:200]} | Answer: {req.answer[:200]}",
        ))
    except Exception as e:
        logger.warning(f"Failed to record chat feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")
