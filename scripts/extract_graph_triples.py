"""
extract_graph_triples.py — Phase B: real filing-derived knowledge-graph triples.

Reads embedded filing chunks from the ``edgar_embeddings`` table and uses an LLM
to extract typed ``(subject, predicate, object)`` triples constrained to the
Evidence-Graph vocabulary (Company / Segment / Risk / Executive / Metric / XBRL).
Each triple carries source references (``chunk_id``, ``source_file``,
``source_loc``, ``confidence``) so the graph is auditable — Phase C can plumb
those refs to the UI for click-through to the source text.

This REPLACES the code-graph triples (`/graphify`, ``ticker=''``) with
per-ticker filing entities. It is idempotent: triple ids are a deterministic
hash of ``(ticker, subject, predicate, object, chunk_id)`` and inserts use
``INSERT OR IGNORE``, so re-running over the same chunks is a no-op.

Usage:
    python -m scripts.extract_graph_triples --tickers NVDA,MU
    EXTRACT_TICKERS="NVDA,MU" python -m scripts.extract_graph_triples

Design notes:
    * Single-writer DuckDB — do NOT run this while the embed ETL holds a write
      connection to the same DB file (they will lock-conflict). Run after embed.
    * Best-effort per chunk: any LLM/parse failure yields zero triples for that
      chunk and is logged, never raised.
    * Cost bounded by MAX_CHUNKS_PER_FILING / MAX_TRIPLES_PER_CHUNK and a
      MIN_CONFIDENCE floor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Dict, List, Optional

import duckdb
from loguru import logger

# ---------------------------------------------------------------------------
# Vocabulary & tuning knobs
# ---------------------------------------------------------------------------

# Allowed node types (the Evidence-Graph brief vocabulary). A triple is dropped
# if either endpoint's type is not in this set.
NODE_TYPES = {"Company", "Segment", "Risk", "Executive", "Metric", "XBRL", "Product", "Geography"}

# Recommended predicate vocabulary (the model is nudged toward these; predicates
# are normalised to UPPER_SNAKE but not hard-rejected, to preserve signal).
PREDICATES = (
    "HAS_SEGMENT", "FACES_RISK", "LED_BY", "HAS_EXECUTIVE", "REPORTS_METRIC",
    "OPERATES_IN", "COMPETES_WITH", "DEPENDS_ON", "OFFERS_PRODUCT", "VERIFIED_BY",
)

MIN_CONFIDENCE = float(os.getenv("GRAPH_MIN_CONFIDENCE", "0.5"))
MAX_TRIPLES_PER_CHUNK = int(os.getenv("GRAPH_MAX_TRIPLES_PER_CHUNK", "8"))
MAX_CHUNKS_PER_FILING = int(os.getenv("GRAPH_MAX_CHUNKS_PER_FILING", "40"))

_DEFAULT_DB_PATH = os.getenv("DB_PATH", "./data/rag.duckdb")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS graph_triples (
    id           VARCHAR PRIMARY KEY,
    ticker       VARCHAR NOT NULL DEFAULT '',
    subject      VARCHAR NOT NULL,
    predicate    VARCHAR NOT NULL,
    object       VARCHAR NOT NULL,
    confidence   DOUBLE  DEFAULT 1.0,
    source_file  VARCHAR,
    source_loc   VARCHAR,
    subject_type VARCHAR,
    object_type  VARCHAR,
    chunk_id     VARCHAR
)
"""

# Idempotent migrations for DBs created before Phase B added the typed columns.
ALTER_STMTS = (
    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS subject_type VARCHAR",
    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS object_type  VARCHAR",
    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS chunk_id     VARCHAR",
)

CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_gt_ticker_subj ON graph_triples (ticker, subject)",
    "CREATE INDEX IF NOT EXISTS idx_gt_chunk ON graph_triples (chunk_id)",
)

INSERT_SQL = """
INSERT OR IGNORE INTO graph_triples
    (id, ticker, subject, predicate, object, confidence,
     source_file, source_loc, subject_type, object_type, chunk_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the graph_triples table and migrate older schemas (idempotent)."""
    conn.execute(CREATE_TABLE_SQL)
    for stmt in ALTER_STMTS:
        try:
            conn.execute(stmt)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Schema alter skipped (may already exist): {e}")
    for stmt in CREATE_INDEX_SQL:
        try:
            conn.execute(stmt)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Index create skipped: {e}")


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def make_chunk_id(ticker: str, accession: str, chunk_index: Optional[int]) -> str:
    """Stable id for a chunk row in edgar_embeddings.

    edgar_embeddings has no surrogate key, but (ticker, accession, chunk_index)
    is unique per row. Phase C's evidence route parses this back to fetch the
    source text. Uses '-' for a missing chunk_index so the id stays well-formed.
    """
    idx = "-" if chunk_index is None else str(chunk_index)
    return f"{ticker}:{accession}:{idx}"


