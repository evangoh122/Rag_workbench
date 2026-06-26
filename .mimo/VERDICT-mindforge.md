# VERDICT — mindforge — MiMo — round 1
Status: CHANGES NEEDED
Reviewed: api/services/guardrails/consensus_rails.py, docs/mindforge-risk-alignment.md

## Findings
- [SEVERITY: major] docs/mindforge-risk-alignment.md:85 — The design strategy to gate the consensus rail to high-stakes routes (to avoid doubling latency/cost on every answer) is NOT called out in the documentation or the code docstrings. Running this synchronously on every query would severely degrade performance. — Suggestion: Add a note in the Bias & Fairness section of the doc and the docstring of `consensus_rails.py` explicitly stating it should be conditionally executed for high-stakes routes.
- [SEVERITY: minor] api/services/guardrails/consensus_rails.py:92 — The `timeout=20.0` parameter means that on an API failure or hang, the chat path will still be slowed down by up to 20 seconds before failing open. While it fails open and doesn't block indefinitely, it *will* significantly delay the response on a timeout. — Suggestion: Consider lowering the timeout to a more aggressive threshold (e.g., 5-10s) if this is meant to fail fast, or explicitly document the worst-case latency impact.

## Notes
- `max_tokens=600` and `context[:12000]` boundaries are sane and will protect against unbounded context length issues.
- Confirmed no DB writes or review-DB costs are introduced in this module.
- The `mindforge-risk-alignment.md` document is highly readable and well-structured for non-engineers and compliance reviewers.

---

# VERDICT — mindforge — MiMo — round 3 (final)
Status: APPROVED
Reviewed: api/services/guardrails/consensus_rails.py; _apply_consensus_rail +
_ensure_consensus_columns wiring in api/services/langgraph_engine.py
(review driven via the MiMo API on user instruction)

## Findings
- none

## Notes
Latency bounded by risk-gating + 8s timeout; DB cost minimal (single UPDATE/INSERT
only on material disagreement); all synchronous work guarded by
should_run_consensus(); fail-open + deterministic divergence appropriate.

## Resolution of round 1
- r1 major (gating not documented) → FIXED: should_run_consensus() gate + doc §3
  table + docstring.
- r1 minor (timeout 20s) → FIXED: timeout 20→8s, env-configurable via
  CONSENSUS_TIMEOUT.
- r2 perf nits (per-disagreement ALTER write-lock; conn acquired twice; hard
  context chop) → FIXED: process-level _CONSENSUS_COLUMNS_ENSURED guard; single
  shared connection; paragraph-boundary truncation.

---

# VERDICT — mindforge — MiMo — round 4 (final, async + risk/compliance)
Status: APPROVED
Reviewed: consensus_rails.py (async-aware), _spawn_consensus / _consensus_worker /
_ensure_consensus_columns in langgraph_engine.py

## Findings
- none

## Notes
Hot-path cost is trivial (gating string/regex + one Thread.start()). Background
worker is fail-open with 8s timeout, serializes DB writes under the shared
review_conn_lock, DDL guarded to one ALTER per process, context capped at 12k.
No blocking/synchronous/unbounded work on the response path. Resolves the r3
latency major (sync→async fire-and-forget per user direction).

---

# VERDICT — mindforge — MiMo — round 5 (advice rail + concurrency)
Status: APPROVED
Reviewed: dialog_rails.py (investment-advice rail), consensus_rails.py,
_consensus_worker + get_new_review_connection wiring

## Findings
- none

## Notes
Advice rail patterns well-narrowed (excluded bare "recommend buying" → avoids the
board-buyback false positive; excluded bare "overvalued" → avoids impairment-test
questions). Gating still tight; 8s timeout + fail-open clean; daemon-thread
fire-and-forget = zero hot-path latency. The dedicated DuckDB connection in
_consensus_worker correctly avoids cross-thread connection sharing (resolves the
r-prior `.cursor()` concern and Codex r2).

---

# VERDICT — mindforge — MiMo — round 6 (Codex r3 fix)
Status: APPROVED
Reviewed: dialog_rails.py (reordered check_dialog), consensus_rails.py, wiring

## Findings
- none

## Notes
Advice rail ordering (advice → financial-keyword allowlist → off-topic denylist)
avoids the false-positive traps. Patterns narrow by design ("should i buy" needs
first-person "i"; "recommend" needs "you recommend"), so "the board recommends
buying back shares" passes. Dedicated DB connection per thread + explicit close in
`finally` cleanly solves the cross-thread concurrency issue.


---

# VERDICT — mindforge — MiMo — round 7
Status: APPROVED
Reviewed: api/db/database.py (get_new_review_connection -> parent.cursor()), api/services/guardrails/input_rails.py (needs_llm_check gate), api/services/langgraph_engine.py (worker conn lifecycle)

