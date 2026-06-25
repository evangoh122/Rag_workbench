# VERDICT - mindforge - DeepSeek - round 1
Status: CHANGES NEEDED
Reviewed: .deepseek/coordination/PROTOCOL.md; .deepseek/coordination/REVIEW-REQUEST-mindforge.md; api/services/guardrails/consensus_rails.py; docs/mindforge-risk-alignment.md; docs/specs/eval-layer-spec.md; api/services/confidence_scorer.py; api/services/drift_detection.py; api/routes/audit.py; api/middleware/auth.py; api/services/guardrails/output_rails.py; api/services/guardrails/input_rails.py; api/services/guardrails/execution_rails.py; api/config.py; api/db/review_queue.py; api/services/langgraph_engine.py; api/routes/chat.py; api/services/semantic_validator.py; api/services/xbrl_cross_validator.py

## Findings
- [SEVERITY: major] docs/mindforge-risk-alignment.md:41 - The doc says "every answer routes to AUTO / SAMPLED_REVIEW / ESCALATE", but the actual API has `/api/chat/sql`, `/api/chat/rag`, `/api/chat/graph-rag`, and the conversational fast path in `/api/chat/auditable-rag` that return without eval routing, and `eval_node` also skips scoring when no XBRL fields are extracted. This overstates the live Model Risk control surface. - Scope the claim to the auditable RAG path when XBRL fields are available, or explicitly list the bypass/skipped paths as current gaps.
- [SEVERITY: major] docs/mindforge-risk-alignment.md:69 - The doc claims "No persistent user data on the runtime host", but `audit_runs` persists `question` and `answer` text in the persistent review/runtime DB and the code comments state those audit records must survive restarts. User prompts can contain user-provided data even if the corpus is public SEC filings. - Reword to "no separate user profile/customer store" and state that audit logs persist question/answer text on the private runtime/review dataset, with corresponding privacy caveat.
- [SEVERITY: minor] docs/mindforge-risk-alignment.md:45 - The doc says "Eight deterministic always-escalate triggers", but `confidence_scorer.ALL_TRIGGERS` currently registers ten predicates: the listed eight plus `out_of_range` and `downstream_action`. The spec section also describes the broader trigger set. - Update the count and examples, or remove the fixed number and reference the current trigger list.
- [SEVERITY: minor] docs/mindforge-risk-alignment.md:89 - The dual-model consensus control says material divergence routes to human review, but the review request and code confirm `consensus_rails.py` is standalone and not wired into `chat.py`, `langgraph_engine.py`, `ChatResponse`, or `audit_runs` yet. The gaps section does mention audit persistence and model swap, but not clearly that the rail does not currently affect live routing. - Add "not yet wired into the request path/routing" to the control or Honest gaps section.

## Notes
`check_consensus` and `ConsensusVerdict` are coherent for the standalone contract. Fail-open paths return `agree=True, skipped=True`; the threshold logic is correct (`score <= divergence_threshold` agrees); numeric comparison is regex/set based with no eval/SQL execution; no-number and secondary-only-number cases produce no divergence; `$1,200` and `1200` normalize to the same token.

The cited security/audit implementation mostly matches the doc: auth uses tiered keys and `hmac.compare_digest`; admin hard-fails without `ADMIN_API_KEY`; input/output/execution rails implement the referenced regex/heuristic checks; audit list/get use parameterized SQL branches; `audit_runs` columns match the cited source_docs/chunk_ids/xbrl_facts_cited/math_steps/confidence/eval_route/verification_status/model_used fields.

---

# VERDICT — mindforge — DeepSeek — round 3 (final)
Status: APPROVED
Reviewed: api/services/guardrails/consensus_rails.py; _apply_consensus_rail + call
site (langgraph_engine.py:2009) in run_auditable_rag; docs/mindforge-risk-alignment.md
(review driven via the DeepSeek API on user instruction)

## Findings
- none

## Notes
Code and doc consistent. Risk-gating, fail-open, divergence, route override
(AUTO→SAMPLED_REVIEW), audit persistence (consensus_* columns), and review-queue
insertion all match documented behavior. Correlated-model limitation honestly
disclosed in both code comments and doc.

## Resolution of round 1 + round 2
- r1 major (routing "every answer" overstated) → FIXED: §1 scoped to auditable-RAG
  path; non-scored paths listed.
- r1 major (persistence vs "no persistent user data") → FIXED: §2 states audit_runs
  persists question+answer as an audit trade-off; privacy claim scoped.
- r1 minor (8 vs 10 triggers) → FIXED: doc now says 10, enumerated.
- r1 minor (not-wired clarity) → then wired; doc §3 updated to "wired and active".
- r2 major (docstring implied module produces primary answer) → FIXED: docstring
  clarifies primary_answer is passed in.
- r2 major (call site not shown) → FALSE POSITIVE from a truncated review excerpt;
  call confirmed at langgraph_engine.py:2009. Re-reviewed with call site → APPROVED.

---

# VERDICT — mindforge — DeepSeek — round 4 (final, async + risk/compliance)
Status: APPROVED
Reviewed: consensus_rails.py (should_run_consensus risk/compliance category);
_spawn_consensus / _consensus_worker + call site in langgraph_engine.py;
docs/mindforge-risk-alignment.md (async + risk/compliance rewrite)

## Findings
- none

## Notes
Code correctly implements the documented design: fail-open, risk-gating via
should_run_consensus (incl. the new risk/compliance category), async fire-and-forget
with zero response latency, eventual consistency for audit/review updates, and the
divergence threshold logic. All doc claims in mindforge-risk-alignment.md are
supported by the code, including the correlated-model caveat and planned frontier
swap. (Codex r1 lineage finding is moot under async — response carries its
pre-consensus route, no contradiction within a single response.)

---

# VERDICT — mindforge — DeepSeek — round 5 (advice rail + concurrency)
Status: APPROVED
Reviewed: dialog_rails.py (advice rail), consensus_rails.py, _consensus_worker +
get_new_review_connection in langgraph_engine.py, docs/mindforge-risk-alignment.md

## Findings
- none

## Notes
Advice rail runs before the on-topic financial-keyword check; patterns precise, no
catastrophic backtracking. Concurrency fix uses a dedicated per-thread review
connection. Doc claims align with implementation. (Note: an earlier DeepSeek note
referenced ".cursor()"; the final code uses db_manager.get_new_review_connection()
— an independent connection — which is the stronger fix.)

---

# VERDICT — mindforge — DeepSeek — round 6 (Codex r3 fix)
Status: APPROVED
Reviewed: dialog_rails.py (financial-keyword allowlist now precedes off-topic),
tests/test_guardrails.py, consensus_rails.py, langgraph_engine.py wiring, doc

## Findings
- none

## Notes
Advice rail patterns precise and fire before the financial-keyword allowlist;
financial allowlist now precedes the off-topic denylist (fixes Codex r3 "test"
false positive). Concurrency fix uses an independent per-thread DuckDB connection.
Doc-vs-code accuracy holds across all claims.
