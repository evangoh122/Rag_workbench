"""Temporary script: send recent diff to Gemini + DeepSeek for code review."""
import os, json, urllib.request, concurrent.futures
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DIFF = Path(__file__).parent.parent / "scripts" / "_review_diff.txt"

PROMPT = """You are a senior software engineer reviewing a Python/FastAPI codebase.
Review the git diff below. Identify: bugs, security issues, thread-safety problems,
missing error handling, SQL injection risks, and correctness issues.
Bullet points only, grouped by file. Skip style nits.

""" + DIFF.read_text()[:14000]


def post_json(url, body, headers=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", **(headers or {})
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def call_mimo():
    key = os.getenv("XIAOMI_API_KEY") or os.getenv("MIMO_API_KEY")
    base = os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1")
    r = post_json(
        f"{base}/chat/completions",
        {
            "model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 2000,
            "temperature": 0.1,
        },
        {"Authorization": f"Bearer {key}"},
    )
    return r["choices"][0]["message"]["content"]


def call_deepseek():
    key = os.getenv("DEEPSEEK_API_KEY")
    r = post_json(
        "https://api.deepseek.com/v1/chat/completions",
        {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 1500,
            "temperature": 0.1,
        },
        {"Authorization": f"Bearer {key}"},
    )
    return r["choices"][0]["message"]["content"]


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    fm = ex.submit(call_mimo)
    fd = ex.submit(call_deepseek)
    mimo = fm.result() if not fm.exception() else f"ERROR: {fm.exception()}"
    deepseek = fd.result() if not fd.exception() else f"ERROR: {fd.exception()}"

print("=== MIMO ===")
print(mimo)
print("\n=== DEEPSEEK ===")
print(deepseek)
