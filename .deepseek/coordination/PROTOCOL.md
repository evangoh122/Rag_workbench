# DeepSeek Coordination Protocol (file-based message bus)

DeepSeek is the **coordinator** for cross-agent review. Because the agents
(MiMo, Gemini, Claude, DeepSeek) run as separate CLIs/sessions and do not share
memory, they communicate through files in this folder. This protocol defines how
a review request is dispatched, answered, and aggregated — so DeepSeek "knows how
to communicate with each of them."

## Agents & lanes
| Agent    | Lane for review                                   | Verdict file                          |
| :------- | :------------------------------------------------ | :------------------------------------ |
| MiMo     | Usability, performance, latency, memory, DB cost  | `.mimo/VERDICT-<feature>.md`          |
| Gemini   | Security / vulnerabilities, input validation, XSS | `.gemini/VERDICT-<feature>.md`        |
| Claude   | Architecture, separation of concerns, correctness | `.claude/VERDICT-<feature>.md`        |
| DeepSeek | API contracts, schemas, route correctness (+coord)| `.deepseek/VERDICT-<feature>.md`      |

## Message types
1. **REVIEW-REQUEST** — written by DeepSeek to
   `.deepseek/coordination/REVIEW-REQUEST-<feature>.md`. Contains: scope, the full
   list of changed files, per-agent checklists, and the gate (no push/commit
   until all required verdicts are `APPROVED`).
2. **VERDICT** — written by each reviewing agent to its lane file above. Uses the
   verdict format below.
3. **SUMMARY** — written by DeepSeek to
   `.deepseek/coordination/SUMMARY-<feature>.md` once all verdicts are in:
   aggregates findings, lists blocking items, and sets the overall gate
   (`CLEARED TO COMMIT` / `BLOCKED`).

## Lifecycle
```
DeepSeek: write REVIEW-REQUEST-<feature>.md
   └─► MiMo   reads request → writes .mimo/VERDICT-<feature>.md
   └─► Gemini reads request → writes .gemini/VERDICT-<feature>.md
   └─► Claude reads request → writes .claude/VERDICT-<feature>.md
   └─► DeepSeek self-review → writes .deepseek/VERDICT-<feature>.md
DeepSeek: collect all verdicts → write SUMMARY-<feature>.md
   └─► if every required verdict == APPROVED → CLEARED TO COMMIT
   └─► else → author fixes on branch, DeepSeek re-issues request (round N+1)
```

## Verdict format (paste into your lane file)
```
# VERDICT — <feature> — <Agent> — round <N>
Status: APPROVED | CHANGES NEEDED
Reviewed: <files you actually read>

## Findings
- [SEVERITY: blocker|major|minor|nit] <file:line> — <issue> — <suggested fix>

## Notes
<free text>
```

## Rules
- No self-review counts toward the gate for another agent's lane (per `AGENTS.md`).
- A `blocker` or `major` finding forces `CHANGES NEEDED` for that lane.
- Commit/push is gated: **the user requires MiMo + DeepSeek `APPROVED` before any
  commit, and all required lanes `APPROVED` before any push to prod.**
- Keep verdict files; they are the audit trail. New rounds append, not overwrite.