def triple_id(ticker: str, subject: str, predicate: str, obj: str, chunk_id: str) -> str:
    """Deterministic id so re-runs dedupe by content rather than appending."""
    key = "\x1f".join([ticker, subject.lower(), predicate.lower(), obj.lower(), chunk_id])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _normalise_predicate(pred: str) -> str:
    """Normalise a predicate to UPPER_SNAKE_CASE."""
    cleaned = "".join(c if c.isalnum() else " " for c in pred).strip()
    return "_".join(cleaned.upper().split()) or "RELATED_TO"


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You extract a knowledge graph from SEC filing text. Read the passage and "
    "return typed (subject, predicate, object) triples describing relationships "
    "between business entities. "
    "Allowed node types (use EXACTLY these strings for subject_type/object_type): "
    + ", ".join(sorted(NODE_TYPES)) + ". "
    "Prefer these predicates when they fit: " + ", ".join(PREDICATES) + ". "
    "Rules: only extract relationships explicitly supported by the passage; do "
    "NOT invent entities or numbers; keep subjects/objects short noun phrases "
    "(the entity name, not a sentence); skip boilerplate. "
    "Respond with STRICT JSON only, no markdown, of the form: "
    '{"triples": [{"subject": str, "subject_type": str, "predicate": str, '
    '"object": str, "object_type": str, "confidence": number}]}. '
    "confidence is 0..1 (your certainty the relationship is stated in the text). "
    "Return an empty list if the passage has no extractable relationships."
)


def _make_client():
    """Build the OpenAI client from the active provider config (mirrors Phase A)."""
    from openai import OpenAI
    from api.config import Config

    cfg = Config.get_provider_config()
    client = OpenAI(api_key=cfg["api_key"] or "local", base_url=cfg["base_url"], timeout=30.0)
    return client, cfg["model"]


