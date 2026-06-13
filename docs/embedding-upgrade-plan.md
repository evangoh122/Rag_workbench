# Embedding Upgrade Plan: Ollama → Fin-E5

## Context

Current state: `nomic-embed-text` via Ollama (768-dim, general-purpose) or `Qwen/Qwen3-Embedding-8B` via HuggingFace (4096-dim, general multilingual). Neither is finance-adapted.

Target state: Fin-E5 (finance-domain embedding) as primary model, wired into a cascading retrieval pipeline.

---

## Gap Analysis (current vs. best practices)

### 1. Handling Tables and Numbers

| Sub-criterion | Status | Issue |
|---|---|---|
| Avoid embedding raw numerical data | Partial | Table chunks detected by `StructureChunker` and tagged `content_type="table"` are still passed to `embed_documents()` — the tag is never used to skip them |
| Layout-aware parsers (Docling/Marker) | Missing | Parsing is BeautifulSoup + custom regex only |
| Hybrid storage (structured → SQL, unstructured → vectors) | Partial | XBRL/Polygon → SQL correctly. Table chunks from filings → vectors (should be SQL) |

### 2. Selecting Embedding Models

| Sub-criterion | Status | Issue |
|---|---|---|
| Domain-specific finance embedding | Missing | Using general-purpose nomic-embed-text or Qwen3 |
| Finance-adapted reranker | Missing | `ms-marco-MiniLM-L-6-v2` trained on web passages, not financial text |
| FinMTEB benchmarking | Missing | No benchmark evaluation wired anywhere |

### 3. Chunking & Metadata Enrichment

| Sub-criterion | Status | Issue |
|---|---|---|
| Tables kept intact as single chunks | Done | `StructureChunker` detects and emits table regions as single chunks |
| Merged cells / header normalization | Missing | BeautifulSoup `get_text()` flattens HTML, losing `<th>` and merged cell structure |
| Metadata enrichment on chunks | Done | ticker, section_label, period_of_report, form_type, content_type all stored |
| Date filtering at retrieval time | Missing | `period_of_report` stored but never used in retrieval WHERE clauses |
| Semantic chunking by section headers | Done | Item 1/1a/7/7a/8 extracted; Jaccard-similarity sentence grouping within sections |

### 4. Semantic Search vs. Lexicon Baseline

| Sub-criterion | Status | Issue |
|---|---|---|
| Hybrid search (dense + BM25) | Done | `EDGARHybridRetriever` runs BM25 + vector + RRF fusion |
| Loughran-McDonald lexicon baseline | Missing | No financial lexicon anywhere in the project |

---

## Recommended Architecture: Cascading Pipeline

Your existing setup already has the scaffolding. Fin-E5 slots into the middle stage:

```
Query → BM25 (fast lexical, top-k×5) ──┐
                                         ├→ RRF → Cross-encoder reranker → LLM
Query → Fin-E5 vector (semantic, top-k×5) ──┘
```

This is better than Parallel Vectors (two simultaneous embedding models) for now because:
- No schema changes required beyond dim update
- Fin-E5 alone covers the biggest quality gap (domain specificity)
- Parallel Vectors can be added later as a second column once Fin-E5 quality is validated

---

## Implementation Steps

### Step 1 — Verify Fin-E5 model ID and dimension
Before writing any code, check the **FinMTEB leaderboard** for the exact HuggingFace model ID.
Confirm:
- Model is available on HF Inference API (or runnable locally via `sentence-transformers`)
- Output dimension (likely 768 or 1024)

Candidate models to evaluate on FinMTEB:
- `BAAI/bge-en-icl`
- `Linq-AI-Research/Linq-Embed-Mistral`
- Any `fin-e5` tagged model on HuggingFace

### Step 2 — Update `.env`
```env
EMBEDDING_PROVIDER=huggingface
HF_EMBEDDING_MODEL=<fin-e5-model-id>
EMBEDDING_DIM=768                      # match Fin-E5 actual output dim
```

### Step 3 — Remove Ollama code path (embeddings.py + requirements.txt)

**3a. `requirements.txt`**
```diff
- langchain-ollama>=0.2.0,<0.3.0
- ollama>=0.4.0,<0.5.0
```

**3b. `api/services/embeddings.py`** — delete the entire Ollama code path:
- Remove `from langchain_ollama import OllamaEmbeddings` (line 3)
- Remove `PrefixedOllamaEmbeddings` class (lines 7-13)
- Remove `is_ollama_available()` function (lines 60-76)
- Remove `_ollama_available` global + Ollama branch from `get_embeddings()` (lines 57-58, 102-116)
- `get_embeddings()` becomes: if provider is "huggingface" → `HFInferenceEmbeddings`, else → log error + return None

### Step 4 — Skip table chunks during embedding (`scripts/embed_edgar.py` ~line 507)
Table chunks embed poorly (dense numbers confuse vector space). Skip them during ingestion:

