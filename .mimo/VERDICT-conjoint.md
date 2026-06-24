# VERDICT — conjoint — MiMo — round 1

**Status: CHANGES NEEDED**

**Reviewed:** All files listed in the changeset: `api/routes/conjoint.py`, `frontend/src/api/conjoint.ts`, `frontend/src/components/ConjointSurvey.tsx`, `frontend/src/components/ConjointGate.tsx`, `frontend/src/pages/ConjointStudy.tsx`, and all diffs (`api/main.py`, `api/models/schemas.py`, `api/routes/chat.py`, `api/services/langgraph_engine.py`, `frontend/src/api/chat.ts`, `frontend/src/App.tsx`).

## Findings

### 1. Survey modal re-prompts on every message after dismiss [major]

**File:** `frontend/src/App.tsx:171–180`

The `useEffect` sets `surveyPrompted = true` only when `setSurveyOpen(true)` fires. If the user dismisses the survey modal via the `onClose` handler (the X button or the backdrop) *without* submitting the usefulness vote, `markConjointCompleted()` is never called, so `hasCompletedConjoint()` returns `false` on next mount, and `surveyPrompted` remains `false`. The next assistant message ≥3 triggers the modal again — indefinitely until the user finally submits.

```tsx
// App.tsx:171-180
useEffect(() => {
    if (surveyPrompted || gateOpen || prefs === null) return;
    const answers = messages.filter((m) => m.role === 'assistant').length;
    if (answers >= 3) {
      setSurveyPrompted(true);   // ← only set here, not on dismiss
      setSurveyOpen(true);
    }
  }, [messages, surveyPrompted, gateOpen, prefs]);
```

**Suggested fix:** Set `surveyPrompted = true` inside the `onClose` callback for the survey modal so a dismissed survey is not re-triggered:

```tsx
// In the survey modal's onClose (App.tsx around line 1289)
onClose={() => { setSurveyOpen(false); setSurveyPrompted(true); }}
```

### 2. Progress bar jumps from 0 % to 100 % on final task [minor]

**File:** `frontend/src/components/ConjointSurvey.tsx:198`

The progress width uses `taskIdx / taskList.length`, so for 6 tasks the sequence is 0%, 0%, 0%, 0%, 0%, 100% (integer division after `taskIdx` reaches 5 — actually no, it's JS float division, so it's 0%, 16.7%, 33%, 50%, 66.7%, 83.3%). It never reaches 100% while tasks are showing. The bar is purely cosmetic but gives a misleading sense of "not done yet" on the final choice task.

**Suggested fix:** Use `(taskIdx + 1) / taskList.length * 100` so it reaches 100% on the last task.

### 3. `/results` full-table scan of `conjoint_responses` [minor]

**File:** `api/routes/conjoint.py:319`

```python
rows = conn.execute(
    "SELECT profile_a, profile_b, chosen FROM conjoint_responses"
).fetchall()
```

This is an unfiltered full-table scan. The `idx_conjoint_responses_session` index (line 101) only helps the point-lookup path in `/complete`. At current scale (dev/study, low hundreds of rows) this is fine, but it will degrade as responses accumulate. The single-row `SELECT` + `INSERT` on `/response` and `/session` are cheap; the concern is only the aggregate `/results` endpoint.

**Suggested fix:** Add a comment noting this is acceptable at study scale, or pre-compute/cache the aggregate on `/complete` (write-on-complete pattern). No index change needed for a read-heavy, write-rare aggregate.

### 4. localStorage reads on mount are already memoized [nit — no action]

**File:** `frontend/src/App.tsx:99–100`

`prefs` and `gateOpen` use lazy initializers (`() => loadConjointPrefs()`) so localStorage is read exactly once on mount. `surveyPrompted` likewise. The later `useEffect` deps on `prefs` are references to the state object, not re-reads. This is fine.

### 5. `role` wiring on the chat hot path — no blocking work [nit — no action]

**File:** `api/routes/chat.py:197`

`role_guidance_for(req.role)` is a dict lookup on a 4-item dict (constant time, synchronous). It returns a static string that is passed through `run_auditable_rag` → `GraphState` → `qualitative_output_node` where it's sliced to 600 chars and interpolated into the existing system prompt string. No DB calls, no LLM calls, no I/O. No hot-path concern.

### 6. Control vs treatment comprehensibility [nit — no action]

**Files:** `ConjointGate.tsx`, `ConjointSurvey.tsx`

The gate clearly labels "Standard app" (control) vs "Personalize by role" (treatment) with distinct visual treatments (muted vs accent). The survey's task instruction ("Pick the bundle you'd rather receive…") is clear. The post-completion screen correctly distinguishes the two arms in its messaging. The `ConjointStudy` page disclaims the self-selected arm assignment as observational. Flow is clear; users cannot get stuck (error states have retry + close, close button present on all interactive phases).

---

## Notes

- The `_preferred_levels` tie-breaking logic (`conjoint.py:256`) defaults to level index 0 on ties, which is a reasonable canonical default but means `standard` always wins a tie with `role_based` for `answer_basis`, `direct` wins ties for `answer_style`, etc. Worth documenting but not a usability issue.
- The `showEvidence` / `showExplain` / `promptsGuided` derived values in App.tsx correctly gate the evidence panels, explanations, and follow-up label text, giving treatment participants a visibly different experience matching their conjoint-derived prefs. This is well-implemented.