def extract_triples_from_chunk(
    text: str,
    ticker: str,
    client,
    model: str,
) -> List[Dict]:
    """Extract validated triples from one chunk of filing text.

    Best-effort: returns [] on any LLM/parse failure. Triples are validated
    against NODE_TYPES, confidence-clamped, MIN_CONFIDENCE-filtered, and capped
    at MAX_TRIPLES_PER_CHUNK.
    """
    text = (text or "").strip()
    if not text:
        return []
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Company ticker: {ticker}\n\nPassage:\n{text[:6000]}"},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else raw
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"Triple extraction failed for {ticker} chunk (non-fatal): {e}")
        return []

    candidates = data.get("triples") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        return []

    out: List[Dict] = []
    for t in candidates:
        if not isinstance(t, dict):
            continue
        subject = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()
        predicate = str(t.get("predicate", "")).strip()
        subject_type = str(t.get("subject_type", "")).strip()
        object_type = str(t.get("object_type", "")).strip()
        if not subject or not obj or not predicate:
            continue
        # Constrain node types to the Evidence-Graph vocabulary.
        if subject_type not in NODE_TYPES or object_type not in NODE_TYPES:
            continue
        try:
            confidence = float(t.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if confidence < MIN_CONFIDENCE:
            continue
        out.append({
            "subject": subject[:255],
            "predicate": _normalise_predicate(predicate)[:64],
            "object": obj[:255],
            "subject_type": subject_type,
            "object_type": object_type,
            "confidence": confidence,
        })
        if len(out) >= MAX_TRIPLES_PER_CHUNK:
            break
    return out


# ---------------------------------------------------------------------------
# Chunk fetch / persistence
# ---------------------------------------------------------------------------

def fetch_chunks(conn: duckdb.DuckDBPyConnection, ticker: str, limit: int) -> List[Dict]:
    """Fetch narrative chunks for a ticker from edgar_embeddings.

    Returns the most informative chunks first (longest narrative text), capped
    at ``limit`` to bound extraction cost per filing. Table chunks are skipped —
    relationships come from prose, not number grids.
    """
    rows = conn.execute(
        """
        SELECT text, accession, section_id, chunk_index, form_type, period_of_report
        FROM edgar_embeddings
        WHERE ticker = ?
          AND COALESCE(content_type, 'narrative') <> 'table'
          AND text IS NOT NULL
        ORDER BY length(text) DESC
        LIMIT ?
        """,
        [ticker, limit],
    ).fetchall()
    return [
        {
            "text": r[0],
            "accession": r[1] or "",
            "section_id": r[2] or "",
            "chunk_index": r[3],
            "form_type": r[4] or "",
            "period_of_report": r[5] or "",
        }
        for r in rows
    ]


def persist_triples(conn: duckdb.DuckDBPyConnection, rows: List[Dict]) -> int:
    """Insert triple rows (INSERT OR IGNORE on deterministic id). Returns count attempted."""
    for r in rows:
        conn.execute(INSERT_SQL, [
            r["id"], r["ticker"], r["subject"], r["predicate"], r["object"],
            r["confidence"], r["source_file"], r["source_loc"],
            r["subject_type"], r["object_type"], r["chunk_id"],
        ])
    return len(rows)


def link_xbrl_metrics(conn: duckdb.DuckDBPyConnection, ticker: str) -> int:
    """Add ``Metric -VERIFIED_BY-> XBRL`` edges by matching extracted Metric nodes
    to filed XBRL concepts for the same ticker.

    Best-effort and bounded: matches a Metric label to an XBRL concept by simple
    case-insensitive substring on the alphanumeric stem (e.g. "gross margin" ↔
    "GrossProfit" won't match, but "revenue" ↔ "Revenues" will). Skips silently
    if xbrl_facts is absent. Returns number of VERIFIED_BY edges inserted.
    """
    try:
        concepts = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT concept FROM xbrl_facts WHERE ticker = ? AND concept IS NOT NULL",
                [ticker],
            ).fetchall()
        ]
    except Exception as e:
        logger.debug(f"link_xbrl_metrics: xbrl_facts unavailable for {ticker}: {e}")
        return 0
    if not concepts:
        return 0

    metric_rows = conn.execute(
        """
        SELECT DISTINCT subject, subject_type, chunk_id, source_file, source_loc FROM graph_triples
        WHERE ticker = ? AND subject_type = 'Metric'
        UNION
        SELECT DISTINCT object AS subject, object_type AS subject_type, chunk_id, source_file, source_loc
        FROM graph_triples WHERE ticker = ? AND object_type = 'Metric'
        """,
        [ticker, ticker],
    ).fetchall()

    def _stem(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())

    concept_stems = {c: _stem(c) for c in concepts}
    inserted = 0
    for metric, _, chunk_id, source_file, source_loc in metric_rows:
        mstem = _stem(metric)
        if len(mstem) < 4:
            continue
        for concept, cstem in concept_stems.items():
            if mstem in cstem or cstem in mstem:
                tid = triple_id(ticker, metric, "VERIFIED_BY", concept, chunk_id or "")
                conn.execute(INSERT_SQL, [
                    tid, ticker, metric, "VERIFIED_BY", concept, 1.0,
                    source_file, source_loc, "Metric", "XBRL", chunk_id,
                ])
                inserted += 1
                break
    return inserted


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_extract_graph_triples(
    tickers: List[str],
    db_path: Optional[str] = None,
    max_chunks_per_filing: int = MAX_CHUNKS_PER_FILING,
    client=None,
    model: Optional[str] = None,
) -> int:
    """Extract and persist filing-derived triples for the given tickers.

    Returns the total number of triples inserted (attempted). Opens its own
    DuckDB connection (read-write) — caller must ensure no other writer holds
    the DB. ``client``/``model`` are injectable for tests.
    """
    db_path = db_path or _DEFAULT_DB_PATH
    if client is None:
        client, model = _make_client()
    assert model is not None, "model must be provided when passing an explicit client"

    conn = duckdb.connect(db_path)
    try:
        ensure_schema(conn)
        total = 0
        for ticker in tickers:
            ticker = ticker.strip().upper()
            if not ticker:
                continue
            chunks = fetch_chunks(conn, ticker, max_chunks_per_filing)
            if not chunks:
                logger.warning(f"{ticker}: no chunks in edgar_embeddings — skipping")
                continue
            logger.info(f"{ticker}: extracting triples from {len(chunks)} chunks")
            rows: List[Dict] = []
            for ch in chunks:
                chunk_id = make_chunk_id(ticker, ch["accession"], ch["chunk_index"])
                triples = extract_triples_from_chunk(ch["text"], ticker, client, model)
                for tr in triples:
                    rows.append({
                        "id": triple_id(ticker, tr["subject"], tr["predicate"], tr["object"], chunk_id),
                        "ticker": ticker,
                        "subject": tr["subject"],
                        "predicate": tr["predicate"],
                        "object": tr["object"],
                        "confidence": tr["confidence"],
                        "source_file": ch["accession"],
                        "source_loc": ch["section_id"],
                        "subject_type": tr["subject_type"],
                        "object_type": tr["object_type"],
                        "chunk_id": chunk_id,
                    })
            inserted = persist_triples(conn, rows)
            linked = link_xbrl_metrics(conn, ticker)
            conn.commit()
            logger.info(f"{ticker}: inserted {inserted} triples (+{linked} XBRL links)")
            total += inserted + linked
        return total
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_tickers(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract filing-derived knowledge-graph triples")
    parser.add_argument("--tickers", default=os.getenv("EXTRACT_TICKERS", ""),
                        help="Comma/space-separated tickers (or set EXTRACT_TICKERS)")
    parser.add_argument("--db-path", default=_DEFAULT_DB_PATH, help="Path to DuckDB file")
    parser.add_argument("--max-chunks", type=int, default=MAX_CHUNKS_PER_FILING,
                        help="Max chunks per ticker to extract from")
    args = parser.parse_args()

    tickers = _parse_tickers(args.tickers)
    if not tickers:
        print("No tickers given. Use --tickers NVDA,MU or set EXTRACT_TICKERS.", file=sys.stderr)
        sys.exit(2)

    n = run_extract_graph_triples(tickers, db_path=args.db_path, max_chunks_per_filing=args.max_chunks)
    print(f"[extract_graph_triples] Done — {n} triples inserted across {len(tickers)} ticker(s)")
