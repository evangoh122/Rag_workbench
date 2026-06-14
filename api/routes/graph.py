"""Evidence-Graph routes (Phase C).

Click-through auditability: given a triple's ``chunk_id`` (the stable id Phase B
writes, ``ticker:accession:chunk_index``), return the source excerpt and filing
metadata so the UI can show *where in the filing* a graph edge came from.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.db.database import db_manager

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _parse_chunk_id(chunk_id: str) -> tuple[str, str, int | None]:
    """Split ``ticker:accession:chunk_index`` → (ticker, accession, index|None).

    Ticker/accession never contain ':', so a left/right split is unambiguous
    even if the accession contains dashes. A '-' index means "unknown".
    """
    parts = chunk_id.split(":")
    if len(parts) < 3:
        raise ValueError("chunk_id must be 'ticker:accession:chunk_index'")
    ticker = parts[0]
    idx_raw = parts[-1]
    accession = ":".join(parts[1:-1])
    if not ticker or not accession:
        raise ValueError("chunk_id missing ticker or accession")
    idx: int | None
    if idx_raw == "-":
        idx = None
    else:
        try:
            idx = int(idx_raw)
        except ValueError:
            raise ValueError("chunk_index must be an integer or '-'")
    return ticker, accession, idx


def _edgar_url(ticker: str) -> str:
    """Best-effort EDGAR link for the filing (same shape as the chat SourceItem)."""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={ticker}&type=10-K&dateb=&owner=include&count=40"
    )


@router.get("/evidence")
def evidence(chunk_id: str):
    """Return the source excerpt + filing metadata for a graph triple's chunk."""
    try:
        ticker, accession, idx = _parse_chunk_id(chunk_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sql = (
        "SELECT text, ticker, accession, section_id, form_type, period_of_report "
        "FROM edgar_embeddings WHERE ticker = ? AND accession = ?"
    )
    params: list = [ticker, accession]
    if idx is not None:
        sql += " AND chunk_index = ?"
        params.append(idx)
    sql += " LIMIT 1"

    try:
        row = db_manager.execute(sql, params).fetchone()
    except Exception as e:
        logger.exception("evidence lookup failed")
        raise HTTPException(status_code=500, detail="evidence lookup failed") from e

    if not row:
        raise HTTPException(status_code=404, detail="no source chunk for that chunk_id")

    text, t_ticker, t_accession, section_id, form_type, period = row
    return {
        "chunk_id": chunk_id,
        "ticker": t_ticker or ticker,
        "accession": t_accession or accession,
        "section_id": section_id or "",
        "form_type": form_type or "",
        "period_of_report": period or "",
        "excerpt": text or "",
        "edgar_url": _edgar_url(t_ticker or ticker),
    }
