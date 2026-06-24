# REVIEW-REQUEST — conjoint — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (architect)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. No push to prod
until **all** required lanes (MiMo, Gemini, Claude, DeepSeek) = `APPROVED`.

## Feature
Choice-based **conjoint analysis** of the answer experience, plus a self-selected
**standard (control) vs role-based (treatment)** A/B with an end-of-session
**usefulness vote**. Results persist to the durable review DB and an aggregate
study page computes count-based part-worth utilities + attribute importance +
usefulness-by-arm.

- 4 binary attributes: `answer_basis` (role_based|standard), `answer_style`
  (direct|explained), `prompts` (guided|suggested), `evidence` (text_only|graph_metrics).
- 4 roles w/ JTBD personas: Compliance Officer, Equity Research Analyst, Credit
  Analyst, Relationship Manager. `role_based` answers tailored via `role_guidance`
  appended to the qualitative answer system prompt (never alters numbers).
- Control = usefulness vote only; Treatment = conjoint choice tasks + vote.

## Files changed / added
**Backend**
- `api/routes/conjoint.py` (NEW) — endpoints `/attributes`, `/session`, `/response`,
  `/complete`, `/results`; tables `conjoint_sessions`, `conjoint_responses` in the
  review DB; counting analysis; role guidance lookup.
- `api/main.py` — registered `conjoint_router`.
- `api/models/schemas.py` — `ChatRequest.role`.
- `api/routes/chat.py` — passes `role_guidance_for(req.role)` into `run_auditable_rag`.
- `api/services/langgraph_engine.py` — `role_guidance` param + `GraphState` key +
  appended to `qualitative_output_node` system prompt only.

**Frontend**
- `frontend/src/api/conjoint.ts` (NEW) — types, API calls, localStorage prefs.
- `frontend/src/api/chat.ts` — `role` arg on `sendAuditableRagMessage`.
- `frontend/src/components/ConjointSurvey.tsx` (NEW) — tasks + vote flow.
- `frontend/src/components/ConjointGate.tsx` (NEW) — standard vs personalize entry.
- `frontend/src/pages/ConjointStudy.tsx` (NEW) — survey + results (recharts).
- `frontend/src/App.tsx` — `conjoint` view + nav, gate/survey modals, personalization
  gating (evidence/explanation/prompts), passes `roleArg` to chat.

## Verification already done by author
- Backend imports clean; counting analysis + preferred-levels verified on synthetic data.
- Full SQL flow exercised in-memory (both arms); fixed a `GROUP BY/ORDER BY` binder bug.
- `tsc -b --noEmit` passes on the frontend.

## Per-agent checklists

### MiMo (usability + performance) — REQUIRED
- [ ] Survey/gate flow is clear; control vs treatment is understandable; can't get stuck.
- [ ] `/results` and `/session` query cost on the review DB (indexes? table scans on
      `conjoint_responses` as it grows?). Recommend any index.
- [ ] No blocking/synchronous heavy work on the chat hot path from `role` wiring.
- [ ] localStorage prefs read on every render in `App.tsx` — acceptable? memoize?
- [ ] Modal auto-prompt (≥3 answers) isn't annoying / doesn't loop.

### DeepSeek (API + schema correctness) — REQUIRED
- [ ] Endpoint contracts + Pydantic validation (`chosen` ^[AB]$, `usefulness` 1..5,
      arm/role allow-listing, profile validation).
- [ ] Idempotent table creation + `ADD COLUMN IF NOT EXISTS` migrations are safe.
- [ ] `/response` never trusts client profiles beyond `_valid_profile`; injection-safe
      (all parameterized).
- [ ] `complete` derives prefs only from the session's own rows.

### Gemini (security / vulnerabilities) — REQUIRED before prod push
- [ ] Endpoints are unauthenticated POSTs (like `/analytics/track`) — acceptable?
      rate-limited by existing middleware? abuse/DoS via `/response` spam?
- [ ] `role` from client flows into the LLM system prompt via `role_guidance_for`
      (server-side allow-list, NOT raw client text) — confirm no prompt injection.
- [ ] No PII stored beyond the optional free-text `usefulness_comment` (capped 2000).
- [ ] Frontend renders no raw HTML from these responses (no new XSS vector).

### Claude (architecture) — REQUIRED before prod push
- [ ] Review DB is the right home (durable, snapshotted) vs main read-only DB.
- [ ] `role_guidance` injection is contained and never touches numeric output_node.
- [ ] Separation of concerns; no new coupling that breaks the DAG.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-conjoint.md`. Review only the files
> in your lane against your checklist, reading the actual diffs. Write your verdict
> to your lane file (`.<agent>/VERDICT-conjoint.md`) using the format in
> `.deepseek/coordination/PROTOCOL.md`. Do not modify source; report findings.
