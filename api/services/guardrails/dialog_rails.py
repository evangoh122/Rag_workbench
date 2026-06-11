"""
dialog_rails.py — Phase 13: Dialog Rail (Off-Topic Detection).

Detects off-topic queries (non-financial) and gracefully refuses to answer.
Uses keyword-based topic classification (no external ML model required).

Usage:
    from api.services.guardrails.dialog_rails import check_dialog, DialogVerdict
    verdict = check_dialog(user_message)
    if verdict.off_topic:
        return {"answer": verdict.refusal_message}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class DialogVerdict:
    on_topic: bool
    off_topic: bool = False
    topic: Optional[str] = None
    refusal_message: Optional[str] = None


# ── Financial topic keywords ─────────────────────────────────────────────────
# Queries matching these are considered on-topic for a financial SEC filing assistant.

_FINANCIAL_KEYWORDS: set[str] = {
    # Financial statements
    "revenue", "income", "profit", "loss", "earnings", "margin", "cost",
    "expense", "cash flow", "operating", "net income", "gross profit",
    "ebitda", "free cash flow", "fcf", "capex", "capital expenditure",
    "depreciation", "amortization", "sga", "r&d", "research and development",
    "dividend", "buyback", "share repurchase", "eps", "earnings per share",
    # Balance sheet
    "assets", "liabilities", "equity", "debt", "cash", "inventory",
    "receivable", "payable", "goodwill", "intangible", "current ratio",
    "debt to equity", "leverage", "liquidity", "solvency",
    # SEC filings
    "10-k", "10-q", "8-k", "sec filing", "edgar", "xbrl", "gaap",
    "non-gaap", "restatement", "amendment", "annual report",
    "quarterly report", "form type", "accession", "cik",
    # Company/stock
    "stock", "share", "ticker", "market cap", "valuation", "p/e",
    "price to earnings", "portfolio", "sector", "industry",
    "competitor", "market share",
    # Financial metrics
    "revenue growth", "profit margin", "operating margin", "net margin",
    "return on equity", "roe", "return on assets", "roa",
    "current ratio", "quick ratio", "working capital",
    # Business
    "fiscal year", "fiscal quarter", "segment", "subsidiary",
    "acquisition", "merger", "spinoff", "ipo", "offering",
    # Semiconductor-specific
    "gpu", "data center", "gaming", "ai chip", "semiconductor",
    "wafer", "fab", "foundry", "chip", "asic", "fpga",
    "dram", "nand", "memory", "microcontroller", "analog",
    "test equipment", "packaging", "substrate", "euv lithography",
    # Risk & governance
    "risk", "risks", "risk factor", "management discussion", "md&a",
    "material weakness", "going concern", "contingency", "litigation",
}

# ── Off-topic indicators ─────────────────────────────────────────────────────
# Queries strongly matching these are off-topic.

_OFF_TOPIC_PATTERNS: list[tuple[str, str]] = [
    (r"\b(recipe|cook|bake|ingredient)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(weather|temperature|forecast|rain|snow)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(sports|football|basketball|soccer|baseball|game score)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(movie|tv show|netflix|youtube|music|song|album)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(politics|election|president|senator|congress|democrat|republican)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(joke|riddle|poem|story|tale|novel)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(homework|exam|test|quiz|assignment|essay)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(travel|hotel|flight|vacation|restaurant|food)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(dating|relationship|love|romance|marriage)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
    (r"\b(medical|doctor|symptom|disease|medication|health advice)\b",
     "I'm a financial analysis assistant. I can help with SEC filings, financial statements, and company analysis. What would you like to know?"),
]

_COMPILED_OFF_TOPIC: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), refusal)
    for pattern, refusal in _OFF_TOPIC_PATTERNS
]


def check_dialog(message: str) -> DialogVerdict:
    """Check if the user query is on-topic for a financial SEC filing assistant.

    Args:
        message: The raw user input string.

    Returns:
        DialogVerdict with off_topic=True if the query is clearly non-financial.
    """
    if not message or not message.strip():
        return DialogVerdict(on_topic=True)

    # Check off-topic patterns
    for compiled, refusal in _COMPILED_OFF_TOPIC:
        if compiled.search(message):
            return DialogVerdict(
                on_topic=False,
                off_topic=True,
                topic="off_topic",
                refusal_message=refusal,
            )

    # Check if query contains at least one financial keyword
    msg_lower = message.lower()
    has_financial_keyword = any(
        kw in msg_lower for kw in _FINANCIAL_KEYWORDS
    )

    if has_financial_keyword:
        return DialogVerdict(on_topic=True)

    # Short queries (commands, greetings) are allowed through
    if len(message.split()) <= 3:
        return DialogVerdict(on_topic=True)

    # Queries without financial keywords and longer than 3 words
    # are potentially off-topic but we allow them through with a soft check
    # (the retrieval/generation pipeline will handle insufficient context)
    return DialogVerdict(on_topic=True)
