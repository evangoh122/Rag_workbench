# VERDICT — conjoint — DeepSeek — round 1

**Status:** CHANGES NEEDED

**Reviewed:** `api/routes/conjoint.py`, `api/models/schemas.py`, `api/routes/chat.py`, `api/services/langgraph_engine.py`, `frontend/src/api/conjoint.ts`, `frontend/src/components/ConjointSurvey.tsx`, `frontend/src/components/ConjointGate.tsx`, `frontend/src/pages/ConjointStudy.tsx`, `frontend/src/App.tsx`, `frontend/src/api/chat.ts`, `api/main.py`

## Findings

### [blocker] SQL injection risk via `_ensure_tables` migration loop — `api/routes/conjoint.py:57-60`

The migration loop uses string formatting with `_stmt[:48]` in the log message, but more critically, the `_stmt` variable is a hardcoded string literal, so this is not an injection vector. However, the `try/except` pattern that catches all exceptions silently could mask real SQL errors. The `ADD COLUMN IF NOT EXISTS` statements are safe because they're literal strings, but the broad exception handling is concerning.

**Fix:** Replace bare `except Exception` with `except Exception as e:` and log the actual error, not just a truncated version of the statement. Consider using `conn.execute()` with parameterized queries for the ALTER TABLE statements if they ever become dynamic.

### [blocker] `_valid_profile` rejects valid profiles with extra keys — `api/routes/conjoint.py:103-108`

The function uses `set(p.keys()) != set(_ATTR_KEYS)` which rejects profiles that have **any** extra keys beyond the four expected attributes. This is overly strict — a profile with an unexpected key (e.g., from a future schema evolution) would be rejected. The function should only check that all required keys are present and valid, ignoring extras.

**Fix:** Change to:
```python
if not all(k in p for k in _ATTR_KEYS):
    return False
```

### [major] `_counting_analysis` has a logic error in win counting — `api/routes/conjoint.py:127-143`

The function counts appearances for **both** profiles in each choice task, but only counts wins for the **chosen** profile. This is correct for the win-rate calculation. However, the `n_choices` counter is incremented for every row where `chosen in ("A", "B")`, but the appearance counting happens for both profiles regardless. This means `n_choices` counts the number of valid choices, which is correct.

**However**, there's a subtle bug: if `chosen` is not "A" or "B", the row is skipped entirely, but the `continue` statement means the appearance counts for that row are also skipped. This is correct behavior — invalid choices should be excluded entirely.

**No fix needed** — the logic is actually correct. Retracting this finding.

### [major] `complete_session` doesn't validate that the session has any responses — `api/routes/conjoint.py:218-240`

If a treatment session has zero responses (e.g., the user closed the browser before making any choices), `_preferred_levels` will return defaults (level index 0) because `_counting_analysis` returns zero appearances/wins. This silently produces a "preference" that was never actually expressed.

**Fix:** Add a check after fetching rows:
```python
if not rows:
    raise HTTPException(status_code=400, detail="No responses recorded for this session")
```

### [major] `_preferred_levels` tie-breaking is incorrect — `api/routes/conjoint.py:175-185`

The tie-breaking logic says "On a tie keep the canonical default (index 0)" but the comparison `levels[0]["utility"] >= best["utility"]` will always prefer level 0 when utilities are equal. However, `best` is computed as `max(levels, key=lambda lv: lv["utility"])`, which returns the **first** level with the maximum utility. If level 0 and level 1 have the same utility, `best` will be level 0 (since `max` returns the first max), so the tie-breaking condition `levels[0]["utility"] >= best["utility"]` will be true, and level 0 is selected. This works correctly but is confusing.

**Fix:** Simplify the tie-breaking to be explicit:
```python
best_level = max(levels, key=lambda lv: lv["utility"])
# On tie, prefer the canonical default (index 0)
if levels[0]["utility"] == best_level["utility"]:
    prefs[attr["key"]] = levels[0]["key"]
else:
    prefs[attr["key"]] = best_level["key"]
```

### [major] `role_guidance_for` returns `None` for empty string — `api/routes/conjoint.py:87-90`

