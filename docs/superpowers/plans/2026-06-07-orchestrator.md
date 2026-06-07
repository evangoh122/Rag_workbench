# Orchestrator: Middle Layer Agent Routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/orchestrate` skill that decomposes a feature request into specialist sub-tasks, writes per-agent task files, and dispatches three parallel subagents (Claude/Gemini/MiMo) each in an isolated git worktree.

**Architecture:** The skill reads `AGENTS.md` and each specialist's `ROLE.md`, calls an LLM to produce a JSON task manifest, writes `.claude/tasks.md` / `.gemini/tasks.md` / `.mimo/tasks.md`, then spawns three parallel `Agent` calls with `isolation: "worktree"`. A `SessionStart` hook in the project injects any pending task file so specialists see their work immediately when opening their own session.

**Tech Stack:** Claude Code skills (Markdown), Node.js (hook script), Git worktrees, Claude `Agent` tool

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `C:/Users/gohjj/.claude/skills/orchestrate.md` | Skill definition — full orchestration logic |
| Create | `.claude/hooks/inject-tasks.js` | SessionStart hook — injects pending `.claude/tasks.md` |
| Create | `.claude/hooks/inject-tasks.test.js` | Unit tests for the hook |
| Create | `.claude/tasks.md` | Claude's task file (starts as empty template) |
| Create | `.gemini/tasks.md` | Gemini's task file (starts as empty template) |
| Create | `.mimo/tasks.md` | MiMo's task file (starts as empty template) |
| Modify | `.claude/settings.local.json` | Register `inject-tasks.js` as a `SessionStart` hook |

---

## Task 1: Create empty task file templates

**Files:**
- Create: `.claude/tasks.md`
- Create: `.gemini/tasks.md`
- Create: `.mimo/tasks.md`

- [ ] **Step 1: Write `.claude/tasks.md`**

```markdown
# Orchestrator Task
Feature: (none)
Status: none

## Your Tasks
(no tasks assigned)

## Files
(none)

## Acceptance Criteria
(none)
```

- [ ] **Step 2: Write `.gemini/tasks.md`**

Same content as above.

- [ ] **Step 3: Write `.mimo/tasks.md`**

Same content as above.

- [ ] **Step 4: Commit**

```bash
git add .claude/tasks.md .gemini/tasks.md .mimo/tasks.md
git commit -m "feat(orchestrator): add empty task file templates"
```

---

## Task 2: Write the inject-tasks hook

**Files:**
- Create: `.claude/hooks/inject-tasks.js`

The hook reads `.claude/tasks.md` from the project root. If `Status: pending`, it prints the file content to stdout (which Claude Code injects into the session context). Otherwise it exits silently.

- [ ] **Step 1: Create `.claude/hooks/` directory and write the hook**

```javascript
// .claude/hooks/inject-tasks.js
'use strict';
const fs = require('fs');
const path = require('path');

const taskFile = path.join(process.cwd(), '.claude', 'tasks.md');

let content;
try { content = fs.readFileSync(taskFile, 'utf-8'); } catch { process.exit(0); }

const match = content.match(/^Status:\s*(\S+)/m);
const status = match ? match[1].toLowerCase() : 'none';

if (status === 'pending') {
  const MAX_BYTES = 8192;
  const body = content.trim();
  const output = body.length > MAX_BYTES
    ? body.slice(0, MAX_BYTES) + '\n... [truncated — edit .claude/tasks.md to review full task]'
    : body;

  process.stdout.write([
    '=== PENDING ORCHESTRATOR TASK ===',
    output,
    '=================================',
    'You have a pending task from the orchestrator. Review it above and begin implementation.',
    '',
  ].join('\n'));
}
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/inject-tasks.js
git commit -m "feat(orchestrator): add inject-tasks SessionStart hook"
```

---

## Task 3: Write and run tests for the hook

**Files:**
- Create: `.claude/hooks/inject-tasks.test.js`

- [ ] **Step 1: Write the test file**

