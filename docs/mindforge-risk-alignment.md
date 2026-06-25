# MindForge Risk Alignment

How this application addresses the GenAI risk dimensions framed by **MAS Project
MindForge** (the Monetary Authority of Singapore's GenAI governance track, whose
*AI Risk Management Operationalisation Handbook* was published March 2026) and the
broader MAS lineage — **FEAT Principles (2018) → Veritas (2020–2023) → MindForge
(2023– ) → proposed Guidelines on AI Risk Management**.

> **Regulatory status (mid-2026):** the MAS Guidelines on AI Risk Management are
> *proposed*, not yet in force (consultation closed 31 Jan 2026; ~12-month
> transition expected). This document frames the app as built to a standard that
> is about to land. Cross-references to `§4.x` point at
> [`docs/specs/eval-layer-spec.md`](specs/eval-layer-spec.md), the authoritative
> internal spec.

This is a defensive / governance document. It maps **risk dimension → control →
evidence in code → status**, and is honest about gaps.

---

## At-a-glance coverage

| # | Risk dimension | Status | Primary controls |
|---|----------------|--------|------------------|
| 1 | Model Risk | ✅ Strong | Risk-tiered routing (§4.2), 10 always-escalate triggers (§4.3), drift monitoring (§4.5), XBRL/semantic cross-validation, dual-model consensus |
| 2 | Data & Privacy | ✅ Good | PII masking on output, input caps, public-filing corpus, no persistent user data |
| 3 | Bias & Fairness | 🟡 In progress | **Dual-model consensus rail** (example: DeepSeek + MiMo → frontier models in prod), sentiment/tone-skew checks, cross-company even-handedness |
| 4 | Transparency & Explainability | ✅ Strong | Per-answer audit log (sources, chunks, XBRL facts, math steps), Evidence Graph, surfaced confidence + reason codes |
| 5 | Governance & Accountability | ✅ Good | Sampled-review + escalate tiers, human-in-the-loop review queue, immutable run log |
| 6 | Legal & Regulatory | 🟡 Partial | Grounding/citation enforcement, regulator-facing audit API; advice-disclaimer rail TODO |
| 7 | Cyber & Security | ✅ Strong | Tiered API-key auth (constant-time), rate limiting, CORS, prompt-injection/jailbreak input rail, system-prompt-leak output rail, SQL/math execution rail |

---

## 1. Model Risk

**The risk:** the model silently misreads an edge case and downstream logic
executes flawlessly on bad data.

**How we address it:**
- **Risk-tiered autonomy** (`§4.2`, `api/services/confidence_scorer.py`): answers
  on the **auditable-RAG path** route to `AUTO` / `SAMPLED_REVIEW` / `ESCALATE`.
  Confidence is derived from *verifiable provenance + XBRL cross-check*, **not**
  the model's self-reported confidence (which collapses to ~0.5 and is useless for
  routing). *Note:* the conversational fast path, the `/sql` and `/rag` endpoints,
  and abstentions do **not** carry an eval route — scoring applies to the audited
  numeric/qualitative answers, not to greetings or non-scored modes.
- **Ten deterministic always-escalate triggers** (`§4.3`, `confidence_scorer.py`,
  `ALL_TRIGGERS`): balance-sheet identity violation, amended filing, bankruptcy /
  non-reliance / auditor-change / going-concern 8-Ks, XBRL mismatch, unrecognized
  concept, out-of-range value, and downstream-action — these escalate regardless
  of confidence because the cost asymmetry justifies a deterministic override.
- **Independent verification** before an answer is trusted:
  `xbrl_cross_validator.py`, `semantic_validator.py`, `polygon_verifier.py`,
  `verifier.py`.
- **Ongoing monitoring** (`§4.5`, `api/services/drift_detection.py`):
  human-agreement-rate floor + unrecognized-concept spike. Escalation rate is
  intentionally excluded as a trigger (REQ-RQ-05).
- **Dual-model consensus** (see §3) as a cross-model sanity check.

Maps to SR 11-7 *sound model validation* + *ongoing monitoring*, and MAS
*AI life-cycle controls*.

## 2. Data & Privacy

**How we address it:**
- **PII masking on every output** (`api/services/guardrails/output_rails.py`):
  SSN, credit card, email, phone, and API-key patterns are detected and redacted
  before the response leaves the service.
- **Input bounds** (`input_rails.py`): hard length cap; no unbounded prompts.
- **Low inherent exposure:** the corpus is *public SEC filings*, not customer PII.
- **What IS persisted, and why:** for auditability (§4 / MAS *documentation for
  reproducibility*), the `audit_runs` table **does persist the user's question and
  the generated answer**, plus feedback snippets in `reviewer_verdicts`. This is an
  intentional governance trade-off — the audit trail requires the query+answer — so
  the privacy posture is *"no account/identity data and no third-party data
  sharing"*, **not** "nothing is stored". Persisted to the durable review DB and
  snapshotted to a *private* dataset.
