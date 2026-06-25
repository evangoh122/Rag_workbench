# SUMMARY — mindforge — final

**Coordinator:** DeepSeek
**Commit gate (MiMo + DeepSeek):** ✅ **CLEARED TO COMMIT**
**Push gate (all lanes):** ⏳ still requires **Codex + Gemini** APPROVED before any
push to prod.

## Verdicts
| Lane | Final status | File |
| :--- | :--- | :--- |
| MiMo (usability/perf/latency) | ✅ APPROVED (no findings) | `.mimo/VERDICT-mindforge.md` |
| DeepSeek (correctness/schema/doc-vs-code) | ✅ APPROVED (no findings) | `.deepseek/VERDICT-mindforge.md` |
| Gemini (security) | ⏳ pending | `.gemini/VERDICT-mindforge.md` |
| Codex | ⏳ pending | (user-run) |

## What was fixed across rounds
- Risk-gating documented + encoded (`should_run_consensus`); rail no longer implied
  to run on every answer.
- Timeout 20→8s, env-configurable (`CONSENSUS_TIMEOUT`).
- Doc corrected: 10 triggers (not 8); routing scoped to auditable-RAG path;
  `audit_runs` persistence of question+answer disclosed; rail now documented as
  wired+active (it was wired after the first doc draft).
- Perf: process-level guard on the consensus-column DDL (avoids per-disagreement
  write-lock); single shared review-DB connection; paragraph-boundary context
  truncation.
- Docstring clarified that the primary answer is passed in, not produced here.

## Round 4 — async fire-and-forget + risk/compliance gating
After the Codex (push-gate) finding and a product decision, the rail was
restructured:
- **Async fire-and-forget**: `_spawn_consensus` runs `_consensus_worker` in a
  background daemon thread — zero latency on the response; audit/review converge
  after (eventual consistency). This makes the **Codex r1 lineage finding moot**
  (response carries its pre-consensus route; no in-response contradiction).
- **Risk/compliance added to the high-risk gate** (litigation, material weakness,
  going concern, covenants, regulatory, restatement, impairment, etc.) per user
  direction.
- Gemini (security) round 1 = APPROVED (timeout-default-arg minor → fixed by
  moving the env read into the body).
- **Re-review (round 4): MiMo = APPROVED, DeepSeek = APPROVED, no findings.**

Commit gate remains ✅ CLEARED. Codex finding addressed-by-design (async); a Codex
re-verify or explicit waive closes the push gate.

## Round 5 — investment-advice rail + concurrency hardening
- **Advice rail (Legal & Regulatory)**: `dialog_rails.py` hard-refuses
  recommendation/personal-action/price-prediction questions with a "not a licensed
  investment adviser" disclaimer; wired into `chat._apply_input_rails` (all chat
  endpoints). Patterns narrowed after MiMo review (no false positives on
  goodwill-impairment "overvalued" or board-buyback "recommend buying").
- **Concurrency (Codex r2 + MiMo)**: background worker opens its OWN DuckDB
  connection via `get_new_review_connection()` (not a shared/cursor connection).
- **Re-review (round 5): MiMo = APPROVED, DeepSeek = APPROVED, no findings.**

Commit gate ✅ CLEARED for round 5. Codex r2 concurrency blocker resolved with the
dedicated-connection fix (Codex re-verify or waive to fully close the push gate).

## Round 6 — Codex r3 fix (off-topic precedence)
- **Codex r3**: "Is goodwill overvalued per the impairment **test**?" was refused as
  off-topic because the generic education pattern matched bare "test" before the
  financial-keyword allowlist.
- **Fix**: `check_dialog` reordered to advice → financial-keyword allowlist →
  off-topic denylist; bare "test" removed from the education pattern. Added 3
  guardrail tests; full `tests/test_guardrails.py` (15) passes.
- **Re-review (round 6): MiMo = APPROVED, DeepSeek = APPROVED, no findings.**

Codex r2 (concurrency) resolved; Codex r3 (off-topic precedence) now fixed — needs
a Codex re-verify to flip the Codex lane to APPROVED and fully close the push gate.

## Note on process
The MiMo + DeepSeek reviews were driven directly via their APIs (Claude
orchestrated) on user instruction, rather than via separate CLI sessions. Verdict
files remain the audit artifacts.


## Round 7 — no-mistakes automated-review findings
Triggered by the no-mistakes pipeline's automated review (architecture/correctness lane), which read the full branch diff and returned 5 findings (1 error, 2 warning, 2 info) on the now-wired consensus rail + dialog/input guardrails. (The earlier pipeline failures were a Windows cmd.exe arg-length limit in how the daemon spawned the review agent -- fixed via `agent_path_override -> claude.exe` in ~/.no-mistakes/config.yaml -- not a code issue.)

