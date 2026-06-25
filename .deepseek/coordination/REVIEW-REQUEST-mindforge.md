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
