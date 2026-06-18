# RAG Workbench Agents

This document defines the roles, responsibilities, and ownership model for the AI agents collaborating on the RAG Workbench project.

## Agent Roles

### 🏛 Claude: Software Architect
**Branch:** `claude`
**Primary Focus:** Overall system design, maintainability, and architectural integrity.
**Responsibilities:**
- Enforce separation of concerns.
- Design API routes and organizational structure.
- Manage configuration validation.
- Implement core RAG pipeline abstractions.

### 🔒 Gemini: Security & Performance Engineer
**Branch:** `gemini`
**Primary Focus:** Security hardening, parallel processing, and multimodal data ingestion.
**Responsibilities:**
- Implement authentication and rate-limiting middleware.
- Optimize ingestion pipelines (EDGAR/Tickers).
- Secure API endpoints against injection risks.
- Optimize parallel retrieval using async/multithreading.

### ⚡ MiMo: Performance & Optimization Engineer
**Branch:** `mimo`
**Primary Focus:** Latency reduction, memory efficiency, and database optimization.
**Responsibilities:**
- Optimize query performance and caching strategies.
- Manage data pipeline efficiency.
- Benchmark and reduce startup bottlenecks.
- Optimize MySQL query performance.

## Ownership Model

| Component | Owner | Path |
| :--- | :--- | :--- |
| API Routes | Claude | `api/routes/` |
| Middleware | Gemini | `api/middleware/` |
| Retrievers | Gemini/MiMo | `api/retrievers/` |
| Configuration | Claude | `api/config.py` |
| Core RAG Pipeline | Claude | `api/services/graph_rag_engine.py`, `api/services/langgraph_engine.py` |
| Ingestion Scripts | Gemini | `scripts/embed_*.py` |
| Data Pipelines | MiMo | `data/` |
| Startup Logic | MiMo | `run.py` |
| Integration & UI | Main | `frontend/`, `main.py` |

## Merge Workflow

1. **Branching:** Each specialist works on their own branch (`claude`, `gemini`, `mimo`). Commits go to the named branch only — never directly to `main`.
2. **Peer Review (required):** Before any branch merges to `main`, one other specialist must review and approve it. No self-review.
3. **Review round-robin:**
   - `claude` branch → reviewed by **MiMo**
   - `mimo` branch → reviewed by **Gemini**
   - `gemini` branch → reviewed by **Claude**
4. **Review verdict:** Reviewer returns `APPROVED` or `CHANGES NEEDED`. If changes needed, author fixes on their branch and requests re-review.
5. **Integration:** Only approved branches merge to `main`. Claude resolves architectural conflicts; Gemini resolves security/perf conflicts; MiMo resolves optimization conflicts.
6. **Worktree base:** When dispatching agents with `isolation: "worktree"`, always verify the worktree is branched from `main` (not a stale specialist branch). Check with `git log --oneline <worktree-branch> | head -3` before dispatching review.

## Known Issues & Operational Gotchas

### DuckDB Version Mismatch (RESOLVED 2026-06-18)
- **Issue:** Local DuckDB (1.5.3) created database files incompatible with the Hugging Face Docker image (which initially capped DuckDB at `<1.1.0` in `requirements.txt`).
- **Symptom:** `Serialization Error: Failed to deserialize: expected end of object, but found field id: 103` on the space side when loading the database.
- **Fix:** Removed the `<1.1.0` upper cap constraint on `duckdb` in `requirements.txt` to align the Hugging Face Docker environment with the local database generation version (1.5.3). This permanently resolves the cross-platform serialization mismatch.
- **Venv Status:** The `.venv_duck10` virtual environment (previously used for backwards compatibility) is now obsolete. Development and deployment tasks utilize the main `.venv` (running DuckDB 1.5.3+) going forward.

### Section Extraction TOC Bug (FIXED 2026-06-18)
- **Issue:** `_extract_sections_with_labels()` used `re.search()` which matched TOC entries first. The 15% coverage guard then fell back to `full_text`, so ALL chunks got tagged `full_text`.
- **Fix:** Changed to `re.finditer()` + longest match. Retag script `scripts/retag_sections.py` fixed existing data.
- **Lesson:** When regex extraction has fallback logic, always test with real data — TOC entries look like section headers but are much shorter.

### Review Queue Empty
- **Issue:** `review_decisions` table is empty because all queries route to `AUTO` (confidence ≥ 0.85).
- **Not a bug:** High-confidence XBRL queries auto-accept. To populate the queue, run narrative-heavy queries that produce `SAMPLED_REVIEW` or `ESCALATE` routes.

### Orphaned Reviewer Verdicts
- **Issue:** 2 verdicts in `reviewer_verdicts` reference decision IDs that don't exist in `review_decisions`.
- **Cause:** Submitted via `/api/chat/feedback` endpoint (uses message timestamp as fake `decision_id`), not through the review queue.
