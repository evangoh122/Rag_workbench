# VERDICT — persona-fit — Gemini — round 1
Status: APPROVED
Reviewed: `api/services/langgraph_engine.py`, `api/routes/conjoint.py`, `api/routes/chat.py`, `api/services/guardrails/persona_rails.py`

## Findings
- [nit] `api/services/langgraph_engine.py:1855` — A process-level flag `_PERSONA_COLUMNS_ENSURED` is used to prevent continuous DDL contention. Given DuckDB handles write locking, under burst conditions, a few concurrent threads might block until the lock releases, but DuckDB correctly handles idempotent schemas. This is structurally safe.
- [minor] `api/services/langgraph_engine.py:1874` — Thread creation is unmanaged. The daemon threads launched in `_apply_persona_rail` have no maximum bound. A massive burst of misses could technically spawn a large number of threads. Considering miss rates should be low, this is acceptable for now.

## Notes
- **Latency Profile**: The persona-fit rail uses pure deterministic heuristics (regex/string matching) rather than LLM-as-a-judge. This adds virtually zero overhead to the critical path.
- **Database Thread Safety**: The background persist worker (`_persona_persist_worker`) correctly spawns a *new*, dedicated DuckDB connection (`get_new_review_connection()`). This respects DuckDB's constraint against sharing connections across threads.
- **Fail-Open Posture**: The extensive `try-except` blocks wrapping `check_persona_fit`, the rail invocation, and the background thread ensure that even if the schema update or regex fails, the API route will not drop the user's request. No new prompt injection vectors are opened by splitting the `answer_requirements`.