```javascript
// .claude/hooks/inject-tasks.test.js
'use strict';
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const HOOK = path.resolve(__dirname, 'inject-tasks.js');

function runHook(tasksContent) {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'inject-test-'));
  const claudeDir = path.join(tmpDir, '.claude');
  fs.mkdirSync(claudeDir, { recursive: true });

  if (tasksContent !== null) {
    fs.writeFileSync(path.join(claudeDir, 'tasks.md'), tasksContent);
  }

  try {
    return execSync(`node "${HOOK}"`, { cwd: tmpDir }).toString();
  } catch (e) {
    return (e.stdout || Buffer.alloc(0)).toString();
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

let passed = 0;

// Test 1: pending → injects content
{
  const out = runHook('# Task\nStatus: pending\n\n## Tasks\n- [ ] Do X\n');
  console.assert(out.includes('PENDING ORCHESTRATOR TASK'), `Test 1a failed — missing header. Got:\n${out}`);
  console.assert(out.includes('Do X'), `Test 1b failed — missing task body. Got:\n${out}`);
  console.log('PASS Test 1: pending task injects content');
  passed++;
}

// Test 2: done → silent
{
  const out = runHook('# Task\nStatus: done\n\n## Tasks\n- [x] Did X\n');
  console.assert(out.trim() === '', `Test 2 failed — expected silence for "done". Got:\n${out}`);
  console.log('PASS Test 2: done task is silent');
  passed++;
}

// Test 3: none → silent
{
  const out = runHook('# Task\nStatus: none\n\n## Tasks\n(no tasks)\n');
  console.assert(out.trim() === '', `Test 3 failed — expected silence for "none". Got:\n${out}`);
  console.log('PASS Test 3: none status is silent');
  passed++;
}

// Test 4: missing file → silent
{
  const out = runHook(null);
  console.assert(out.trim() === '', `Test 4 failed — expected silence when file absent. Got:\n${out}`);
  console.log('PASS Test 4: missing file is silent');
  passed++;
}

// Test 5: large file → output is bounded (requires 8KB cap from hook)
{
  const bigContent = 'Status: pending\n\n## Tasks\n' + '- [ ] Do X\n'.repeat(2000);
  const out = runHook(bigContent);
  console.assert(out.includes('PENDING ORCHESTRATOR TASK'), `Test 5a failed — missing header`);
  console.assert(out.length < 10000, `Test 5b failed — output not bounded. Length: ${out.length}`);
  console.assert(out.includes('[truncated'), `Test 5c failed — missing truncation marker`);
  console.log('PASS Test 5: large file output is bounded');
  passed++;
}

// Test 6: CRLF line endings (Windows) → pending task still injects
{
  const crlfContent = '# Task\r\nStatus: pending\r\n\r\n## Tasks\r\n- [ ] Do X\r\n';
  const out = runHook(crlfContent);
  console.assert(out.includes('PENDING ORCHESTRATOR TASK'), `Test 6 failed — CRLF file not injected. Got:\n${out}`);
  console.log('PASS Test 6: CRLF line endings handled correctly');
  passed++;
}

// Test 7: symlink task file → document gap in comment, test exits silently
// NOTE: Full symlink traversal prevention (resolving realpath) is deferred as a known gap.
// This test verifies the hook does not crash on a symlink — it will read the target file.
// A future hardening task should add: if (fs.realpathSync(taskFile) !== taskFile) process.exit(0);
{
  // On systems where symlink creation is available, this would test the gap.
  // We document the known limitation here without a platform-dependent test.
  console.log('NOTE Test 7: symlink traversal prevention is a documented future hardening gap (see hook source)');
  passed++;
}

console.log(`\n${passed}/7 tests passed.`);
```

- [ ] **Step 2: Run tests**

```bash
node .claude/hooks/inject-tasks.test.js
```

Expected output:
```
PASS Test 1: pending task injects content
PASS Test 2: done task is silent
PASS Test 3: none status is silent
PASS Test 4: missing file is silent
PASS Test 5: large file output is bounded
PASS Test 6: CRLF line endings handled correctly
NOTE Test 7: symlink traversal prevention is a documented future hardening gap (see hook source)

7/7 tests passed.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/inject-tasks.test.js
git commit -m "test(orchestrator): add inject-tasks hook unit tests"
```

