# Orchestrator: Middle Layer Agent Routing

**Date:** 2026-06-07
**Status:** Approved
**Scope:** RAG Workbench — multi-agent development workflow

---

## Overview

A `/orchestrate` skill that receives a feature request, decomposes it into specialist sub-tasks, writes per-agent task files, and dispatches three parallel subagents — one per specialist (Claude, Gemini, MiMo) — each working in an isolated git worktree on their own branch. A `SessionStart` hook ensures specialists see their pending tasks automatically when they open their own session.

---

## Architecture

```
/orchestrate "<feature request>"
        │
        ├─ 1. Read AGENTS.md + file tree + recent git log
        │
        ├─ 2. LLM decompose → task manifest (JSON)
        │         claude:  { title, tasks[], files[], criteria[] }
        │         gemini:  { title, tasks[], files[], criteria[] }
        │         mimo:    { title, tasks[], files[], criteria[] }
        │
        ├─ 3. Write task files
        │         .claude/tasks.md   (Status: pending)
        │         .gemini/tasks.md   (Status: pending)
        │         .mimo/tasks.md     (Status: pending)
        │
        └─ 4. Spawn 3 parallel Agent subagents
                  each in isolated worktree on their branch
                  each reads its task file, implements, commits
                        │
                        └─ 5. Collect results → report diffs + blockers
```

---

## Components

### `/orchestrate` skill

File: `.claude/skills/orchestrate.md`

Responsibilities:
- Read `AGENTS.md` and key source files to build codebase context
- Call LLM to decompose the feature request into a per-specialist task manifest
- Validate manifest structure; retry once on malformed output
- Write `.claude/tasks.md`, `.gemini/tasks.md`, `.mimo/tasks.md`
- Ensure each specialist's branch exists (create from `main` if not)
- Dispatch three parallel `Agent` calls with `isolation: "worktree"`
- Collect results; emit a final report showing each specialist's commit(s), changed files, and any blockers

### Task files

One file per specialist directory. Written by the orchestrator; read by the subagent and (via hook) by any human specialist who opens a session.

Format:
```markdown
# Orchestrator Task — YYYY-MM-DD
Feature: <one-line description>
Status: pending

## Your Tasks
- [ ] <imperative, concrete action>
- [ ] ...

## Files
- <path to touch>
- ...

## Acceptance Criteria
- <observable outcome>
- ...
```

`Status` field transitions: `pending` → `in_progress` → `done`.

### SessionStart hook addition

When a specialist opens a session, the hook checks if their task file exists and has `Status: pending`. If so, it injects the file content into the session context so the specialist sees their tasks immediately without searching.

Hook target files:
- `.claude/tasks.md` — injected for Claude sessions
- `.gemini/tasks.md` — injected for Gemini sessions
- `.mimo/tasks.md` — injected for MiMo sessions

---

## Task Decomposition

The orchestrator sends this context to the LLM:

- Full content of `AGENTS.md` (ownership table, responsibilities)
- `git ls-files` output (file tree)
- `git log --oneline -10` (recent history)
- User's feature request

Expected output — strict JSON:
```json
{
  "claude":  { "title": "...", "tasks": ["..."], "files": ["..."], "criteria": ["..."] },
  "gemini":  { "title": "...", "tasks": ["..."], "files": ["..."], "criteria": ["..."] },
  "mimo":    { "title": "...", "tasks": ["..."], "files": ["..."], "criteria": ["..."] }
}
```

If a specialist has no work for this feature, their `tasks` array is empty and their Agent call is skipped.

---

## Parallel Subagent Dispatch

Each Agent subagent receives:
- Their specialist identity (role, owned paths, branch name) from `AGENTS.md`
- The absolute path to their task file
- Instruction to read the task file, implement each task, mark items `[x]`, update `Status: done`, and commit on their branch

Each call uses `isolation: "worktree"` so branches cannot interfere. If a branch does not exist, the orchestrator creates it from `main` before dispatch.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| LLM returns malformed JSON | Retry once; on second failure write all tasks to `.claude/tasks.md` and ask user to split manually |
| Specialist task list is empty | Skip that Agent call; note in final report as "no work" |
| Subagent fails mid-task | Worktree preserved with partial commits; report flags specialist as `incomplete` |
| Branch does not exist | Created from `main` before dispatch |

---

## Out of Scope (this iteration)

- Cross-specialist review pass (Approach 3 upgrade path)
- Automated conflict resolution between branches
- CI/CD integration
- Merge orchestration

---

## Smoke Test

Run: `/orchestrate "add a /api/health/db endpoint"`

This touches all three domains:
- Claude: new route in `api/routes/`
- Gemini: auth + rate-limit hook on new route
- MiMo: DB health-check query optimisation

Verify:
1. Three task files written with `Status: pending`
2. Three subagents commit on their respective branches
3. Final report lists each specialist's commit SHA and changed files
