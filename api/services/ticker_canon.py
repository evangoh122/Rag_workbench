"""
ticker_canon.py — canonical display symbols for user-facing answers.

Internal corpus keys stay raw: ``TICKER_TO_CIK`` rows (api/config.py),
retriever/peer alias maps and DB ``ticker`` columns keep ``ANTH``. Only
rendered output is canonicalized, so user-facing answers never show ANTH.
"""
from __future__ import annotations

import re
from typing import Any

# Raw internal key -> canonical user-facing symbol.
CANONICAL_TICKERS: dict[str, str] = {"ANTH": "ANT"}

# Stored symbols that are also ordinary English words. A query may select these
# only through an explicit upper-case ticker mention ("FORM", "ONTO"), never
# through prose ("in its form S-1", "based on the filing").
AMBIGUOUS_ENGLISH_TICKERS: frozenset[str] = frozenset({"ON", "FORM", "ONTO", "TER"})

_TOKEN_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in CANONICAL_TICKERS), key=len, reverse=True)) + r")\b"
)


# Canonical user-facing symbol -> internal corpus key for query routing.
QUERY_TICKER_ALIASES: dict[str, str] = {
    display: raw for raw, display in CANONICAL_TICKERS.items()
}


def display_ticker(t: str) -> str:
    """Canonical display form of a ticker symbol; identity when unmapped."""
    return CANONICAL_TICKERS.get(t, t)


def query_tickers(symbol: str) -> set[str]:
    """Stored-symbol set a DB ``ticker`` filter must accept for ``symbol``.

    ``ANT`` (the user-facing canonical symbol) resolves to ``{"ANT", "ANTH"}``
    because the corpus stores the internal key ``ANTH``. Every other symbol
    resolves to itself only, so unrelated symbols never widen the filter.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return set()
    return {normalized, QUERY_TICKER_ALIASES.get(normalized, normalized)}


def normalize_selected_ticker(symbol: str) -> str:
    """Normalize a caller/UI-selected ticker to its stored corpus key.

    Selections arrive from the UI/client as ``ANT``, ``ant`` or a
    whitespace-padded variant; retrieval always needs the stored key ``ANTH``.
    Only the selected-ticker field is normalized — arbitrary query prose is
    never reinterpreted here.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return ""
    return QUERY_TICKER_ALIASES.get(normalized, normalized)


def canonicalize_user_text(text: str) -> str:
    """Map standalone canonicalizable symbol tokens to display form.

    Replaces only the standalone symbol (``\\bANTH\\b`` -> ``ANT``); words
    like ``ANTHROPIC`` and ``Anthropic`` are never altered. Idempotent.
    """
    if not text:
        return text
    return _TOKEN_RE.sub(lambda m: CANONICAL_TICKERS[m.group(1)], text)


def canonicalize_user_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize every user-facing text field of a response in place.

    Internal identifiers (``ticker``/``resolved_ticker``, retrieved-doc
    metadata, lineage keys, graph triples and the chart's internal ``ticker``)
    are deliberately left untouched so audit/provenance keeps the stored key.
    """
    for key in ("final_answer", "what_it_means", "how_to_interpret"):
        value = result.get(key)
        if isinstance(value, str):
            result[key] = canonicalize_user_text(value)

    follow_ups = result.get("follow_ups")
    if isinstance(follow_ups, list):
        result["follow_ups"] = [
            canonicalize_user_text(item) if isinstance(item, str) else item
            for item in follow_ups
        ]

    chart = result.get("chart")
    if isinstance(chart, dict):
        if isinstance(chart.get("title"), str):
            chart["title"] = canonicalize_user_text(chart["title"])
        for item in chart.get("series") or []:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                item["name"] = canonicalize_user_text(item["name"])
        for item in chart.get("data") or []:
            if isinstance(item, dict) and isinstance(item.get("period"), str):
                item["period"] = canonicalize_user_text(item["period"])
    return result
