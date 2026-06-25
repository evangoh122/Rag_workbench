"""One-off: get MiMo + DeepSeek to review the conjoint changeset via their real
APIs (keys in .env), and write each verdict to its lane file.

Throwaway helper (per the repo's `_*.py` convention). Not part of the app.
Run: ./.venv/Scripts/python.exe scripts/_run_conjoint_review.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from api.config import Config  # noqa: E402

# New files → include full content. Modified files → include the git diff.
NEW_FILES = [
    "api/routes/conjoint.py",
    "frontend/src/api/conjoint.ts",
    "frontend/src/components/ConjointSurvey.tsx",
    "frontend/src/components/ConjointGate.tsx",
    "frontend/src/pages/ConjointStudy.tsx",
]
MODIFIED_FILES = [
    "api/main.py",
    "api/models/schemas.py",
    "api/routes/chat.py",
    "api/services/langgraph_engine.py",
    "frontend/src/api/chat.ts",
    "frontend/src/App.tsx",
]

REVIEW_REQUEST = (ROOT / ".deepseek/coordination/REVIEW-REQUEST-conjoint.md").read_text(encoding="utf-8")


def _git_diff(path: str) -> str:
    try:
        out = subprocess.run(
            ["git", "diff", "HEAD", "--", path],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        return out.stdout or "(no diff captured)"
    except Exception as e:  # noqa: BLE001
        return f"(git diff failed: {e})"


def build_changeset() -> str:
    parts: list[str] = []
    for rel in NEW_FILES:
        p = ROOT / rel
        if p.exists():
            parts.append(f"### NEW FILE: {rel}\n```\n{p.read_text(encoding='utf-8')}\n```")
    for rel in MODIFIED_FILES:
        parts.append(f"### DIFF: {rel}\n```diff\n{_git_diff(rel)}\n```")
    return "\n\n".join(parts)


LANES = {
    "mimo": {
        "title": "MiMo",
        "focus": (
            "USABILITY and PERFORMANCE. Survey/gate UX clarity, control-vs-treatment "
            "comprehensibility, DuckDB query cost on the review DB as conjoint_responses "
            "grows (indexes / table scans), any blocking work on the chat hot path from the "
            "role wiring, localStorage reads per render in App.tsx, and the auto-prompt "
            "(>=3 answers) not looping or annoying."
        ),
        "out": ROOT / ".mimo/VERDICT-conjoint.md",
    },
    "deepseek": {
        "title": "DeepSeek",
        "focus": (
            "API CONTRACTS, SCHEMA CORRECTNESS, and SECURITY. Pydantic validation "
            "(chosen ^[AB]$, usefulness 1..5, arm/role allow-listing, profile validation), "
            "idempotent table creation + ADD COLUMN IF NOT EXISTS migrations, SQL injection "
            "safety (all parameterized), that complete derives prefs only from the session's "
            "own rows, that client `role` flows into the LLM prompt via a server-side allow-list "
            "(role_guidance_for) and not raw client text, and unauthenticated-endpoint abuse risk."
        ),
        "out": ROOT / ".deepseek/VERDICT-conjoint.md",
    },
}

SYSTEM = (
    "You are a meticulous senior engineer performing a pre-commit peer review. "
    "Review ONLY against your assigned lane. Read the actual code. Be concrete: cite "
    "file:line where possible, classify each finding [blocker|major|minor|nit], and give a "
    "suggested fix. Do not rewrite the code. End with an explicit verdict line: "
    "'Status: APPROVED' or 'Status: CHANGES NEEDED'. APPROVED only if no blocker/major findings."
)


def review(provider_key: str) -> None:
    lane = LANES[provider_key]
    prev = Config.CHAT_PROVIDER  # not used; we read provider config directly
    del prev
    # Pull this provider's config explicitly (independent of CHAT_PROVIDER).
    import os
    os.environ["CHAT_PROVIDER"] = provider_key
    cfg = Config.get_provider_config()
    if not cfg["api_key"]:
        print(f"[{lane['title']}] no API key — skipping")
        return

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=180.0)
    user = (
        f"# Review request\n{REVIEW_REQUEST}\n\n"
        f"# YOUR LANE: {lane['title']}\nFocus strictly on: {lane['focus']}\n\n"
        f"# Changeset to review\n{build_changeset()}\n\n"
        "Write your verdict now using the format from PROTOCOL.md "
        "(# VERDICT — conjoint — <Agent> — round 1 / Status / Reviewed / Findings / Notes)."
    )
    print(f"[{lane['title']}] calling {cfg['model']} @ {cfg['base_url']} …")
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        temperature=0.1,
        max_tokens=cfg.get("max_tokens", 4096),
        timeout=180.0,
    )
    text = (resp.choices[0].message.content or "").strip()
    lane["out"].write_text(text + "\n", encoding="utf-8")
    status = "CHANGES NEEDED" if "CHANGES NEEDED" in text.upper() else (
        "APPROVED" if "APPROVED" in text.upper() else "UNKNOWN")
    print(f"[{lane['title']}] wrote {lane['out'].relative_to(ROOT)} — verdict: {status}")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["mimo", "deepseek"]
    for t in targets:
        try:
            review(t)
        except Exception as e:  # noqa: BLE001
            print(f"[{t}] review failed: {type(e).__name__}: {e}")
