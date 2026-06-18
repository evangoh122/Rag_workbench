# SEC Sentiment & Management Tone Analysis — Implementation Plan

> Status: **Implemented** — all 4 phases complete. Branch: `gemini`. Authored 2026-06-18, implemented 2026-06-18.
> Sources: "SEC Sentiment & Tone Analysis" brief (5-level progression from dictionary-based to LLM interpretation).

## Gap analysis (grounded in current code)

| Requirement | Status |
|---|---|
| **Level 1**: Loughran–McDonald financial-sentiment dictionary (7 categories) | ✅ Implemented. Bundled as `data/sentiment_dict/lm_word_lists.json` (JSON, not CSV). |
| **Level 2**: Section-level sentiment scoring (MD&A, Risk Factors, etc.) | ✅ Implemented. `edgar_embeddings.section_id` grouped and scored per section. |
| **Level 3**: Filing-to-filing change detection (Δ positive/negative/uncertainty YoY) | ✅ Implemented. `compare_filing_sentiment()` with per-category pct changes. |
| **Level 4**: Embedding-based tone shift (cosine similarity of MD&A across years) | ✅ Implemented. `compute_tone_shift()` with dimension validation, Item 7A exclusion. |
| **Level 5**: LLM-based narrative interpretation of management tone + key drivers | ✅ Implemented. `generate_tone_analysis()` with caching, env-var gate, abstention skip. |
| Frontend display of sentiment/tone results | ✅ Implemented. `ToneAnalysis.tsx` widget with direction badge, term counts, pct changes, tone-shift score. |
| `ChatResponse` model carries tone data | ✅ Implemented. `tone_analysis: Optional[Dict[str, Any]]` on both Python and TypeScript sides. |

---

## Implementation summary

### Phase A — Loughran–McDonald Dictionary + Section-Level Scoring ✅

**Files:** `api/services/sentiment.py`, `api/routes/sentiment.py`, `data/sentiment_dict/lm_word_lists.json`

- 7 sentiment categories: positive, negative, uncertainty, litigious, constraining, strong_modal, weak_modal
- `SentimentDictionary` frozen dataclass with `lru_cache` loading
- `count_sentiment(text)` — tokenizes via regex (`[a-z][a-z\-']*[a-z]|[a-z]`), intersects with dictionary
- `analyze_filing_sections(sections)` — per-section scoring + aggregation
- `get_filing_sentiment(ticker, accession)` — queries `edgar_embeddings`, groups by `section_id`
- Routes: `GET /api/sentiment/{ticker}`, `/{ticker}/compare`, `/{ticker}/history`

### Phase B — LLM Tone Interpretation + Frontend Widget ✅

**Files:** `api/services/sentiment.py` (`generate_tone_analysis`), `api/services/langgraph_engine.py`, `api/routes/chat.py`, `frontend/src/components/ToneAnalysis.tsx`

- `generate_tone_analysis(ticker)` — best-effort LLM synthesis, cached per `(ticker, accession)`, capped at 64 entries
- Gated by `SENTIMENT_LLM_ENABLED` env var (default true)
- Skipped on abstentions (`verification_status == "ABSTAIN"`)
- Wired into `run_auditable_rag` as post-processing after educational layers
- `tone_analysis` passed through `ChatResponse` to frontend
- `ToneAnalysis.tsx` renders: direction badge, term counts with pct changes, summary, key drivers

### Phase C — Filing-to-Filing Change Detection ✅

**Files:** `api/services/sentiment.py` (`compare_filing_sentiment`), `api/routes/sentiment.py`

- `compare_filing_sentiment(ticker, acc_a, acc_b)` — defaults to latest 2 filings
- Per-category deltas with pct changes: positive, negative, uncertainty, litigious, constraining, strong_modal, weak_modal
- Overall tone shift score

### Phase D — Embedding-Based Tone Shift ✅

**Files:** `api/services/sentiment.py` (`compute_tone_shift`), `api/routes/sentiment.py`, `frontend/src/components/ToneAnalysis.tsx`