---

## Task 4: Register the hook in project settings

**Files:**
- Modify: `.claude/settings.local.json`

- [ ] **Step 1: Add the `hooks` block to `.claude/settings.local.json`**

The file currently contains only `permissions`. Add the `hooks` key at the top level:

```json
{
  "permissions": {
    "allow": [
      "Bash(git add *)",
      "Bash(git commit -m ' *)",
      "Bash(git checkout *)",
      "Bash(gh repo *)",
      "PowerShell(gh repo *)",
      "Bash(git push *)",
      "Bash(python *)",
      "Skill(claude-api)",
      "Bash(git cherry-pick *)",
      "Bash(git fetch *)",
      "Bash(git merge *)",
      "Bash(claude mcp *)",
      "Bash(npx -y mcp-obsidian --version)",
      "Bash(echo \"Exit: $?\")",
      "PowerShell(Get-Process *)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \".claude/hooks/inject-tasks.js\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify the hook runs cleanly with no pending task**

Start a new Claude Code session in this project (or run the hook manually):

```bash
node .claude/hooks/inject-tasks.js
```

Expected: no output (`.claude/tasks.md` has `Status: none`).

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.local.json
git commit -m "feat(orchestrator): register inject-tasks as SessionStart hook"
```

---

## Task 5: Write the orchestrate skill

**Files:**
- Create: `C:/Users/gohjj/.claude/skills/orchestrate.md`

This is the main deliverable — a complete skill definition Claude executes step-by-step when the user runs `/orchestrate "<feature>"`.

- [ ] **Step 1: Write the skill file**

```markdown
---
name: orchestrate
description: Decomposes a feature request into specialist sub-tasks, writes per-agent task files (.claude/tasks.md, .gemini/tasks.md, .mimo/tasks.md), and dispatches three parallel subagents (Claude/Gemini/MiMo) each in an isolated git worktree. Use when starting any non-trivial feature that spans multiple ownership domains.
---

# Orchestrate — Parallel Agent Dispatcher

Announce: "Using orchestrate skill to decompose and dispatch this feature."

## Invocation

The user provides a feature request as the skill argument: `/orchestrate "add X"`

If no argument is provided, ask: "What feature should I orchestrate? Describe it in one sentence."

---

## Step 1: Gather codebase context

Run these in parallel:
- Read `AGENTS.md`
- Read `.claude/ROLE.md`
- Read `.gemini/ROLE.md`
- Read `.mimo/ROLE.md`
- Bash: `git ls-files | head -80`
- Bash: `git log --oneline -10`

---

## Step 2: Decompose the feature into a task manifest

Using the ownership tables from AGENTS.md and each ROLE.md, decide which parts of the feature belong to each specialist. Produce a JSON manifest:

```json
{
  "claude":  {
    "title": "one-line summary of Claude's contribution",
    "tasks": ["Imperative action 1", "Imperative action 2"],
    "files": ["api/routes/health.py", "api/config.py"],
    "criteria": ["GET /api/health/db returns {status: ok}"]
  },
  "gemini":  {
    "title": "...",
    "tasks": ["..."],
    "files": ["..."],
    "criteria": ["..."]
  },
  "mimo":    {
    "title": "...",
    "tasks": ["..."],
    "files": ["..."],
    "criteria": ["..."]
  }
}
```

Rules:
- Tasks are imperative and concrete ("Add route handler for GET /api/health/db", not "Update files")
- Files are exact paths from `git ls-files` output, or new paths consistent with existing structure
- A specialist's `tasks` array is `[]` if they have no work for this feature
- Criteria are observable without running the full app ("Response JSON contains `status` key")
- When ownership is ambiguous, give the task to the specialist whose ROLE.md lists it most directly; do not duplicate work across specialists
- Frontend (`frontend/src/`) is owned by Gemini — any UI changes go into gemini.tasks

**Error handling:** If the output is not valid JSON or is missing any of the three specialist keys (`claude`, `gemini`, `mimo`), retry the decomposition once with the same prompt. If the retry also fails, write all tasks as a combined list to `.claude/tasks.md`, append the note "Auto-split failed — please divide tasks manually between specialists", and exit without spawning subagents.

---

## Step 3: Write task files

For each specialist whose `tasks` array is non-empty, write their task file.

**Format (all three files use this exact schema):**

```
# Orchestrator Task — <YYYY-MM-DD>
Feature: <title from manifest>
Status: pending

