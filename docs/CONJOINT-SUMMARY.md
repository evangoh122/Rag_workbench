# Conjoint Analysis + Standard-vs-Personalized A/B — Implementation Summary

> Handoff for review. Status: **implemented, reviewed (MiMo + DeepSeek), NOT committed/pushed.**

## What it does
Adds a **choice-based conjoint study** of the answer experience plus a **self-selected A/B**
(standard "control" vs role-based "treatment") with an **end-of-session usefulness vote**.
Results persist to the durable DuckDB; an aggregate page computes part-worth utilities,
attribute importance, and usefulness-by-arm.

**4 binary attributes:** `answer_basis` (role_based|standard), `answer_style` (direct|explained),
`prompts` (guided|suggested), `evidence` (text_only|graph_metrics).

**4 role personas (JTBD):** Compliance Officer (Mary M.), Equity Research Analyst (Derek T.),
Credit Analyst (Nayara N.), Relationship Manager (Robert Q.).

## Key product decisions (locked with the user)
- Purpose: **both** — run the survey *and* apply winning prefs to the session.
- Format: **choice-based conjoint** (pick 1 of 2 profiles per task; ~6 tasks).
- Analysis: **count-based** part-worth utilities + attribute importance (zero new deps).
- Placement: **modal** (entry gate + end-of-session) **and** dedicated `/rag/conjoint` page.
- Arm assignment: **self-selected** (not randomized) — analysis labeled observational, not an RCT.
- Survey coverage: **both arms vote; only treatment does the conjoint tasks.**

## How it works
**Flow:** entry gate (Standard vs Personalize → pick role) → personalization applies during chat
→ after ≥3 answers an end-of-session modal opens → treatment does choice tasks + vote, control
votes only → `/complete` returns the respondent's winning levels.

**Personalization (treatment):**
- Presentation (frontend): `answer_style` toggles the explanation layer; `evidence` toggles
  chart/audit panels; `prompts` relabels follow-ups. Control shows everything (standard).
- `answer_basis=role_based` (backend): `chat.py` sends `role` → `role_guidance_for(role)` →
  `run_auditable_rag(..., role_guidance=...)` → appended **only to the qualitative answer system
  prompt**. **Never touches the numeric `output_node`**, so audited numbers are unaffected.
- The injected guidance carries the **full persona JTBD** (situation, motivation, outcome,
  emotional job, social job + directive), not just a tone hint.

**Storage:** durable review DB (`REVIEW_DB_PATH`, same volume as `analytics_events`). Tables
`conjoint_sessions` (arm, role, usefulness, comment, applied_prefs) and `conjoint_responses`
(profiles + chosen), indexed on `session_id`.

## Endpoints (`api/routes/conjoint.py`)
`GET /attributes`, `POST /session`, `POST /response`, `POST /complete` (existence +
already-completed guard), `GET /results`. All SQL parameterized; arm/role server-side
allow-listed; `chosen ^[AB]$`, `usefulness 1..5`, exact-key profile validation.

## Files
- **New backend:** `api/routes/conjoint.py`
- **Modified backend:** `api/main.py` (router), `api/models/schemas.py` (`ChatRequest.role` +
  pattern), `api/routes/chat.py` (role wiring), `api/services/langgraph_engine.py`
  (`role_guidance` state + prompt injection)
- **New frontend:** `frontend/src/api/conjoint.ts`, `components/ConjointSurvey.tsx`,
  `components/ConjointGate.tsx`, `pages/ConjointStudy.tsx`
- **Modified frontend:** `frontend/src/api/chat.ts` (role arg), `frontend/src/App.tsx`
  (view + nav, gate/survey modals, personalization gating)

## Review done (MiMo + DeepSeek, via their real APIs)
- **Round 1 → CHANGES NEEDED.** Applied the legitimate fixes: index on `session_id`, exact-key
  profile validation, `/complete` existence/already-completed guard, `role` regex pattern,
  migration error logging, survey error phase on session-start failure, lazy localStorage init,
  persona-context enrichment.
- **Round 2 → CHANGES NEEDED, but findings are mostly false positives** (DeepSeek reverses its
  own round-1 advice and flags static migration SQL as "injection"; MiMo re-flags a re-prompt
  loop and progress-bar jump the code doesn't have). Only legit item: `/results` full scan —
  intended for an aggregate endpoint. **Recommendation: stop the loop.**
- Verdict files: `.mimo/VERDICT-conjoint.md`, `.deepseek/VERDICT-conjoint.md`.
  Coordination protocol + request: `.deepseek/coordination/`.

## Verification
- Backend imports clean; SQL flow exercised end-to-end (both arms); counting-analysis math
  verified; extra-key rejection, index creation, role-pattern enforcement confirmed.
- Frontend `tsc -b --noEmit` clean.

## Things worth a reviewer's eye
1. Self-selected arm = selection bias (intended; labeled observational). Consider randomization
   if causal claims are needed.
2. Role guidance applies to qualitative answers only (numeric framing untouched by design).
3. Conjoint endpoints are unauthenticated POSTs (like `/analytics/track`); covered by the global
   `rate_limit_middleware`, no per-session throttle.
4. Counting analysis is the "count" method, not a logit/HB model — fine as a first-order estimate.

## Status
**Not committed, not pushed** (per the commit gate). Awaiting go-ahead to commit on a branch.
