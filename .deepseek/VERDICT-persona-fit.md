# VERDICT — persona-fit — DeepSeek — round 1
Status: APPROVED
Reviewed: api/routes/chat.py, api/routes/conjoint.py, api/services/langgraph_engine.py, api/services/guardrails/persona_rails.py, tests/test_persona_rails.py

## Findings
- [nit] `api/routes/conjoint.py:100` — Unicode character `â€”` appears in comment (likely encoding artifact from diff). Should be plain ASCII `--` or proper em-dash. Non-functional but cosmetic.
- [nit] `api/services/langgraph_engine.py:1358` — Same `â€”` encoding artifact in comment. Non-functional.
- [minor] `api/services/langgraph_engine.py:1361` — `_rg[:1200]` slice could silently truncate a multi-byte character mid-sequence. Consider `_rg[:1200]` is safe for Python strings (character-based, not byte-based), so this is fine — retracting.
- [nit] `api/services/guardrails/persona_rails.py:1` — Docstring references `api/routes/conjoint.py` path; verify this path is correct in the deployed tree (it is, per the diff). No issue.

## Notes
- `run_auditable_rag` new `role_key` param defaults to `None` — all existing callers unaffected. Backward-compatible.
- `chat.py` wiring passes `req.role` correctly; `role_key` is server-side allow-listed via `_ROLE_BY_KEY` map in `conjoint.py`.
- `ADD COLUMN IF NOT EXISTS` migrations on `audit_runs` are idempotent and guarded by process-level flag — safe.
- `PersonaFitVerdict` shape is clean; fail-open paths (unknown role, empty answer, no applicable requirements, exception) all return `skipped, fit=True` as specified.
- `result["persona_fit"]` extra key does NOT leak into `ChatResponse` — the response is built explicitly from `result["final_answer"]` in `chat.py:210`, not from the full result dict. Confirmed safe.
- No contract change to `/auditable-rag` endpoint — the route signature is unchanged.
- All checklist items verified: backward-compatible param, safe DDL, fail-open paths, no response leakage.


---

# VERDICT — persona-fit — DeepSeek — round 2
Status: APPROVED
Reviewed: api/services/guardrails/persona_rails.py, tests/test_persona_rails.py

## Findings
- [nit] api/services/guardrails/persona_rails.py:37 — The regex `_FINANCIAL_FIGURE` uses `re.VERBOSE` but the comment encoding shows garbled characters (`â€”`). This is a cosmetic issue in the diff display, not in the actual code. No action needed.

## Notes
The fix correctly and completely resolves the round-1 finding:

1. **`_FINANCIAL_FIGURE` regex** (line 37-47): Replaces the overly broad `_NUMBER` pattern that matched any digit sequence. The new regex explicitly requires one of:
   - Dollar-prefixed amounts (`$1,200`, `$3.4`)
   - Percentages (`12.5%`, `45 %`)
   - Scaled magnitudes with unit words (`3.4 billion`, `1,200 million`)
   - Thousands-separated numbers (`1,200`, `26,000`)
   
   This correctly excludes bare integers, form types ("10-K"), item numbers ("1A"), section numbers ("1.01"), and fiscal years ("2024").

2. **`_has_financial_figure` function** (line 94-101): Renamed from `_has_number` with updated docstring explaining the distinction. All call sites updated (lines 157, 163).

3. **Regression tests** (test_persona_rails.py:84-101): 
   - `test_credit_qualitative_citation_not_treated_as_figure` verifies the exact scenario from the finding — a qualitative answer citing "Item 1A of the 10-K, fiscal 2024" now correctly returns `fit=True` (skipped requirements).
   - `test_has_financial_figure_distinguishes_amounts_from_labels` provides comprehensive coverage of both positive and negative cases.

4. **No regressions**: The existing test `test_credit_unverified_number_without_caveat_misses` still passes because `$1,200 million` matches the new `_FINANCIAL_FIGURE` pattern (dollar-prefixed with thousands separator).

The fix is complete, correct, and introduces no false negatives or regex errors.
