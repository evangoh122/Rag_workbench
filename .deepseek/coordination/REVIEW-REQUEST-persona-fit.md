# REVIEW-REQUEST — persona-fit — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (architect)
**Branch:** `feat/mindforge-consensus-rail` (uncommitted working tree)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. No push to prod
until **all** required lanes (MiMo, Gemini, Claude, DeepSeek) = `APPROVED`.

## Feature
Two changes that make the four conjoint **personas** actually get served to their
requirements:

1. **Persona guidance split (tone vs requirements).** Each role previously had a
   single `answer_guidance` blob that the engine injected as *"Tailor the answer's
   tone, emphasis, and depth…"* — which flattened content/structure MUSTs (cite
   every section, caveat unverified numbers) into a tone hint. Now each role has:
   - `answer_guidance` → TONE/EMPHASIS, and
   - `answer_requirements` → the hard, checkable behavioral MUSTs.
   `role_guidance_for()` labels them distinctly; the engine injection no longer
   downgrades requirements to tone and explicitly preserves the "never change the
   numbers / never introduce facts" guarantee.

2. **Persona-fit rail (NEW guardrail).** After an answer is generated for a role,
   a deterministic, fail-open rail checks whether the answer satisfies that
   persona's `answer_requirements` (citation present, verification surfaced,
   unverified numbers caveated). Advisory only — it never edits the answer or
   changes routing. On a miss it logs and records the miss on the audit row.

Personas: Compliance Officer, Equity Research Analyst, Credit Analyst,
Relationship Manager (RM has no hard requirement — conciseness is soft, rail skips).

## Files changed / added
**Backend**
- `api/services/guardrails/persona_rails.py` (NEW) — `check_persona_fit(role_key,
  answer, *, verification_status, fit_threshold)` → `PersonaFitVerdict`. Pure,
  deterministic keyword/structure heuristics; fail-open; per-persona requirement
  table mirrors `conjoint.ROLES[*].answer_requirements`.
- `api/routes/conjoint.py` — added `answer_requirements` to each role in `ROLES`;
  `role_guidance_for()` now composes JTBD + `Tone & emphasis:` + `Requirements
  (must satisfy):` (requirements clause omitted when blank).
- `api/services/langgraph_engine.py` —
  - reworded the `role_instruction` injection (no longer "tone only"; keeps the
    numbers/facts guarantee; cap 1000→1200 chars for the longer composed string);
  - `_apply_persona_rail(result, role_key)` called after `_spawn_consensus`;
  - `_persona_persist_worker` + `_ensure_persona_columns` (adds `persona_role`,
    `persona_fit_status`, `persona_fit_score`, `persona_fit_missing` to
    `audit_runs` via `ADD COLUMN IF NOT EXISTS`, guarded by a process flag);
  - `run_auditable_rag(... , role_key=None)` new param.
- `api/routes/chat.py` — passes `role_key=req.role` into `run_auditable_rag`.

**Tests**
- `tests/test_persona_rails.py` (NEW) — 18 tests (guidance split + rail behaviour).

## Verification already done by author
- `tests/test_persona_rails.py` + `tests/test_guardrails.py` → 30 passed.
- `tests/test_routes_chat.py` → 7 passed.
- `import api.services.langgraph_engine` clean; `role_guidance_for` output spot-checked.

## Per-agent checklists

### MiMo (usability + performance / latency / DB cost) — REQUIRED
- [ ] Persona-fit check runs **synchronously** on the chat hot path — confirm it's
      negligible (pure regex, no LLM/IO) and adds no meaningful latency.
- [ ] DB write is **only** on a miss, in a daemon thread, on a dedicated connection
      — confirm no added write-lock pressure on the live API (see DuckDB-lock risk).
- [ ] `_ensure_persona_columns` DDL is guarded to run at most once/process — OK?
- [ ] Reworded role instruction (longer prompt, 1200-char cap) — acceptable token cost?

### DeepSeek (API + schema correctness) — REQUIRED
- [ ] `run_auditable_rag` new `role_key` param is backward-compatible (defaults None;
      all existing callers unaffected); `chat.py` wiring correct.
- [ ] `ADD COLUMN IF NOT EXISTS` migrations on `audit_runs` are safe + idempotent;
      `UPDATE … WHERE run_id = ?` parameterized; no contract change to `/auditable-rag`.
- [ ] `PersonaFitVerdict` shape + `check_persona_fit` fail-open paths (unknown role,
      empty answer, no applicable requirements, exception) all return `skipped, fit=True`.
- [ ] `result["persona_fit"]` extra key does not leak into `ChatResponse` (response
      is built explicitly) — confirm.

### Gemini (security / vulnerabilities) — REQUIRED before prod push
- [ ] `role_key` from client is server-side allow-listed (schema pattern + ROLES map),
      never raw client text into SQL or prompt.
- [ ] `persona_fit_missing` written to DB is composed from server-side labels only.

### Claude (architecture) — REQUIRED before prod push
- [ ] Rail is contained, advisory, never mutates the audited answer or routing.
- [ ] Mirrors the consensus-rail pattern (worker/connection/columns) without new coupling.
- [ ] Tone-vs-requirements split is the right seam; heuristic-vs-LLM-judge scope is honest.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-persona-fit.md`. Review only the files
> in your lane against your checklist, reading the actual diffs. Write your verdict
> to your lane file (`.<agent>/VERDICT-persona-fit.md`) using the format in
> `.deepseek/coordination/PROTOCOL.md`. Do not modify source; report findings.
