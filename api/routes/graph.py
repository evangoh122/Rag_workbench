"""Evidence-Graph routes (Phase C).

Click-through auditability: given a triple's ``chunk_id`` (the stable id Phase B
writes, ``ticker:accession:chunk_index``), return the source excerpt and filing
metadata so the UI can show *where in the filing* a graph edge came from.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.db.database import db_manager
from api.middleware.auth import get_read_api_key

router = APIRouter(prefix="/api/graph", tags=["graph"], dependencies=[Depends(get_read_api_key)])


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


@router.get("/analytics")
def analytics():
    """Aggregate stats for the knowledge graph: totals, relation types, entity
    types, and per-company coverage. Powers the graph-view analytics panel."""
    try:
        totals = db_manager.execute(
            "SELECT count(*), count(DISTINCT ticker), count(DISTINCT predicate), "
            "count(DISTINCT object) FROM graph_triples WHERE ticker <> ''"
        ).fetchone()
        predicates = db_manager.execute(
            "SELECT predicate, count(*) c, round(avg(confidence), 2) "
            "FROM graph_triples WHERE ticker <> '' GROUP BY predicate ORDER BY c DESC"
        ).fetchall()
        entities = db_manager.execute(
            "SELECT object_type, count(*) c FROM graph_triples "
            "WHERE ticker <> '' AND object_type IS NOT NULL AND object_type <> '' "
            "GROUP BY object_type ORDER BY c DESC"
        ).fetchall()
        per_company = db_manager.execute(
            "SELECT ticker, count(*) c, count(DISTINCT predicate) p "
            "FROM graph_triples WHERE ticker <> '' GROUP BY ticker ORDER BY c DESC"
        ).fetchall()
        xbrl_linked = db_manager.execute(
            "SELECT count(*) FROM graph_triples "
            "WHERE ticker <> '' AND (predicate = 'VERIFIED_BY' OR object_type = 'XBRL')"
        ).fetchone()
    except Exception as e:
        logger.exception("graph analytics failed")
        raise HTTPException(status_code=500, detail="graph analytics failed") from e

    t = totals or (0, 0, 0, 0)
    return {
        "totals": {
            "triples": t[0],
            "companies": t[1],
            "relation_types": t[2],
            "entities": t[3],
            "xbrl_linked": (xbrl_linked or [0])[0],
        },
        "relations": [
            {"predicate": r[0], "count": r[1], "avg_confidence": r[2]}
            for r in predicates
        ],
        "entity_types": [{"type": r[0], "count": r[1]} for r in entities],
        "per_company": [
            {"ticker": r[0], "triples": r[1], "relation_types": r[2]}
            for r in per_company
        ],
    }


@router.get("/triples")
def triples(ticker: str | None = None, limit: int = 300):
    """Return knowledge-graph triples for the dedicated Graph tab.

    Optionally filtered to one company. Capped (default 300) so the force
    graph stays legible. Highest-confidence edges first.
    """
    try:
        limit = max(1, min(int(limit), 1000))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="limit must be an integer between 1 and 1000")
    sql = (
        "SELECT subject, predicate, object, subject_type, object_type, "
        "chunk_id, source_file, source_loc, confidence, ticker "
        "FROM graph_triples WHERE ticker <> ''"
    )
    params: list = []
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    sql += " ORDER BY confidence DESC NULLS LAST LIMIT ?"
    params.append(limit)

    try:
        rows = db_manager.execute(sql, params).fetchall()
    except Exception as e:
        logger.exception("graph triples fetch failed")
        raise HTTPException(status_code=500, detail="graph triples fetch failed") from e

    return {
        "triples": [
            {
                "subject": r[0],
                "predicate": r[1],
                "object": r[2],
                "subject_type": r[3] or "",
                "object_type": r[4] or "",
                "chunk_id": r[5] or "",
                "source_file": r[6] or "",
                "source_loc": r[7] or "",
                "confidence": r[8],
                "ticker": r[9],
            }
            for r in rows
        ],
        "count": len(rows),
    }


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
