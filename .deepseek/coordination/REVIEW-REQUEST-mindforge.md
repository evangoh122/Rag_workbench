# REVIEW-REQUEST — mindforge — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (architect)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. (User will then
route to **Codex** + **Gemini** before any push to prod.)

## Feature
Documentation of **MAS Project MindForge** GenAI risk alignment, plus a standalone
**dual-model consensus rail** used as the illustrative *Bias & Fairness* control.

- A new doc maps the 7 MindForge risk dimensions (Model Risk, Data & Privacy,
  Bias & Fairness, Transparency & Explainability, Governance & Accountability,
  Legal & Regulatory, Cyber & Security) → control → evidence in code → status,
  and is explicit about gaps.
- A new guardrail module runs an **independent secondary model** over the **same
  retrieved context** and deterministically compares material numeric claims
  against the primary answer; material divergence is a "lower-confidence / route
  to review" signal. Fail-open by design.

> **IMPORTANT for reviewers:** the consensus rail is currently a **standalone
> module** — it is **NOT yet imported** into `chat.py` / `langgraph_engine.py`
> and does **not** run on the request path. It exists as the working example the
> doc references. Do **not** flag it as a dead import or assume it adds latency to
> live answers yet. Wiring is a deliberate follow-up (see "Deferred / out of
> scope").

> **Bias caveat already documented:** the example pairs DeepSeek + MiMo, which
> share a training lineage (correlated biases). The doc states production must
> swap the secondary to a *different-lineage frontier model* (Claude / GPT, both
> already in `api/config.py`) for the consensus signal to mean real diversity.

## Files changed / added
- `api/services/guardrails/consensus_rails.py` (NEW) — `ConsensusVerdict`
  dataclass; `check_consensus(query, context, primary_answer, *, divergence_threshold,
  timeout)`; deterministic numeric normalisation + divergence; MiMo secondary via
  `api/config.py` provider settings; fail-open on any error/missing key.
- `docs/mindforge-risk-alignment.md` (NEW) — risk-dimension → control → evidence
  mapping; cross-references `docs/specs/eval-layer-spec.md` §4.x and real source
  files; honest-gaps section; dual-LLM→frontier-swap appendix.

## Verification already done by author
- Module is self-contained; fail-open paths return `agree=True, skipped=True`
  (empty answer, no context, no MIMO key, secondary call exception, empty
  secondary).
- Numeric normaliser strips `$`/commas/trailing `%`; divergence = fraction of
  primary figures not corroborated by secondary.
- Removed an unused `_SCALE` regex. Remaining Pyright note on
  `api_key=Config.MIMO_API_KEY` is the SAME false positive as `input_rails.py`
  (`Config` is an instance via `config.py:285`), left for consistency.

## Per-agent checklists

### MiMo (usability + performance + latency + DB cost) — REQUIRED
- [ ] Latency/cost *when wired*: a synchronous secondary LLM call per answer
      ~doubles latency. Is the design (gate it to high-stakes routes vs every
      answer) called out correctly? Is `timeout=20s`, `max_tokens=600`,
      `context[:12000]` sane?
- [ ] Fail-open behaviour never blocks or slows the chat path on secondary
      failure/timeout — confirm.
- [ ] No DB writes added (consensus is response-only in v1) — confirm no review-DB
      cost introduced.
- [ ] Doc readability: is the risk table + per-dimension structure clear to a
      non-engineer reviewer (e.g. compliance)?

### DeepSeek (correctness + API/schema + doc-vs-code accuracy) — REQUIRED
- [ ] `check_consensus` contract + `ConsensusVerdict` shape are coherent; threshold
      semantics (`score <= threshold → agree`) correct.
- [ ] Numeric normalisation / divergence logic is sound and injection-safe (no
      eval, no SQL, regex only). Edge cases: no numbers, only secondary numbers,
      formatting differences ($1,200 vs 1200).
- [ ] **Doc accuracy is in-lane:** verify the file + `§4.x` references in
      `docs/mindforge-risk-alignment.md` actually match the code they cite
      (`confidence_scorer.py` triggers, `drift_detection.py`, `audit.py`
      `audit_runs` columns, `auth.py`, `output_rails.py`, `input_rails.py`,
      `execution_rails.py`). Flag any claim the code does not support.
- [ ] Gaps section is honest and not overselling coverage.

## Deferred / out of scope (do not block on these)
- Wiring the rail into `run_auditable_rag` / `chat.py` + `ChatResponse` field.
- Persisting `consensus_*` to `audit_runs`.
- Cross-company consistency eval suite.
- Frontier-model swap for the secondary.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-mindforge.md`. Review only the files
> in your lane against your checklist, reading the actual files. Write your verdict
> to your lane file (`.<agent>/VERDICT-mindforge.md`) using the format in
> `.deepseek/coordination/PROTOCOL.md`. Do not modify source; report findings.

---

# REVIEW-REQUEST — mindforge — round 2

**Status of round 1:** MiMo = CHANGES NEEDED, DeepSeek = CHANGES NEEDED (the
written verdict file is authoritative — a relayed "APPROVED" does not count).
Gate remains BLOCKED. All round-1 findings addressed below; please re-verify your
lane and append a round-2 verdict.

## Findings addressed (round 1 → fix)
| # | Lane | Finding | Fix |
| :--- | :--- | :--- | :--- |
| 1 | DeepSeek/MiMo | Doc said "8 always-escalate triggers"; code has 10 (`ALL_TRIGGERS`) | Doc lines updated to **10**, triggers enumerated (added `out_of_range`, `downstream_action`) — verified against `confidence_scorer.py` |
| 2 | MiMo (major) | Risk-gating to high-stakes routes not stated in doc/docstring | Added "Risk-gating" table to doc §3 **and** a `should_run_consensus(query, eval_route)` gate + docstring note in `consensus_rails.py` |
| 3 | MiMo (minor) | `timeout=20.0` worst-case latency | Lowered default to **`8.0`** |
| 4 | DeepSeek (major) | Doc overstated "every answer" eval routing | §1 now scopes routing to the **auditable-RAG path** and lists the non-scored paths (conversational/`/sql`/`/rag`/abstain) |
| 5 | DeepSeek (major) | "No persistent user data" contradicts `audit_runs` persisting question+answer | §2 rewritten: states `audit_runs` **does** persist question+answer (audit trade-off), scoped privacy claim to "no accounts/identity, no third-party sharing"; added note that PII in a prompt is logged before output masking |
| 6 | DeepSeek (minor) | Consensus rail not-wired status unclear | Added explicit "**not yet wired into live routing**" status block in doc §3 |

## New / changed since round 1
- `api/services/guardrails/consensus_rails.py` — added `should_run_consensus()`
  risk gate (high-stakes route OR multi-year/trend OR comparison → run; else skip),
  risk-gating docstring, timeout 20→8s. Smoke-tested: 6 gating cases + divergence
  behave as specified.
- `docs/mindforge-risk-alignment.md` — items 1, 4, 5, 6 above + §3 risk-gating
  table referencing `should_run_consensus`.

## Re-check checklist
### MiMo — REQUIRED
- [ ] §3 risk-gating table + `should_run_consensus` resolves the "every answer"
      latency concern.
- [ ] `timeout=8.0` acceptable worst-case before fail-open.

### DeepSeek — REQUIRED
- [ ] Trigger count + enumeration now matches `ALL_TRIGGERS`.
- [ ] §1 routing scope and §2 persistence statement are now accurate vs code.
- [ ] `should_run_consensus` logic is sound (year regex, signal lists, route gate).

---

# REVIEW-REQUEST — mindforge — round 7

**Coordinator:** DeepSeek (Claude orchestrating, per process note in SUMMARY)
**Author of change:** Claude (architect)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. (User then routes to
**Codex** + **Gemini** before any push to prod. **Codex re-verify is specifically
requested this round** — see finding #1, it reverses a round-5 Codex decision.)

## What triggered this round
The change was run through the **no-mistakes** pipeline. Its automated review lane
(architecture/correctness) read the **full branch diff** and returned **5 findings**
(1 error, 2 warning, 2 info) on the now-**wired** consensus rail and the dialog/input
guardrails. Four are addressed below; the fifth is a documented v1 limitation left
as-is. No findings were about the docs. (Note: the earlier pipeline failures were a
Windows `cmd.exe` arg-length limit in how the daemon spawned the review agent — not a
code issue; fixed via `agent_path_override → claude.exe`.)

## Findings addressed (no-mistakes review → fix)
| # | Sev | File | Finding | Fix |
| :-- | :-- | :-- | :-- | :-- |
| 1 | **error** | `api/db/database.py:100` | `get_new_review_connection()` opens a **2nd** `duckdb.connect(REVIEW_DB_PATH)` while the singleton `_review_conn` already holds the file open RW. DuckDB's file-lock (see `execute_readonly` docstring) forbids a 2nd same-file connect in-process → it raises, the consensus worker's fail-open `try/except` swallows it, and **audit persistence + AUTO→SAMPLED_REVIEW escalation silently never land** (rail is a no-op). | Return `self._review_conn.cursor()` — an independent connection on the **same** instance (no re-lock, same tables). |
| 2 | warning | `api/services/guardrails/input_rails.py:133` | `check_input()` makes a **blocking** MiMo call (5s timeout) on **every** chat turn — undercuts the async design of the consensus rail. | **Gate** the call: only invoke MiMo when `len(message) > 200` **or** the message is multi-line (`\n` ≥ 2). Short single-line inputs that already cleared the cheap regex/keyword layers skip the 5s call. |
| 3 | warning | `api/services/guardrails/dialog_rails.py:179` | Financial-keyword allowlist (round-6 reorder) uses **substring** match (`kw in msg_lower`); short keys false-positive: `eps`→"st**eps**", `ipo`→"**ipo**d", `roa`→"ab**roa**d", `fab`→"**fab**ulous", `asic`→"b**asic**". Off-topic queries ("steps to bake a cake") get routed into the RAG pipeline. | Precompiled **word-boundary** regex `_FINANCIAL_KEYWORD_RE` (longest-first alternation, `re.escape`'d). |
| 4 | info | `api/models/schemas.py:6` | `check_input` rejects > 1500 chars but `ChatRequest.message` allowed `max_length=8000` → dual limit; 1501–8000 passes pydantic then 400s at runtime. | Schema `max_length` 8000 → **1500** to match the runtime cap (reject once at the boundary). |
| 5 | info | `consensus_rails.py` | Numeric normalisation treats `1,200` vs `1.2 billion` as uncorroborated (false DISAGREE). | **Left as-is** — documented v1 limitation; fails in the conservative (over-escalate) direction. |

## ⚠️ IMPORTANT — finding #1 reverses a round-5 decision (Codex, please re-verify)
Round 5 (per SUMMARY) **deliberately** made the worker open its **own** DuckDB
connection via `get_new_review_connection()` "(not a shared/cursor connection)" to
resolve the **Codex r2** concurrency blocker (don't share one connection object across
threads). The no-mistakes review shows that approach is a **silent no-op** because the
file-lock rejects the second connect. The `.cursor()` fix **reconciles both
constraints**: `conn.cursor()` returns a **distinct connection object** (so request and
worker threads never share one handle — satisfies the Codex r2 intent) on the **same
database instance** (so no second file-lock — satisfies the no-mistakes finding). This
is the idiomatic DuckDB per-thread pattern. Please confirm this reading.

## Files changed (uncommitted; +47 / −13 across 4 files)
- `api/db/database.py` — `get_new_review_connection()` → `parent.cursor()` under
  `_review_conn_lock`; docstring rewritten to explain the lock/cursor rationale.
- `api/services/guardrails/input_rails.py` — `needs_llm_check` gate before the MiMo call.
- `api/services/guardrails/dialog_rails.py` — `_FINANCIAL_KEYWORD_RE` word-boundary
  matcher; `check_dialog` uses `.search()` instead of substring `any(...)`.
- `api/models/schemas.py` — `ChatRequest.message` `max_length` 1500.

## Verification already done by author
- Both rail files + schema parse clean.
- Regex validated both directions: false positives (`steps`, `ipod`, `abroad`,
  `fabulous`, `basic`) → no match; real terms (`eps`, `roa`, `roe`, `ipo`, `r&d`,
  `free cash flow`) → match.
- Gate logic confirmed: short single-line → skip MiMo; >200 chars or multi-line → check.
- **`tests/test_guardrails.py` 15/15 pass.**
- `database.py` `.cursor()` change is logic-only (cannot exercise the worker without a
  live secondary); reasoning above + DuckDB cursor semantics.

## Per-agent re-check checklist
### MiMo (usability + performance + latency) — REQUIRED
- [ ] #2 gate (`len>200` or multi-line) is a sound latency/security trade-off — does
      skipping the MiMo analyzer on short single-line inputs (already past regex +
      keyword layers) leave an acceptable residual risk? Is the 200-char threshold sane?
- [ ] #1 `.cursor()` introduces no per-disagreement write-lock contention beyond the
      existing design.

### DeepSeek (correctness + API/schema) — REQUIRED
- [ ] #1 `.cursor()` reconciliation is correct (distinct handle, same instance, no
      re-lock) and the round-5/Codex-r2 intent is preserved. **In-lane: the crux.**
- [ ] #3 word-boundary regex is correct for all keyword shapes (multi-word phrases,
      `r&d`, `p/e`, `10-k`, `non-gaap`) — no regex-escaping or boundary bugs.
- [ ] #4 schema `max_length=1500` is consistent with `check_input` and doesn't break
      any longer legitimate flow.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-mindforge.md` (round 7). Review only the
> files in your lane against the round-7 checklist, reading the actual files. Append your
> verdict to your lane file (`.<agent>/VERDICT-mindforge.md`) using the PROTOCOL.md
> format (round 7). Do not modify source; report findings.


---

# REVIEW-REQUEST — mindforge — round 8

**Coordinator:** DeepSeek (Claude orchestrating). **Gate:** MiMo + DeepSeek APPROVED before commit.

## What triggered this round
A re-run of the no-mistakes pipeline on the round-7 commit (0aa34586) surfaced one **real, still-unfixed** finding the round-7 fixes missed:

**`blocking-llm-on-event-loop` (chat.py)** — `_apply_input_rails` was a SYNC function calling the now-blocking `check_input` (~5s MiMo HTTP call, gated by round-7 #2) synchronously inside the `async def` chat endpoints. When the call fires it stalls the asyncio event loop and freezes ALL concurrent requests on the live Space. The branch introduced this (check_input was pure regex before); #2's gate reduced frequency but not the blocking nature.

The pipeline's `--yes` auto-fix applied the same fix in its worktree but **un-gated**; that run was aborted before push, and the fix was re-applied and gated here.

## Fix under review (api/routes/chat.py only)
- `_apply_input_rails` -> `async`; offload `check_input` via `fastapi.concurrency.run_in_threadpool`; keep `check_dialog` (regex) on the loop; `await` at all 4 endpoints (/sql, /rag, /graph-rag, /auditable-rag).
- Verified: module imports; `iscoroutinefunction(_apply_input_rails)` True; `tests/test_guardrails.py` 15/15.

## Checklists
### MiMo (perf/latency/throughput) — REQUIRED
- [ ] Offload removes the event-loop stall; default threadpool acceptable for the gated load profile; check_dialog correctly kept inline.
### DeepSeek (correctness/API) — REQUIRED
- [ ] sync->async conversion correct/complete; all 4 awaited; run_in_threadpool import + signature correct; check_input contract (returns InputVerdict, never raises) preserved; HTTPException(400) propagation unchanged.