Fixes (4 files, +47/-13):
- **#1 (error) database.py** -- `get_new_review_connection()` now returns `_review_conn.cursor()` (independent connection on the same DuckDB instance) instead of a 2nd `duckdb.connect()` the file-lock rejected. **Reverses the round-5 "dedicated connect" decision**: the second connect was a silent no-op (raised -> swallowed by fail-open -> consensus persistence + AUTO->SAMPLED_REVIEW escalation never landed). `.cursor()` reconciles Codex-r2's "don't share a handle across threads" intent (distinct object) with the lock constraint (same instance, no re-lock).
- **#2 (warning) input_rails.py** -- gated the blocking ~5s MiMo injection check to messages >200 chars or multi-line; short single-line inputs (already past regex+keyword layers) skip it.
- **#3 (warning) dialog_rails.py** -- replaced substring financial-keyword matching with a word-boundary regex (kills eps->"steps", ipo->"ipod", roa->"abroad", fab->"fabulous", asic->"basic" false positives).
- **#4 (info) schemas.py** -- `ChatRequest.message` max_length 8000->1500 to match the check_input runtime cap.
- **#5 (info)** left as-is -- documented v1 numeric-normalization limitation, fails safe.

Verification: `tests/test_guardrails.py` 15/15; regex validated both directions; gate logic confirmed.

**Re-review (round 7, run via the Claude API per prior process): MiMo = APPROVED, DeepSeek = APPROVED, no findings.** MiMo confirmed the gate latency/security trade-off and `.cursor()` non-contention; DeepSeek confirmed #1 cursor reconciliation, #3 regex correctness for all keyword shapes, and #4 schema-cap consistency, and explicitly retracted its round-5 "independent connect is the stronger fix" note.

**All four lanes round 7 = APPROVED, no findings:**
- MiMo (usability/perf/latency) -- gate trade-off + `.cursor()` non-contention confirmed.
- DeepSeek (correctness/schema) -- #1 cursor reconciliation, #3 regex (all keyword shapes), #4 schema-cap consistency confirmed; retracted its round-5 note.
- Codex -- re-verified #1: `.cursor()` returns a distinct handle (Codex-r2 thread-isolation intent preserved) while reusing the same instance to avoid the file-lock violation; reverses the round-5 "dedicated connect" decision it had originally approved.
- Gemini (security) -- #2 gate sound (short-form attacks already caught by regex+keyword; novel injections run long/multi-line), #3 regex mitigates regex-injection + closes false positives, #4 schema cap matches runtime.

Commit gate (MiMo + DeepSeek) [check] **CLEARED TO COMMIT**. Push gate (all lanes incl. Codex + Gemini) [check] **CLEARED** -- the Codex re-verify requested for #1 (it reverses the round-5 Codex-r2 concurrency decision) is in and APPROVED.


## Round 8 — blocking-LLM-on-event-loop fix (no-mistakes review)
A re-run of the no-mistakes pipeline on the round-7 commit (0aa34586) surfaced a real finding the round-7 fixes missed: `_apply_input_rails` (chat.py) was SYNC and called the now-blocking `check_input` (~5s MiMo HTTP call, gated by #2) synchronously inside the async chat endpoints -- stalling the asyncio event loop and freezing all concurrent requests on the live Space. The branch introduced it (check_input was pure regex before); #2's gate reduced frequency but not the blocking nature.

Fix (chat.py): `_apply_input_rails` -> async; `check_input` offloaded via `fastapi.concurrency.run_in_threadpool`; `check_dialog` (regex) kept on the loop; awaited at all 4 endpoints. tests/test_guardrails.py 15/15; module imports; iscoroutinefunction True. (The `--yes` pipeline auto-fixed this identically in its worktree but un-gated -- aborted so it didn't push; re-applied and gated here.)

**Re-review (round 8, via Claude API): MiMo = APPROVED, DeepSeek = APPROVED.** Both nits are pre-existing/out-of-scope: MiMo -- sync engine calls also on the loop; DeepSeek -- /sec-analyzer applies no input rails.

Commit gate (MiMo + DeepSeek) [check] **CLEARED**. Codex + Gemini already APPROVED round 7; round 8 changes only chat.py async wiring (not the guardrail/consensus logic they reviewed), so a Codex/Gemini re-glance on the offload is optional, not blocking for the commit gate.

**Follow-ups (out of scope, not blocking):** (1) /sec-analyzer endpoint applies no input rails; (2) the sync engine calls (chat_sql/ask_rag/run_graph_rag) still run on the loop and could be thread-pooled too.
