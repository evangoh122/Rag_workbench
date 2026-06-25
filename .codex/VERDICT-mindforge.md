# VERDICT - mindforge - Codex - round 1
Status: CHANGES NEEDED
Reviewed: 85c9574e; api/services/guardrails/consensus_rails.py; api/services/langgraph_engine.py; api/models/schemas.py; api/routes/chat.py; api/routes/audit.py; api/db/review_queue.py; docs/mindforge-risk-alignment.md; .mimo/VERDICT-mindforge.md; .deepseek/VERDICT-mindforge.md; .deepseek/coordination/SUMMARY-mindforge.md

## Findings
- [SEVERITY: major] api/services/langgraph_engine.py:1839 - When a consensus disagreement upgrades an `AUTO` answer to `SAMPLED_REVIEW`, `_apply_consensus_rail()` mutates the top-level `result["eval_route"]` and patches `audit_runs`, but it leaves `result["lineage"]["eval_route"]` and `result["lineage"]["review_id"]` with the pre-consensus values created by `lineage_node()`. The `/api/chat/auditable-rag` response exposes both top-level `eval_route` and nested `lineage`, so the same response can say `eval_route=SAMPLED_REVIEW` while `lineage.eval_route=AUTO` and `lineage.review_id=None`, even though a review-queue entry was created. - Update the in-memory lineage after the route override/review insert, or run the consensus rail before lineage is built so the audit row, review queue, and response lineage are generated from one final route.

## Notes
- MiMo and DeepSeek final approval artifacts are present, but push gate remains blocked by this Codex lane until the response-lineage inconsistency is fixed or explicitly waived.
- I did not run the test suite for this review pass.

---

# VERDICT - mindforge - Codex - round 2
Status: CHANGES NEEDED
Reviewed: 41279cbc; api/services/guardrails/consensus_rails.py; api/services/langgraph_engine.py; api/db/database.py; api/models/schemas.py; api/routes/chat.py; api/routes/audit.py; api/routes/review.py; api/db/review_queue.py; docs/mindforge-risk-alignment.md; .mimo/VERDICT-mindforge.md; .deepseek/VERDICT-mindforge.md; .gemini/VERDICT-mindforge.md; .deepseek/coordination/SUMMARY-mindforge.md

## Findings
- [SEVERITY: major] api/db/database.py:74 - The async consensus worker writes to the singleton review DuckDB connection in a background thread, but `review_conn_lock` is not applied consistently to that connection's use. `_consensus_worker()` holds the lock for its writes, while existing request paths (`lineage_node()`, `/api/audit`, `/api/review`, `/api/chat/feedback`, analytics/conjoint/stats) call `db_manager.get_review_connection()` and then execute on the same connection without holding the lock. That means the new background worker can still race with normal review/audit reads and writes on one DuckDB connection; the lock only protects the worker against itself, not the shared connection globally. - Add a review-DB execution helper/transaction wrapper on `DatabaseManager` and route all review DB operations through it, or return a per-thread/per-operation review connection so the background worker cannot concurrently use the same connection object as request handlers.

## Notes
- Codex round 1 finding is resolved by the async design: the response no longer includes `consensus`, and it intentionally returns the pre-consensus route while audit/review converge afterward.
- I did not run the test suite for this review pass.
