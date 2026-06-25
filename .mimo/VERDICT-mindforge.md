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