- **No end-user accounts or identity data** are collected.

**Caveat:** PII detection is regex/heuristic — it will miss novel formats. It is a
backstop, not a DLP system. If a user types PII into a question, that text is
captured in the audit log before output masking applies (output masking protects
the *response*, not the stored prompt).

## 3. Bias & Fairness

> **This is the dimension the dual-LLM example addresses.** In this PoC the
> consensus rail uses **DeepSeek (primary) + MiMo (secondary)**. **In a real
> deployment, swap the secondary to a *different-lineage frontier model*** (e.g.
> Anthropic Claude or OpenAI GPT — both already wired in `api/config.py`). This
> matters: DeepSeek and MiMo share a training lineage, so their biases are
> *correlated*; correlated models can agree confidently and both be wrong the same
> way. True bias mitigation needs models whose errors are *uncorrelated*.

**Controls:**
- **Dual-model consensus rail** (`api/services/guardrails/consensus_rails.py`):
  the audited answer is produced by the primary model; a second, independent model
  answers the **same question from the same retrieved context**; their material
  numeric claims are compared. Material divergence → escalate the audit/review
  tier and record the disagreement. Fail-open: any error or missing key returns a
  SKIPPED verdict so it can never break chat.

  > **Status:** the rail is **wired and active** on the auditable-RAG path, and runs
  > **asynchronously (fire-and-forget)** — `_spawn_consensus` in
  > `langgraph_engine.py` snapshots what it needs and starts a background daemon
  > thread (`_consensus_worker`), so it adds **zero latency** to the user-facing
  > answer. On material disagreement the worker escalates `AUTO→SAMPLED_REVIEW`,
  > opens a review-queue entry, and persists `consensus_*` to `audit_runs` **after**
  > the response is sent. Consequence: the **live response keeps its pre-consensus
  > route** and does not carry the consensus result; the audit row + review queue
  > converge a moment later (eventual consistency by design). The remaining open
  > item is the **frontier-model swap** for the secondary (see Planned hardening).

#### Risk-gating: which questions get the dual model

The second model is gated to **high-risk questions** so it isn't spent on every
answer (cost, not latency — the call is off the response path). The rail fires
only on:

| Gate | Run dual model? | Rationale |
| :--- | :--- | :--- |
| Already `SAMPLED_REVIEW` / `ESCALATE` route | **Yes** | The eval layer already judged it high-stakes |
| **Hard, multi-year questions** (spans ≥2 fiscal years / trend / CAGR / YoY / "since 20XX") | **Yes** | Cross-period reasoning compounds extraction + math error; highest payoff for a second opinion |
| Peer / multi-company comparison | **Yes** | Multiple extractions multiply the chance of a single bad figure |
| **Risk / compliance questions** (risk factors, litigation, regulatory, material weakness, going concern, covenants, restatement, impairment, related-party, etc.) | **Yes** | High regulatory/legal consequence — a misread carries the most weight, so it gets an independent second opinion |
| Single-period, single-metric `AUTO` answer | **No** | Low risk; the cost of a second call is not justified |
| Conversational / non-scored paths | **No** | No audited figures to cross-check |

The gate is encoded in `should_run_consensus(query, eval_route)` so the policy is
auditable and testable, not buried in route code. The "high-stakes route" row
*inherits* the eval layer's trigger-driven `SAMPLED_REVIEW`/`ESCALATE` decision —
the gate checks the route, it does not re-evaluate the §4.3 triggers. The
"conversational / non-scored" exclusion is enforced **upstream**, not inside
`should_run_consensus`: the conversational fast path returns in `chat.py` before
the rail is reached, and `_spawn_consensus` additionally bails when there are no
retrieved docs or the answer is an abstention — so such turns never invoke the
secondary model.
- **Domain-appropriate fairness = even-handedness across companies.** For SEC-
  filing Q&A, protected-class fairness is largely N/A; the live risk is treating
  some tickers more favorably than others, or letting sentiment skew leak into
  answers. Building blocks already present: `api/services/sentiment.py` +
  management-tone analysis, and the deterministic, ticker-agnostic numeric path.

**Already implemented:**
- Risk-gated rail wired into the live auditable-RAG path, running off the response
  path in a background daemon thread (fire-and-forget — zero added latency).
- `AUTO→SAMPLED_REVIEW` escalation + review-queue entry on material disagreement,
  applied to the audit row + review queue **after** the response is sent. The
  background worker serializes its review-DB writes under `review_conn_lock`.
- `consensus_status` / `consensus_divergence` / `consensus_secondary_model`
  persisted to `audit_runs` — columns are added at runtime via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (`_ensure_consensus_columns`,
  guarded to run once per process). **Only the divergence score and the secondary
  model name are persisted**; the full secondary answer is not stored. The **live
  response does not carry the consensus result** (it returns before the worker
  finishes) — the audit trail is the system of record.

