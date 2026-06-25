# Additional Filings Ingestion Plan: +1 Year Annual (10-K / 20-F) + 1 Quarter (10-Q)

Status: **DRAFT — not yet executed**
Created: 2026-06-22
Owner: Evan Goh

---

## Goal

For the companies that **already have filings embedded** in the corpus, broaden
historical coverage by adding:

1. **One additional (prior) year of the annual report** — `10-K` for domestic
   filers, `20-F` for foreign private issuers (STM, TSM). Target = the **2 most
   recent** annual filings per ticker; the latest is usually already present, so
   this effectively backfills the prior year.
2. **One quarter of `10-Q`** — the single most recent `10-Q` per domestic filer.

**Execution order (per user): 10-K / 20-F FIRST, then 10-Q as a second pass.**

Scope is the **existing 34 tickers only** (companies with filings already in the
DB). Backfilling the other 64 not-yet-ingested tickers is a separate effort
(see `scripts/ingest_missing.py` precedent) and is out of scope here.

---

## ✅ Step 0 — reconcile with Hugging Face (RESOLVED 2026-06-22)

> "I think we downloaded half of the 10-k / 20-f and placed them on Hugging Face
> already."

**Finding: local `./data/rag.duckdb` is a strict superset of the HF production
corpus.** No pull/merge from HF needed; local is the source of truth.

Diff of `edgar_embeddings` by `(ticker, form_type, accession)`:

| | Filings | Tickers |
|---|---|---|
| Local `rag.duckdb` | 45 | 34 |
| HF `egoh33/Rag-workbench` | 42 | 34 |

- Filings on HF but **missing locally: 0**.
- Filings local has that HF lacks: **3** — `NVDA` 10-K 2025, `QCOM` 10-K 2024,
  `TXN` 10-K 2025 (prior-year backfills done locally, never uploaded).
- The partial prior-year backfill *was* pushed to HF for **ADI, AMD, AVGO, INTC,
  MU**; NVDA/QCOM/TXN stayed local-only.

**Implication:** proceed with local as the base. At the end (Step 8), push
local → HF so the 3 local-only filings (plus all new ingestion) land on the Space.
HF comparison copy downloaded to `./data/_hf_compare/rag.duckdb` (gitignore/clean
up later).

---

## Current local inventory (verified 2026-06-22)

- DB: `./data/rag.duckdb`, written in **DuckDB 1.5.x** storage format.
  - Readable/writable only by `.venv` (duckdb 1.5.3). `.venv_duck10` (1.0.0)
    **cannot** read it (`SerializationException`).
- `edgar_embeddings`: 34 distinct tickers, all vectors **1024-dim**.
  - `10-K`: 31 tickers · `20-F`: 2 (STM, TSM) · `424B4`: 1 (SPCX) · `10-Q`: 1 (MU)
- Tickers already holding **2 years** of annual (no annual backfill needed):
  ADI, AMD, AVGO, INTC, MU, NVDA, QCOM, TXN.
- **MU** already has 3× `10-Q` (no 10-Q backfill needed).
- **KLAC** `10-K` (2025) has only **1 chunk** — looks broken/partial. Dedup by
  accession means this run will **not** repair it; flag separately.
- **SPCX** is IPO-only (`424B4`); no prior-year annual exists — **skip** for the
  annual pass. (May now have a `10-Q`; pick up in the 10-Q pass.)

---

## Environment (verified)

| Item | Value |
|---|---|
| Python / DB write env | `.venv` → `D:\New folder (2)\Rag_workbench\.venv\Scripts\python.exe` (duckdb 1.5.3) |
| Embedding model | `Qwen/Qwen3-Embedding-0.6B` via local `sentence-transformers` (in-process, CPU) |
| Embedding dim | **1024** (matches existing corpus) |
| Model cache | Present at `~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-0.6B` (no download) |
| EDGAR identity | `EDGAR_USER_AGENT="Evan Goh evangohsg@gmail.com"` (from `.env`) |
| Filing fetch | `edgartools` (`edgar.Company`) — works from this host; SEC REST API |
| torch | 2.12.1 **CPU only** (no CUDA) → embedding is the slow step |

---

## Data conventions to preserve (match existing rows exactly)

These were reverse-engineered from existing rows; deviating will break dedup or
create inconsistent data:

- **`accession`** stored **with dashes**, e.g. `0000006281-25-000153`
  (use `filing.accession_number` directly — do NOT strip dashes).
- **`period_of_report`** = `20{YY}-12-31` where `YY` = middle segment of the
  accession (e.g. `…-24-…` → `2024-12-31`). This is the existing fallback
  convention, not the true fiscal year-end. Reproduce it for consistency.
- **Dedup**: `DELETE`/skip on `(ticker, accession)` before insert so re-runs are
  idempotent and already-present years are no-ops.
