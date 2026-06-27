-- RAG Workbench — Postgres vector store (pgvector + pgvectorscale)
-- ---------------------------------------------------------------------------
-- Target host: Timescale Cloud (pgvector + pgvectorscale preinstalled) or a
-- self-hosted `timescale/timescaledb-ha` image. Plain Supabase has pgvector
-- (HNSW/IVFFlat) but NOT pgvectorscale's diskann — use HNSW there instead.
--
-- Embeddings are L2-normalised (Qwen3-Embedding-0.6B, 1024-dim), so cosine
-- distance (`<=>`, vector_cosine_ops) is the right operator.

CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;  -- pgvectorscale (diskann); harmless to skip on Supabase

-- ── Embeddings (mirrors DuckDB edgar_embeddings) ───────────────────────────
CREATE TABLE IF NOT EXISTS edgar_embeddings (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker           text         NOT NULL,
    accession        text         NOT NULL,
    text             text         NOT NULL,
    embedding        vector(1024) NOT NULL,
    updated_at       timestamptz  DEFAULT now(),
    cik              text,
    section_id       text,
    form_type        text,
    period_of_report text,
    chunk_index      int,
    section_type     text,
    content_type     text,
    -- Idempotent re-loads (matches the ETL's (ticker, accession) dedup).
    UNIQUE (ticker, accession, chunk_index)
);

-- Metadata filters used by hybrid retrieval (ticker / form scoping).
CREATE INDEX IF NOT EXISTS edgar_emb_ticker_idx     ON edgar_embeddings (ticker);
CREATE INDEX IF NOT EXISTS edgar_emb_ticker_form_idx ON edgar_embeddings (ticker, form_type);

-- ── ANN index: choose ONE (you can build, compare recall/latency, drop) ────

-- Option A — pgvectorscale StreamingDiskANN (RECOMMENDED for scale).
-- Disk-based, low RAM, millions+ of vectors, fast filtered search. Cosine.
CREATE INDEX IF NOT EXISTS edgar_emb_diskann
    ON edgar_embeddings
    USING diskann (embedding vector_cosine_ops);

-- Option B — pgvector HNSW (in-memory; great up to ~1-10M if RAM allows).
-- Use this on Supabase / where diskann is unavailable. Tune m / ef_construction.
-- CREATE INDEX IF NOT EXISTS edgar_emb_hnsw
--     ON edgar_embeddings
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- Query-time recall/latency knobs:
--   diskann:  SET diskann.query_search_list_size = 100;   -- higher = better recall
--   hnsw:     SET hnsw.ef_search = 100;
--
-- Example KNN query (top-8 chunks for a ticker, cosine):
--   SELECT id, ticker, text, 1 - (embedding <=> :qvec) AS score
--   FROM edgar_embeddings
--   WHERE ticker = :ticker
--   ORDER BY embedding <=> :qvec
--   LIMIT 8;