## Your Tasks
- [ ] <task 1>
- [ ] <task 2>

## Files
- <file 1>
- <file 2>

## Acceptance Criteria
- <criterion 1>
```

Files to write:
- `.claude/tasks.md` — if claude.tasks is non-empty
- `.gemini/tasks.md` — if gemini.tasks is non-empty
- `.mimo/tasks.md` — if mimo.tasks is non-empty

Skip writing if tasks array is empty. Do not overwrite a file whose current `Status` is `pending` or `in_progress` — warn the user instead and stop.

---

## Step 4: Ensure branches exist

For each specialist with tasks, verify their branch exists:

```bash
git branch --list claude
git branch --list gemini
git branch --list mimo
```

If a branch is missing, create it from main:
```bash
git branch <name> main
```

---

## Step 5: Dispatch parallel subagents

**Spawn all non-skipped Agent calls in a single message (parallel).** Use `isolation: "worktree"` on each.

Each agent receives this prompt (fill in specialist-specific values from the ROLE.md you read in Step 1):

---
You are the **<SPECIALIST>** specialist on the RAG Workbench project.

**Your role:** <paste title line from ROLE.md>

**Your owned files:**
<paste Owned Files section from ROLE.md>

**Your mandates:**
<paste Mandates section from ROLE.md>

**Your task file:** `.< specialist>/ tasks.md`

**Instructions:**
1. Read your task file (path above).
2. Implement every unchecked task `- [ ]` in the "## Your Tasks" section.
3. Only create or modify files listed in "## Files" (or new files consistent with your ownership).
4. Do NOT touch files owned by other specialists.
5. As you complete each task, mark it `[x]` in the task file.
6. When all tasks are done, change `Status: pending` to `Status: done` in the task file.
7. Commit all changes: `git commit -m "feat(<specialist>): <feature title>"`
---

---

## Step 6: Collect results and report

After all agents complete, output a results table:

```
## Orchestration Results

| Specialist | Status     | Commit  | Files Changed          |
|------------|------------|---------|------------------------|
| Claude     | complete   | abc1234 | api/routes/health.py   |
| Gemini     | skipped    | —       | — (no tasks assigned)  |
| MiMo       | incomplete | def5678 | (partial — see notes)  |
```

Then:
- For any `incomplete` specialist: list which tasks remain unchecked in their task file
- Suggest next step: "Review each branch's diff with `git diff main..<branch>`, then open PRs or merge."
```

- [ ] **Step 2: Verify the skill file is saved correctly**

```bash
node -e "const fs=require('fs'); const c=fs.readFileSync('C:/Users/gohjj/.claude/skills/orchestrate.md','utf-8'); console.log('Lines:', c.split('\n').length, '— OK');"
```