**Planned hardening (remaining):**
1. Swap secondary model to a frontier, different-lineage model (the key one — the
   current DeepSeek+MiMo pair is correlated; see the box above).
2. Surface the persisted `consensus_*` fields in the `/api/audit` read API.
3. Add **cross-company consistency tests** (same question across tickers; flag
   unjustified variance) as an offline eval feeding drift detection.

**Honest status:** this is the least mature dimension. The rail is live and
audited, but its bias value is limited until the secondary becomes a
different-lineage frontier model; the consistency suite is still to come.

## 4. Transparency & Explainability

**How we address it:**
- **Per-answer audit record** (`api/routes/audit.py`, table `audit_runs`):
  every run logs `source_docs`, `chunk_ids`, `xbrl_facts_cited`, `math_steps`,
  `confidence`, `eval_route`, `verification_status`, `model_used`. Readable via
  `GET /api/audit` and `/api/audit/{run_id}`.
- **Diagnosable reason codes** (`§3`) instead of opaque pass/fail.
- **Evidence Graph:** click an edge → source filing, so each claim is traceable.
- **Confidence + route are surfaced to the user**, not hidden.

Maps to MAS *documentation for reproducibility and auditability* and FEAT
*Transparency*.

## 5. Governance & Accountability

**How we address it:**
- **Risk-tiered human oversight** (`§4.2`–`§4.4`): `SAMPLED_REVIEW` buys
  observability at controlled cost; `ESCALATE` forces human judgment on
  irreversible/high-impact answers.
- **Human-in-the-loop review queue** (`api/routes/review.py`,
  `api/db/review_queue.py`) with reviewer verdicts feeding the agreement-rate
  metric.
- **Immutable run log** = an accountability trail of what the model decided alone
  vs. what a human challenged.

Maps to SR 11-7 *governance + effective challenge* and MAS *meaningful human
oversight*.

## 6. Legal & Regulatory

**How we address it:**
- **Grounding/citation enforcement:** answers are tied to retrieved filing context;
  the output rail flags numeric claims not present in context as potential
  hallucination.
- **Regulator-facing audit API** (`/api/audit`) — "regulatory read access to
  pipeline run history."
- **Built to the MAS lineage** above (FEAT / Veritas / MindForge / proposed
  Guidelines).

**Gap to close:** no explicit *"not financial advice"* disclaimer or an
advice-blocking dialog rail yet. Recommended before any external/regulated use.

## 7. Cyber & Security

**How we address it:**
- **Tiered authentication** (`api/middleware/auth.py`): READ / WRITE / ADMIN keys,
  constant-time comparison (`hmac.compare_digest`), admin hard-fails rather than
  silently falling back to a shared key.
- **Rate limiting** (`api/middleware/rate_limit.py`) and **CORS**
  (`cors_config.py`).
- **Input rail** (`input_rails.py`): prompt-injection / jailbreak / role-hijack /
  prompt-leak patterns + a dual-LLM intent check (MiMo) + length cap.
- **Output rail** (`output_rails.py`): blocks responses containing system-prompt
  fragments.
- **Execution rail** (`execution_rails.py`): SQL/math execution safety; audit
  queries use parameterised branches, never f-string interpolation of user input.

---

## Honest gaps (do not oversell)

1. **Bias & Fairness** is partial — the consensus rail is live and persisted to
   the audit log, but it pairs **correlated models** (DeepSeek+MiMo) and lacks a
   cross-company consistency suite. *Frontier-model swap is the first fix.*
2. **Hallucination + PII checks are heuristic** (entity-overlap ratio, regex), not
   model-grade — they miss paraphrased fabrications and novel formats.
3. **No financial-advice disclaimer / advice-blocking rail** (Legal & Regulatory).
4. **No real-user ROI numbers** — the trust metrics (agreement rate,
   false-escalation rate, drift) are defined but need a shadow-deployment slice to
   produce a cited result (`§9.4`).

## Appendix — the dual-LLM example, and the production swap

The consensus rail (`api/services/guardrails/consensus_rails.py`) is intentionally
model-agnostic. It reads provider config from `api/config.py`, where
`deepseek`, `openai`, `anthropic`, and `mimo` are all already defined.

- **This PoC:** primary = DeepSeek, secondary = MiMo (both keys already in use).
- **Production:** keep the primary, set the secondary to a **different-lineage
  frontier model** (Claude / GPT). Only then does the consensus signal represent
  genuine model diversity rather than two correlated models agreeing.

The mechanism (independent answer from the same context → deterministic comparison
of material figures → divergence routes to review) is unchanged by the swap; only
the secondary model identifier changes.