The function does `(role_key or "").strip()` which converts `None` to `""`, then looks up `""` in `_ROLE_BY_KEY`. Since `""` is not a valid key, it returns `None`. This is correct behavior, but the function signature says `Optional[str]` for both input and output, which is fine.

**No fix needed** — this is correct.

### [major] `ChatRequest.role` pattern allows empty string — `api/models/schemas.py:14`

The regex pattern `^(compliance_officer|equity_research_analyst|credit_analyst|relationship_manager)?$` allows an empty string (the `?` makes the group optional). This means `role: ""` would pass validation and be treated as `None` downstream. This is acceptable since `role_guidance_for("")` returns `None`, but it's inconsistent with the `Optional[str]` type.

**Fix:** Change the pattern to `^(compliance_officer|equity_research_analyst|credit_analyst|relationship_manager)$` and rely on the `Optional[str]` type to handle `None`.

### [major] `role_guidance` is truncated to 600 chars — `api/services/langgraph_engine.py:1353`

The truncation `_rg[:600]` could cut a role guidance string mid-sentence, potentially producing grammatically incorrect or confusing instructions. The longest guidance string is the Compliance Officer's at ~200 characters, so this is unlikely to be hit in practice, but it's a latent bug.

**Fix:** Either remove the truncation (since all guidance strings are well under 600 chars) or add a comment explaining why 600 is safe.

### [minor] `_ensure_tables` creates sequence but doesn't check if it exists — `api/routes/conjoint.py:44`

`CREATE SEQUENCE IF NOT EXISTS` is used, which is correct for idempotency. However, the sequence is only used for `conjoint_responses.id`. If the table already exists but was created without the sequence (e.g., from a previous schema version), the sequence might not be properly linked.

**Fix:** This is fine — `IF NOT EXISTS` handles idempotency. No change needed.

### [minor] `_make_tasks` could produce duplicate profiles across tasks — `api/routes/conjoint.py:93-100`

The function generates random profiles independently for each task, so the same profile could appear in multiple tasks. This is acceptable for a random design but could be improved with a balanced design.

**Fix:** Not required — random design is intentional per the comment.

### [minor] `complete_session` doesn't validate `body.comment` length server-side — `api/routes/conjoint.py:218-240`

The Pydantic model `CompleteIn` has `max_length=2000` on `comment`, which is validated by FastAPI. However, the `(body.comment or None)` conversion could silently truncate if the client sends a longer string (though Pydantic would reject it).

**Fix:** No change needed — Pydantic validation handles this.

### [nit] `_valid_profile` uses `set(p.keys())` which creates a new set on every call — `api/routes/conjoint.py:103-108`

This is called for every response submission. Creating a set from `p.keys()` is O(n) where n=4, so performance impact is negligible.

**Fix:** Not needed.

### [nit] `_counting_analysis` uses `json.loads` for JSON columns — `api/routes/conjoint.py:127-143`

The function checks `isinstance(profile_a, dict)` before calling `json.loads`. This is correct for handling both dict and string representations from the database.

**Fix:** No change needed.

### [nit] `role_guidance_for` imports are circular-safe — `api/routes/conjoint.py:87-90`

The function is imported by `chat.py` via `from api.routes.conjoint import role_guidance_for`. This is a clean import with no circular dependency since `conjoint.py` doesn't import from `chat.py`.

**Fix:** No change needed.

### [nit] `_ensure_tables` migration loop logs truncated SQL — `api/routes/conjoint.py:57-60`

The log message `_stmt[:48]` truncates the SQL statement to 48 characters. For the ALTER TABLE statements, this would show `ALTER TABLE conjoint_sessions ADD COLUMN IF NOT` which is not very useful.

**Fix:** Log the full statement or a more meaningful identifier.

## Summary

The implementation is generally sound with good attention to security (parameterized queries, server-side allow-lists, Pydantic validation). The two blocker findings are the overly strict profile validation and the missing session-completion guard. The major findings are mostly about edge cases and clarity.

**Status: CHANGES NEEDED** — Address the blocker findings before merging.
