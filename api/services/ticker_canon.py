"""
ticker_canon.py — canonical display symbols for user-facing answers.

Internal corpus keys stay raw: ``TICKER_TO_CIK`` rows (api/config.py),
retriever/peer alias maps and DB ``ticker`` columns keep ``ANTH``. Only
rendered output is canonicalized, so user-facing answers never show ANTH.
"""
from __future__ import annotations

import re

# Raw internal key -> canonical user-facing symbol.
CANONICAL_TICKERS: dict[str, str] = {"ANTH": "ANT"}

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


def canonicalize_user_text(text: str) -> str:
    """Map standalone canonicalizable symbol tokens to display form.

    Replaces only the standalone symbol (``\\bANTH\\b`` -> ``ANT``); words
    like ``ANTHROPIC`` and ``Anthropic`` are never altered. Idempotent.
    """
    if not text:
        return text
    return _TOKEN_RE.sub(lambda m: CANONICAL_TICKERS[m.group(1)], text)
