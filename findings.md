# CI Abstention Findings — RAG Pipeline Returns `sources=0` for All Tickers

**Date:** 2026-06-13
**Branch:** `fix/ci-validation-abstention`
**Symptom:** `scripts/rag_pipeline_ci.py` → 30/31 FAIL with `abstention (0 sources)`; MU/NVDA intermittently `HTTP 502`.

---

## Root Cause

The CI tests the **deployed HF Space**, not localhost (the 502s come from `nginx/1.26.3`). On the Space, retrieval returns zero documents for every ticker because the `edgar_embeddings` table is empty, and the only fallback (live SEC fetch) is blocked from the Space's cloud IP.

### Causal chain
```
EMBEDDING_DIM unset → Space uses 4096 (Qwen default)        ─┐
data/ not shipped → Space starts with empty DB              ─┤→ relies 100% on HF embedding at startup
Qwen3-Embedding-8B unreliable on HF serverless (403/404/502) ─┘
        ↓
/api/admin/embed-data stores 0 chunks → edgar_embeddings EMPTY
        ↓
vector_search → []   AND   BM25 (reads same table) → []
        ↓
fallback chunk_filing_sections → SEC blocks Space IP → []
        ↓
retrieved_docs = []  →  sources=0  →  abstention   ×31
```

---

## Confirmed Evidence

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **Populated DB never ships to the Space** | `data/` is gitignored (`.gitignore:2`); `data/rag.duckdb` not tracked by git; deploy is `git push hf main` (`deploy.yml:80`); Dockerfile `RUN mkdir -p /app/data` creates it empty. Local 33,717 vectors do not exist on Space. |
| 2 | **`EMBEDDING_PROVIDER` + `HF_TOKEN` are set, but `EMBEDDING_DIM` is NOT** | `deploy.yml:58-60` syncs `EMBEDDING_PROVIDER=huggingface`, `HF_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B`, `HF_TOKEN`. No `EMBEDDING_DIM` upload → Space defaults to **4096** (`config.py:147`). Self-consistent if Qwen works, but Space can never reuse 768-dim data. |
| 3 | **Single fragile dependency: Qwen3-Embedding-8B over HF serverless** | Both embed-time (`/api/admin/embed-data`) and query-time (`vector_search`) call HF inference. Git history shows the ongoing failure: `scaleway routing`, `403`, `force hf-inference provider`, `bypass InferenceClient`. 8B embedding models are frequently unserved (404/503) on HF free tier. |
| 4 | **BM25 also dies when the table is empty** | `_load_bm25_index` (`hybrid_retriever.py`) builds from `SELECT ticker, text, accession FROM edgar_embeddings`. Empty table → empty lexical leg too. So vector failure alone wouldn't cause 0 sources — the **table itself is empty**. |
| 5 | **Live-fetch fallback can't save it on the Space** | `chunk_filing_sections` (`sec_client.py:58`) does a live `edgar.Company(ticker).get_filings(...)`. SEC blocks the Space's cloud IP (reason for existing edgartools-fallback + 502 commits). |
| 6 | **502s = Space OOM** | Loading a ~16GB+ 8B embedding model plus the cross-encoder reranker on a small Space instance crashes the worker; nginx returns 502 (seen for MU, NVDA). |

### Local state (for contrast)
```
edgar_embeddings: 33717   (all 768-dim, embedded with nomic-embed-text via Ollama)
ticker_embeddings: 16
xbrl_facts: 10420
polygon_tickers: 16
```
Local retrieval works; the Space does not — the gap is the empty Space index.

---

## Verify in One Call
```bash
curl -s "$SPACE_URL/api/stats" | python -m json.tool
```
- `data.edgar_embeddings: 0` → confirms empty-index root cause.
- `config.embedding_dim: 4096` → confirms `EMBEDDING_DIM` is unset/defaulted.
- `llm.recent_errors` showing HF 403/404/503 → confirms Qwen-on-HF is the failure point.

---

## Fixes (in order of leverage)

1. **Stop depending on HF serverless for an 8B model.** Switch `HF_EMBEDDING_MODEL` to a small model HF actually serves, **or** run embeddings locally in-process via `sentence-transformers` (already a dependency). Removes the 403/OOM/502 failure surface entirely. Candidates: `BAAI/bge-small-en-v1.5` (384-dim), `sentence-transformers/all-MiniLM-L6-v2` (384-dim).
2. **Set `EMBEDDING_DIM` to match the chosen model** as a synced secret in `deploy.yml`. Currently implicit.
3. **Ship a prebuilt index instead of embedding at cold start.** Commit `data/rag.duckdb` via Git LFS (deploy already uses `lfs: true`) or bake into the image. Embedding 31 filings at every cold start is what's failing/OOM-ing.
4. **BM25-only degraded mode is valid.** BM25 needs no embeddings; if `edgar_embeddings.text` were populated by a non-vector path, lexical retrieval alone would return sources.

---

## Chosen Remediation (this change)

Swap to an embedding model run **locally in-process** via `sentence-transformers` (no HF inference API), and set `EMBEDDING_DIM` consistently end-to-end.

- Model: `Qwen/Qwen3-Embedding-0.6B` (1024-dim) — runs in-process on the Space without OOM (the 8B variant OOMs; HF serverless is unreliable for large models), no external inference call. Uses a query-side instruction prefix; documents embedded as-is.
- `config.py`: add a `sentence-transformers` local provider; `EMBEDDING_DIM` defaults per provider (local=1024); add `ACTIVE_EMBEDDING_MODEL` for truthful telemetry.
- `embeddings.py`: add a `LocalSTEmbeddings` backend.
- `requirements.txt`: pin `transformers>=4.51.0` (Qwen3 architecture support).
- `deploy.yml`: sync `EMBEDDING_PROVIDER` / `ST_EMBEDDING_MODEL` / `EMBEDDING_DIM` / `EMBEDDING_QUERY_PREFIX` consistently.