- `compute_tone_shift(ticker)` — queries MD&A chunks (`Item 7`, excludes `Item 7A`)
- Validates embedding dimensions within and across filings
- Mean-pools embeddings per filing, computes cosine similarity via numpy
- Enriches chat `tone_analysis` with `tone_shift_similarity` and `tone_shift_interpretation`
- Frontend displays similarity score with color coding (green >0.95, amber >0.85, red <0.85)
- Route runs blocking work via `asyncio.to_thread()` to avoid event loop stall

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/sentiment/{ticker}` | GET | Per-section L-M sentiment for latest (or specified) filing |
| `/api/sentiment/{ticker}/compare` | GET | YoY delta between two filings (defaults to latest two) |
| `/api/sentiment/{ticker}/history` | GET | Sentiment scores for all filings of a ticker |
| `/api/sentiment/{ticker}/tone-shift` | GET | Embedding cosine similarity between MD&A sections |

---

## Chat response shape

When tone analysis is available, the `tone_analysis` block in `ChatResponse` contains:

```json
{
  "tone_label": "More Cautious",
  "tone_direction": "up",
  "tone_summary": "Management tone appears more cautious...",
  "key_drivers": ["New tariff risk discussion", "Increased supply chain commentary"],
  "positive_terms": 112,
  "negative_terms": 147,
  "uncertainty_terms": 89,
  "positive_change_pct": -8.0,
  "negative_change_pct": 22.0,
  "uncertainty_change_pct": 31.0,
  "section_scores": [{"section_type": "Item 7", "net_sentiment": 0.042, "tone_score": 0.031}],
  "tone_shift_similarity": 0.87,
  "tone_shift_interpretation": "Moderate consistency — minor topic shift detected"
}
```

---

## Review fixes applied

### Review 1 — Phase A/B integration
| Finding | Severity | Fix |
|---|---|---|
| `sections` dict iterated as list in `generate_tone_analysis` | WARNING | Changed to `dict.items()` iteration |
| `_tone_cache` unbounded | WARNING | Capped at 64 entries with FIFO eviction |
| JSON parse `rfind("}")` edge case | WARNING | Added safe `start/end` guard |
| Tone analysis ran on abstentions | WARNING | Gated on `verification_status != "ABSTAIN"` |

### Review 2 — Phase D
| Finding | Severity | Fix |
|---|---|---|
| `LIKE 'Item 7%'` matched Item 7A | CRITICAL | Changed to `(section_id = 'Item 7' OR section_id LIKE 'Item 7 %') AND section_id NOT LIKE 'Item 7A%'` |
| Sync route blocked event loop | HIGH | Wrapped in `asyncio.to_thread()` |
| No embedding dimension validation | HIGH | Added per-filing and cross-filing dimension checks |
| No `np.isfinite()` guard | LOW | Added finite check on similarity result |

---

## Relevant files

| File | Role |
|---|---|
| `api/services/sentiment.py` | **New** — dictionary loader, tokenizer, word counter, section scorer, LLM tone interpreter, tone-shift calculator |
| `data/sentiment_dict/lm_word_lists.json` | **Existing** — bundled Loughran–McDonald word lists (7 categories) |
| `api/routes/sentiment.py` | **New** — sentiment/tone endpoints (4 routes) |
| `api/models/schemas.py` | `SectionSentiment`, `FilingSentiment`, `SentimentDelta`, `FilingSentimentCompare`, `ToneShiftResult`, `tone_analysis` on `ChatResponse` |
| `api/services/langgraph_engine.py` | Wire `generate_tone_analysis` + `compute_tone_shift` into `run_auditable_rag` post-processing |
| `api/routes/chat.py` | Pass `tone_analysis` into `ChatResponse` |
| `api/main.py` | Register sentiment router |
| `frontend/src/api/chat.ts` | `ToneAnalysis` interface + `tone_analysis` on `ChatResponse` |
| `frontend/src/App.tsx` | `Message.tone_analysis` field + `ToneAnalysis` component rendering |
| `frontend/src/components/ToneAnalysis.tsx` | **New** — Management Tone widget (direction badge, term counts, pct changes, tone-shift score) |
| `tests/test_sentiment.py` | **New** — 34 unit tests (dictionary, tokenizer, counting, section analysis, filing aggregation, dataclass) |
| `edgar_embeddings` (DuckDB) | Read-only — queried for ticker sections + embeddings |