## Findings
- none

## Notes
- #2 gate (input_rails.py): latency/security trade-off is sound; the 200-char threshold is sane for typical single-line financial queries. Novel injections that evade the regex+keyword layers overwhelmingly run long or multi-line and still get deep-checked. Residual risk (a sub-200-char single-line novel injection) is acceptable for this threat surface (worst case is an off-topic/leaked-prompt answer, not code exec); consensus/output rails remain downstream. The gate is pure string arithmetic (negligible cost).
- #1 (.cursor()): no per-disagreement write-lock contention or churn beyond the existing design. parent.cursor() is a lightweight independent connection on the same DuckDB instance (no file re-open, no second file-lock); _review_conn_lock is held only for the microsecond .cursor() call; the worker fires only on a rare gated disagreement and closes the cursor in a finally -- no handle/connection leak.
- minor (non-blocking): count("
") >= 2 requires >=3 lines, so a 2-line sub-200-char message skips the LLM check. Within the accepted trade-off; matches the request text ("
 >= 2"). No change required for this lane.


---

# VERDICT — mindforge — MiMo — round 8 (blocking-llm-on-event-loop fix)
Status: APPROVED
Reviewed: api/routes/chat.py, api/services/guardrails/input_rails.py

## Findings
- [SEVERITY: nit] chat.py — pre-existing/out-of-scope: the sync engine calls (chat_sql/ask_rag/run_graph_rag) also run on the event loop; not introduced by this branch. The check_input offload is the correct targeted fix for the regression this branch added.

## Notes
- Event-loop stall removed: `run_in_threadpool(check_input, message)` dispatches the blocking ~5s MiMo call to AnyIO's worker pool and awaits it, freeing the loop; concurrent requests are no longer serialized. `_apply_input_rails` is async and awaited at all 4 endpoints (chat.py:118/139/161/187); check_input is plain sync -- a valid threadpool target.
- Default threadpool (40 tokens) acceptable: the expensive path is gated to >200char/multi-line + MIMO key; the 1500-char cap and cheap regex/keyword layers short-circuit first; the 5s timeout bounds hold time; excess burst queues on the limiter gracefully rather than stalling the loop. A dedicated limiter would be optional hardening, not required.
- check_dialog correctly kept on the loop (pure regex).


---

# VERDICT — mindforge — MiMo — round 9 (conjoint write-triggered snapshot)
Status: APPROVED
Reviewed: api/services/runtime_snapshot.py, api/routes/conjoint.py

## Findings
- [SEVERITY: nit] runtime_snapshot.py — Thread.start() was outside try: if it raises, _snap_in_flight stays True and wedges all future snapshots. [APPLIED: wrapped in try/except — resets the flag under the lock + returns False.]
- [SEVERITY: nit] _MIN_WRITE_SNAPSHOT_INTERVAL_S had no floor; a misconfigured env could disable the throttle. [APPLIED: max(60, ...).]
- [SEVERITY: minor] throttle stamps at snapshot start, so trailing writes wait for the next window (best-effort). [APPLIED: docstring note.]

## Notes
- Survey path stays fast: the sync portion of maybe_snapshot_async is a few env reads + a lock acquire + thread spawn (sub-ms, no I/O); the whole-DB Parquet export + upload runs in the daemon thread, so the response returns before any network/disk work. Off-Space it is a single env check -> zero overhead in dev.
- Throttle + single-in-flight is the right cost shape: <=1 whole-DB upload per interval, never >1 thread; a burst coalesces to one upload (verified). Write-triggered (vs a timer) avoids idle polling on a sleepy free Space and won't keep it awake; daemon=True so shutdown won't hang (graceful-shutdown snapshot still covers the final state).

---

# VERDICT — mindforge — MiMo — round 10 (no-mistakes fixes / merge-to-main gate)
Status: APPROVED
Reviewed: api/models/schemas.py, api/services/guardrails/input_rails.py, api/services/runtime_snapshot.py, api/services/guardrails/consensus_rails.py, api/services/guardrails/dialog_rails.py, api/services/langgraph_engine.py (wiring)

## Findings
none

## Notes
- Full re-review for the merge-to-main gate; covers the only deltas since round-9 APPROVED (the no-mistakes pipeline fixes): input cap 1500->4000 (schema + rail in sync), runtime_snapshot import-crash guard, stale test mock advice=False, obsolete scratch-script cleanup.
- The 4000-char cap adds ~2.5KB to the worst-case MiMo injection prompt (still gated on >200 chars) — negligible on the ~5s call. The snapshot interval guard adds sub-microsecond overhead under the lock and prevents a real boot-crash regression. Nothing in the recap architecture (gating, async fire-and-forget, advice-rail ordering) warrants reconsideration.
