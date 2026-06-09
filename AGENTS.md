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