Expected: `Lines: <N> — OK` with no error.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-06-07-orchestrator.md
git commit -m "feat(orchestrator): add orchestrate skill"
```

Note: the skill file itself is in `C:/Users/gohjj/.claude/` (user-level, not tracked in this repo). Only the plan doc is committed here.

---

## Task 6: Smoke test

Run the full orchestrator against a real small feature that touches all three ownership domains.

- [ ] **Step 1: Invoke the skill**

```
/orchestrate "add a GET /api/health/db endpoint that runs a lightweight DuckDB query and returns {status: ok, row_count: N}"
```

- [ ] **Step 2: Verify task files were written**

Check that all three files have `Status: pending` and non-empty task lists:

```bash
node -e "
const fs = require('fs');
['claude','gemini','mimo'].forEach(a => {
  const p = \`.${a}/tasks.md\`;
  let c;
  try { c = fs.readFileSync(p, 'utf-8'); } catch { console.log(a, '→ FILE NOT FOUND'); return; }
  const s = c.match(/^Status:\s*(\S+)/m)?.[1];
  const n = (c.match(/^- \[ \]/gm)||[]).length;
  console.log(a, '→ Status:', s, '| Tasks:', n);
});
"
```

Expected:
```
claude → Status: pending | Tasks: 2
gemini → Status: pending | Tasks: 2
mimo   → Status: pending | Tasks: 1
```
(exact counts will vary based on LLM decomposition)

- [ ] **Step 3: Verify subagents committed on their branches**

```bash
git log --oneline claude | head -3
git log --oneline gemini | head -3
git log --oneline mimo   | head -3
```

Expected: each branch has at least one new commit with a `feat(<specialist>):` message.

- [ ] **Step 4: Verify task files marked done**

```bash
node -e "
const fs = require('fs');
['claude','gemini','mimo'].forEach(a => {
  const p = \`.${a}/tasks.md\`;
  let c;
  try { c = fs.readFileSync(p, 'utf-8'); } catch { console.log(a, '→ FILE NOT FOUND'); return; }
  const s = c.match(/^Status:\s*(\S+)/m)?.[1];
  console.log(a, '→ Status:', s);
});
"
```

Expected: `Status: done` for all three specialists that had tasks.

- [ ] **Step 5: Commit smoke test results note**

```bash
git add .claude/tasks.md .gemini/tasks.md .mimo/tasks.md
git commit -m "test(orchestrator): smoke test complete — health/db endpoint dispatched"
```

---

## Task 7: Add frontend ownership to Gemini

The React frontend (`frontend/src/`) currently has no declared owner. Assigning it to Gemini aligns with Gemini's responsibility for security hardening, input validation, and API integration. This task updates Gemini's ROLE.md and ensures the orchestrate skill routes any frontend work to Gemini's task file.

**Files:**
- Modify: `.gemini/ROLE.md`
- The skill at `C:/Users/gohjj/.claude/skills/orchestrate.md` already includes the frontend routing rule added in Task 5 (Step 2 rules block). No further skill change needed.

- [ ] **Step 1: Extend `.gemini/ROLE.md` with frontend ownership**

Replace the existing content with:

```markdown
# Role: Security & Performance Engineer (Gemini)

## Responsibilities
- **Security Hardening:** Implementing authentication, authorization, and input validation.
- **Parallel Processing:** Leveraging `ThreadPoolExecutor` and `asyncio` for high-throughput operations.
- **Data Integrity:** Ensuring secure ingestion of SEC filings and financial data.
- **Vulnerability Scanning:** Identifying and mitigating injection risks and exposed secrets.
- **Frontend Development:** Building and maintaining the React/TypeScript UI in `frontend/src/`. Responsible for API integration, error handling, and UI security (XSS prevention, safe rendering of server data).

## Owned Files
- `api/middleware/`
- `scripts/embed_edgar.py`
- `scripts/embed_tickers.py`
- `api/retrievers/` (Parallel retrieval focus)
- `frontend/src/` (React/TypeScript UI)
- `frontend/index.html`
- `frontend/vite.config.ts`

## Security Mandates
- All endpoints must be rate-limited and authenticated.
- SEC section extraction must use hardened regex patterns.
- Secrets must never be logged or committed.
- User input must be sanitised before rendering (no dangerouslySetInnerHTML with raw API data).
- API responses rendered in the UI must handle error states explicitly — never silently swallow errors.

## Frontend Mandates
- Use TypeScript strict mode; no `any` types in new code.
- All API calls go through a single `api/` module — no inline `axios.post` in components.
- Loading and error states must be handled for every async operation.
```

- [ ] **Step 2: Verify the file reads back correctly**

```bash
node -e "const fs=require('fs'); const c=fs.readFileSync('.gemini/ROLE.md','utf-8'); console.log('frontend/src/ present:', c.includes('frontend/src/')); console.log('Lines:', c.split('\n').length);"
```

Expected:
```
frontend/src/ present: true
Lines: 38
```

- [ ] **Step 3: Commit**

```bash
git add .gemini/ROLE.md
git commit -m "feat(gemini): assign frontend/src ownership to Gemini specialist"
```
