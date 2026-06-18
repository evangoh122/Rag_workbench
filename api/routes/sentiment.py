"""Sentiment routes — Loughran-McDonald dictionary-based SEC filing analysis.

Endpoints for per-filing sentiment scoring, filing-to-filing comparison,
sentiment history, and embedding-based tone shift detection.
All read-only, zero-LLM-cost (except tone-shift which uses embeddings, not LLM).
"""
from __future__ import annotations

import asyncio
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.services.sentiment import (
    get_filing_sentiment,
    compare_filing_sentiment,
    get_sentiment_history,
    compute_tone_shift,
)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


@router.get("/{ticker}", response_model=Dict[str, Any])
async def sentiment_summary(
    ticker: str,
    accession: str | None = Query(default=None, description="Specific accession number (latest if omitted)"),
):
    """Return Loughran-McDonald sentiment for a filing's sections.

    Sections are scored independently (Risk Factors, MD&A, etc.) and
    aggregated into a full-filing total.
    """
    result = get_filing_sentiment(ticker.upper(), accession)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No filing data found for ticker '{ticker}'")
    return result


@router.get("/{ticker}/compare", response_model=Dict[str, Any])
async def sentiment_compare(
    ticker: str,
    accession_a: str | None = Query(default=None, description="Prior filing accession"),
    accession_b: str | None = Query(default=None, description="Current filing accession"),
):
    """Compare sentiment between two filings of the same company.

    Defaults to the two most recent filings when accession params are omitted.
    Returns per-category deltas and percentage changes.
    """
    result = compare_filing_sentiment(ticker.upper(), accession_a, accession_b)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Need at least 2 filings for comparison, found none for '{ticker}'",
        )
    return result


@router.get("/{ticker}/history", response_model=Dict[str, Any])
async def sentiment_history(ticker: str):
    """Return sentiment scores for all filings of a ticker, most recent first."""
    history = get_sentiment_history(ticker.upper())
    if not history:
        raise HTTPException(status_code=404, detail=f"No filing data found for ticker '{ticker}'")
    return {"ticker": ticker.upper(), "filings": history}


@router.get("/{ticker}/tone-shift", response_model=Dict[str, Any])
async def sentiment_tone_shift(ticker: str):
    """Measure embedding-based cosine similarity between MD&A sections across filings.

    Low similarity indicates strategic shift or major business changes,
    orthogonal to word-count sentiment.  Runs the blocking DB+numpy work
    in a thread to avoid stalling the event loop.
    """
    result = await asyncio.to_thread(compute_tone_shift, ticker.upper())
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Need >=2 filings with MD&A embeddings for tone-shift, found none for '{ticker}'",
        )
    return result
