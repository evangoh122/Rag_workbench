# VERDICT — persona-fit — MiMo — round 1
Status: APPROVED
Reviewed: `api/services/langgraph_engine.py`, `api/routes/conjoint.py`, `api/routes/chat.py`, `api/services/guardrails/persona_rails.py`, `tests/test_persona_rails.py`

## Findings
- [SEVERITY: minor] `langgraph_engine.py:1876` — `from api.services.guardrails.persona_rails import check_persona_fit` is an inline import inside `_apply_persona_rail`, which is called synchronously on every role-keyed request. After the first call Python resolves it from `sys.modules` cache so the cost is a dict lookup, but hoisting to the top of the function or module level would be cleaner for a hot-path function. — Move import to function-top level (outside `try`) or accept the current pattern with a comment explaining the circular-import rationale.
- [SEVERITY: minor] `langgraph_engine.py:1855–1863` — `_PERSONA_COLUMNS_ENSURED` guard is not atomic: under burst traffic, N threads arriving before the flag is set will all enter the DDL block. The `ADD COLUMN IF NOT EXISTS` makes this idempotent so no harm, but the contention will serialize behind DuckDB's write lock. Same pattern as `_CONSENSUS_COLUMNS_ENSURED`; consistent, but worth noting. — Acceptable as-is; just noting the serialization window.
- [SEVERITY: nit] `tests/test_persona_rails.py:88` — File is missing a trailing newline. — Add `\n` at end of file.
- [SEVEREITY: nit] `persona_rails.py:34` — `_NUMBER` regex matches bare `12.5` inside prose like "12.5%" but also matches stray digits in section references (e.g. "Item 1A" won't match since it's not a pure number start, but "Form 10-K" could match `10`). The conditional `applies` guard on credit_analyst means this only triggers number-conditional checks, so false positives are benign (a false positive *adds* requirements to check, which is conservative). — No action needed; behaviour is conservative.

## Notes
- **Latency**: `_apply_persona_rail` is pure regex/keyword heuristics, zero IO, bounded by 1–4 requirements per role. Negligible sub-millisecond cost. ✅
- **DB writes**: Only on a miss (rare), in a daemon thread, on a dedicated connection via `db_manager.get_new_review_connection()`. Write-lock pressure stays minimal. ✅
- **DDL guard**: `_ensure_persona_columns` runs at most once per process (flag-gated). Idempotent via `IF NOT EXISTS`. ✅
- **Token cost**: Role instruction cap lifted from 1000→1200 chars (~50 extra tokens per persona-keyed request). Acceptable. ✅
- **Memory**: `result["persona_fit"]` is a small fixed-shape dict; no unbounded growth. ✅
- **Fail-open**: Every error/unknown-role/empty-answer path returns `skipped=True, fit=True`. Rail can never degrade the chat path. ✅
- **Consistency with consensus rail**: Same daemon-thread + dedicated-connection + column-ensure pattern. No new coupling introduced. ✅

---

# VERDICT — persona-fit — MiMo — round 2
Status: APPROVED
Reviewed: api/services/guardrails/persona_rails.py, tests/test_persona_rails.py

## Findings
- [SEVERITY: LOW] api/services/guardrails/persona_rails.py:34-46 — Regex may miss edge‑case financial formats (e.g., “‑3.4%” or “$.5B”), but these are uncommon in SEC filings and outside the round‑1 scope. — No fix required; the current patterns cover the vast majority of real reported figures.

## Notes
The fix directly addresses the round‑1 false‑positive issue by replacing the overly broad `_NUMBER` regex with a targeted `_FINANCIAL_FIGURE` pattern that distinguishes real monetary/percentage/scaled figures from filing labels, form types, and years. The two new tests validate both the specific regression case and the regex’s ability to differentiate figures from non‑figures. No regressions in regex matching, performance, or requirement applicability are observed.


---

# VERDICT — persona-fit — MiMo — round 3
Status: APPROVED
Reviewed: api/services/guardrails/persona_rails.py:49, tests/test_persona_rails.py:101-109, tests/test_persona_rails.py:127-132

## Findings
- [SEVERITY: nit] api/services/guardrails/persona_rails.py:49 — The new regex branch uses `[kKmMbBtT]` but the entire pattern is compiled with `re.IGNORECASE`, making explicit case alternation redundant. — Could simplify to `[kmbt]` for clarity (optional, no functional impact).

## Notes
DeepSeek's fix correctly resolves the original finding. The regex `(?:\d+\.\d+[kKmMbBtT]|\d{3,}[kKmMbBtT])(?:\b|(?=[\s,;