```python
for i in range(0, len(all_chunks), batch_size):
    batch = all_chunks[i: i + batch_size]
    narrative_batch = [c for c in batch if c.metadata.content_type != "table"]
    if not narrative_batch:
        continue
    batch_texts = [c.text for c in narrative_batch]
    vecs = model.embed_documents(batch_texts)

    for j, chunk in enumerate(narrative_batch):   # iterate narrative_batch, not batch
        conn.execute("""
            INSERT INTO edgar_embeddings
                (ticker, accession, text, embedding, updated_at,
                 cik, section_id, form_type, period_of_report, chunk_index,
                 section_type, content_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ticker, accession, chunk.text, vecs[j], ts,
            cik,
            chunk.metadata.section_label,
            form_type,
            period_of_report,
            chunk.metadata.chunk_index,
            chunk.metadata.section_type,
            chunk.metadata.content_type,
        ])

    total_chunks_stored += len(narrative_batch)
```

Key fix: iterate `narrative_batch`, not `batch`, so `vecs[j]` aligns with the correct chunk.

### Step 5 — Widen cascade recall in `hybrid_retriever.py` (line 306-307)
Give the cross-encoder reranker more candidates to evaluate:
```python
# was top_k * 2
bm25_docs = bm25_search(query, top_k=self.top_k * 5, ...)
vec_docs  = vector_search(query, top_k=self.top_k * 5, ...)
```

### Step 6 — Recreate embedding tables and re-run ETL
The dimension is baked into the DuckDB column type (`FLOAT[768]` vs `FLOAT[4096]`) and cannot be altered in place:
```sql
DROP TABLE edgar_embeddings;
DROP TABLE ticker_embeddings;
```

Then re-run **in order** (ticker_embeddings holds both metadata AND vectors):
```
POST /api/admin/refresh-data          # restores xbrl_facts + ticker_embeddings metadata
python scripts/embed_edgar.py         # restores edgar_embeddings with Fin-E5 vectors
python scripts/embed_tickers.py       # restores ticker_embeddings vectors (metadata already present)
```

**Important:** DROP TABLE ticker_embeddings also destroys ticker metadata (descriptions, sectors, industries) inserted by `refresh-data`. The re-run order above restores metadata first via refresh-data, then vectors via embed_tickers. The `ON CONFLICT DO UPDATE` in embed_tickers.py ensures vectors are upserted into existing metadata rows without clobbering description/sector/industry.

### Step 7 — Wire ticker embeddings into startup seed (`scripts/seed_on_startup.py`)
`embed_tickers.py` is CLI-only — never runs at container startup. The ticker vector retriever (`DuckDBVectorRetriever`) will find 0 embeddings unless manually invoked. Add a third step to the seed script:

```python
# After the existing embed-data step (~line 89), add:
# ── Step 3: Embed ticker descriptions into ticker_embeddings ────────────
logger.info("Triggering ticker embedding job...")
try:
    from scripts.embed_tickers import run_embed_tickers_etl
    ticker_count = run_embed_tickers_etl()
    logger.info(f"Ticker embedding complete — {ticker_count} tickers")
except Exception as e:
    logger.error(f"Ticker embedding failed: {e}")
```

### Step 8 — Verify tests pass
```bash
pytest tests/test_hybrid_retriever.py tests/test_rag_engine.py
```
The public interface (`embed_query`, `embed_documents`) does not change, so all existing tests should pass.

---

## What to defer

| Pattern | When to tackle |
|---|---|
| **Parallel Vectors** (Fin-E5 + Qwen3 simultaneously) | After Fin-E5 quality is validated — requires adding a second embedding column and doubling ETL time |
| **Parent-Child chunking** | Separate project — requires chunker and schema changes |
| **Finance cross-encoder reranker** | Swap `ms-marco-MiniLM-L-6-v2` after Fin-E5 recall quality is confirmed |
| **Loughran-McDonald lexicon** | Add to BM25 tokenizer as a follow-on improvement |
| **Docling/Marker layout parser** | Replace BeautifulSoup ingestion in a dedicated ingestion upgrade phase |
| **Date filtering at retrieval** | Add `WHERE period_of_report >= ?` to `hybrid_retriever.py` vector queries once re-indexing is done |

---

## Files touched

| File | Change |
|---|---|
| `.env` | `EMBEDDING_PROVIDER`, `HF_EMBEDDING_MODEL`, `EMBEDDING_DIM` |
| `requirements.txt` | Remove `langchain-ollama`, `ollama` |
| `api/services/embeddings.py` | Remove `PrefixedOllamaEmbeddings`, `is_ollama_available()`, Ollama branch in `get_embeddings()` |
| `scripts/embed_edgar.py` | Skip `content_type="table"` chunks before calling `embed_documents()` |
| `api/services/hybrid_retriever.py` | Widen `top_k * 2` → `top_k * 5` for cascade recall |
| `scripts/seed_on_startup.py` | Add ticker embedding step after filing embedding |
| DuckDB | Drop and recreate `edgar_embeddings`, `ticker_embeddings` |