- **Chunking**: `StructureChunker(max_chunk_size=1500, min_chunk_size=200,
  similarity_threshold=0.15)`; sections via `_extract_sections_with_labels`
  (10-K Item 1/1a/7/7a/8; 20-F falls back to full-text — same path that produced
  the existing STM/TSM rows).
- **Provenance header** per chunk:
  `[TICKER:X | SECTION:s | PERIOD:p | FORM:f]` (as in `embed_edgar.py`).
- **Columns**: `ticker, accession, text, embedding, updated_at, cik, section_id,
  form_type, period_of_report, chunk_index, section_type, content_type`.

---

## Why a new driver (not the existing ETL)

`scripts/embed_edgar.py::run_embed_edgar_etl()` fetches only **one** filing per
ticker (first hit walking `["10-K","20-F","10-Q","424B4","S-1/A","S-1"]`) and has
no `form_types`/recency parameter. It is also deploy-critical (called by
`seed_on_startup`). Rather than alter it, add a standalone driver
`scripts/embed_additional.py` that:

- Imports helpers from `embed_edgar.py` (`parse_html_file`,
  `_extract_period_of_report`, `_extract_sections_with_labels`,
  `_ensure_schema`, `_TICKER_CIK`, `StructureChunker`) and `get_embeddings()`.
- Resolves specific filings via `edgartools`:
  `Company(ticker).get_filings(form=F).latest(2)` for annual,
  `.latest(1)` for `10-Q` (index 0 = newest, verified).
- Writes `filing.text()` to disk, parses → chunks → embeds → inserts, skipping
  any `accession` already present.

---

## Implementation steps

### Step 0 — Reconcile with HF (BLOCKING)
Pull `egoh33/Rag-workbench/rag.duckdb`, diff against local, merge so local
reflects production. Recompute the genuinely-missing filing list.

### Step 1 — Write `scripts/embed_additional.py`
Driver as described above. Flags:
- `--forms annual` (default) → `10-K` + `20-F`, `latest(2)`
- `--forms 10-Q` → `10-Q`, `latest(1)`
- `--dry-run` → print planned fetches + skips, no writes
- `--tickers A,B,C` → optional subset (default = the 34 existing tickers)

### Step 2 — Dry run (annual)
`python scripts/embed_additional.py --forms annual --dry-run`
Review: each ticker → which accession(s) would be fetched vs skipped (already
present). Expect no-ops for ADI/AMD/AVGO/INTC/MU/NVDA/QCOM/TXN; skip SPCX.

### Step 3 — Execute annual pass (10-K / 20-F)
`python scripts/embed_additional.py --forms annual`
Run with `.venv` python. Log to `embed_additional_annual.log`.

### Step 4 — Verify annual
Per ticker: confirm 2 annual accessions now present; chunk counts sane (>50,
flag <10 like KLAC). Confirm all new vectors are 1024-dim.

### Step 5 — Execute 10-Q pass
`python scripts/embed_additional.py --forms 10-Q`
Log to `embed_additional_10q.log`. (20-F filers + SPCX expected to no-op.)

### Step 6 — Verify 10-Q + full corpus sanity
Counts by `(ticker, form_type)`; spot-check provenance headers and periods.

### Step 7 — Rebuild DB in DuckDB 1.0.0 format for the Space
The Space cannot read the 1.5.x format (CONSTRAINT: storage-format mismatch).
Export/rebuild to 1.0.0 (`.venv_duck10`) before upload.

### Step 8 — Upload to HF + deploy
Upload `rag.duckdb` to `egoh33/Rag-workbench` (public corpus). Deploy via
`git push origin <branch>:main` to rebuild the Space; verify via `/api/stats`
(the `embed-data` verify step in `deploy.yml` is flaky — trust `/api/stats`).

---

## Risks / notes

- **CPU embedding is slow.** ~31 prior-year 10-Ks + ~31 10-Qs ≈ up to ~62
  filings × hundreds of chunks each. Expect a long run; consider batching.
- **DB lock.** Ensure no local server/ETL holds the write lock during ingestion.
- **Don't write the Space DB in 1.5.x.** Always convert to 1.0.0 before upload.
- **KLAC broken 10-K** (1 chunk) is not fixed by this plan — track separately.
- **Local↔HF divergence** is the biggest correctness risk — Step 0 must come first.

---

## Acceptance criteria

- [ ] Local DB reconciled with HF production corpus (Step 0).
- [ ] Every eligible domestic ticker has **2** annual (`10-K`) accessions.
- [ ] STM, TSM have **2** `20-F` accessions.
- [ ] Every eligible domestic ticker has **≥1** `10-Q` accession.
- [ ] All new vectors are 1024-dim; accession/period conventions preserved.
- [ ] DB rebuilt in 1.0.0 format, uploaded, Space healthy via `/api/stats`.
