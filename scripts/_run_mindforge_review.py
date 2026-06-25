"""One-off: get MiMo + DeepSeek to review the mindforge/consensus-rail change.

Sends each model its lane-specific code + checklist and prints the verdict.
Not part of the app; safe to delete after the review.
"""
import os
import sys
from openai import OpenAI
from api.config import Config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def slice_between(text, start_marker, end_marker):
    i = text.index(start_marker)
    j = text.index(end_marker, i)
    return text[i:j]


consensus = read("api/services/guardrails/consensus_rails.py")
dialog = read("api/services/guardrails/dialog_rails.py")
doc = read("docs/mindforge-risk-alignment.md")
engine = read("api/services/langgraph_engine.py")
wiring = slice_between(engine, "def _ensure_consensus_columns", "def run_auditable_rag")
# Include the actual call site so reviewers can see the rail IS invoked.
ci = engine.index("_spawn_consensus(query, result)")
wiring += (
    "\n\n# ---- call site inside run_auditable_rag (context) ----\n"
    + engine[engine.rfind("\n", 0, ci - 200):ci + 60]
)

VERDICT_FORMAT = (
    "Respond in EXACTLY this format:\n"
    "Status: APPROVED | CHANGES NEEDED\n"
    "Findings:\n"
    "- [SEVERITY: blocker|major|minor|nit] <file:approx_line> — <issue> — <suggested fix>\n"
    "(write 'none' under Findings if APPROVED with nothing to flag)\n"
    "Notes: <one or two lines>\n"
)

INTENT = (
    "CONTEXT: A risk-gated dual-model consensus rail for an auditable SEC-filing RAG app. "
    "The DeepSeek+MiMo pairing is a DELIBERATE EXAMPLE (production swaps the secondary to a "
    "different-lineage frontier model via CONSENSUS_SECONDARY_MODEL — documented, not a bug). "
    "By explicit user direction the rail runs ASYNCHRONOUSLY (fire-and-forget): _spawn_consensus "
    "snapshots what it needs and starts a background daemon thread (_consensus_worker), so it adds "
    "ZERO latency to the response; the live response intentionally does NOT carry the consensus "
    "result, and the audit_runs row + review queue converge AFTER the response (eventual "
    "consistency by design — this is intended, not a bug). It is risk-gated by should_run_consensus() "
    "to high-risk questions only: already-high-stakes routes, hard multi-year/trend, peer "
    "comparison, and RISK/COMPLIANCE questions (litigation, material weakness, going concern, "
    "covenants, regulatory, etc.). Fail-open (any error -> SKIPPED, never breaks chat). On "
    "material numeric disagreement it escalates AUTO->SAMPLED_REVIEW, inserts a review-queue "
    "entry, and persists consensus_* to audit_runs.\n\n"
    "NEW THIS ROUND: (1) An investment-ADVICE dialog rail (dialog_rails.py) HARD-REFUSES "
    "questions seeking recommendations/personal-actions/price-predictions ('should I buy?', "
    "'price target', 'is X a good investment', 'will it go up') with a 'not a licensed "
    "investment adviser' disclaimer, while letting factual filing questions through. Wired "
    "into chat._apply_input_rails (covers all chat endpoints). (2) CONCURRENCY FIX (Codex r2 + "
    "MiMo): the background consensus worker opens its OWN independent DuckDB connection via "
    "db_manager.get_new_review_connection() (a fresh duckdb.connect to the same review DB file) "
    "and closes it when done, so it never shares a connection object with request handlers.\n\n"
)

MIMO_PROMPT = (
    "You are MiMo, reviewing in your lane: USABILITY, PERFORMANCE, LATENCY, MEMORY, DB COST.\n\n"
    + INTENT +
    "Review ONLY for your lane. Checklist: (1) latency/cost of the gated second LLM call; "
    "(2) timeout=8.0 worst-case before fail-open; (3) gating logic actually prevents running "
    "on every answer; (4) any blocking/synchronous heavy work on the chat hot path; "
    "(5) DB cost of the audit UPDATE / review insert; (6) ADVICE RAIL precision — does it "
    "refuse advice questions WITHOUT false-positiving on factual filing questions? clear UX?\n\n"
    f"=== consensus_rails.py ===\n{consensus}\n\n"
    f"=== dialog_rails.py (investment-advice rail) ===\n{dialog}\n\n"
    f"=== wiring in langgraph_engine.py (_consensus_worker etc.) ===\n{wiring}\n\n"
    + VERDICT_FORMAT
)

DEEPSEEK_PROMPT = (
    "You are DeepSeek, reviewing in your lane: CORRECTNESS, API/SCHEMA, and DOC-vs-CODE ACCURACY.\n\n"
    + INTENT +
    "Review ONLY for your lane. Checklist: (1) check_consensus contract + ConsensusVerdict shape; "
    "(2) divergence/threshold logic correctness + edge cases (no numbers, formatting like $1,200 vs 1200); "
    "(3) the wiring's route override + audit UPDATE + review insert correctness and non-fatal handling; "
    "(4) CONCURRENCY: is the per-thread .cursor() use correct + safe (Codex r2)? "
    "(5) ADVICE RAIL correctness: regex precision, no catastrophic backtracking, advice caught before "
    "the on-topic financial-keyword check; "
    "(6) DOC ACCURACY: do claims in mindforge-risk-alignment.md match the code?\n\n"
    f"=== consensus_rails.py ===\n{consensus}\n\n"
    f"=== dialog_rails.py (investment-advice rail) ===\n{dialog}\n\n"
    f"=== wiring in langgraph_engine.py ===\n{wiring}\n\n"
    f"=== docs/mindforge-risk-alignment.md ===\n{doc}\n\n"
    + VERDICT_FORMAT
)


def call(name, base_url, model, api_key, prompt, max_tokens):
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=240.0)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def write_out(path, content):
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        f.write(content)


try:
    mimo_out = call(
        "mimo",
        os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"),
        os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
        Config.MIMO_API_KEY,
        MIMO_PROMPT,
        max_tokens=12000,
    )
except Exception as e:
    mimo_out = f"MIMO call failed: {e}"
write_out("scripts/_mimo_out.txt", mimo_out)
print(f"MIMO output written ({len(mimo_out)} chars)")

try:
    ds_out = call(
        "deepseek",
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        Config.DEEPSEEK_API_KEY,
        DEEPSEEK_PROMPT,
        max_tokens=3000,
    )
except Exception as e:
    ds_out = f"DEEPSEEK call failed: {e}"
write_out("scripts/_deepseek_out.txt", ds_out)
print(f"DEEPSEEK output written ({len(ds_out)} chars)")
