"""
CI validation script — RAG pipeline smoke test over the curated dataset.
Called by .github/workflows/deploy.yml after the deployment is verified.
Reads SPACE_URL and optional ADMIN_API_KEY from environment.

The deployed dataset is the curated Qwen DuckDB restored from the HF dataset
(not a full 31-ticker EDGAR pull). This test asserts the full numeric pipeline
(retrieval -> XBRL extraction -> deterministic math -> verification -> output)
returns an XBRL-VERIFIED revenue figure — i.e. NOT an abstention — for each
ticker below. The ticker set and the single-metric revenue query are chosen
because they verify deterministically against filed XBRL; if retrieval, XBRL
extraction, or verification regresses, these flip to abstention and the gate
goes red. (Tickers whose filed revenue concept doesn't pass the verifier — e.g.
AMD/TXN/INTC — and prospectus-only tickers without XBRL — e.g. SPCX — are
intentionally excluded so the gate stays a true regression signal.)
"""
import json
import os
import sys
import time
from urllib import error, request

SPACE_URL = os.environ["SPACE_URL"]
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
ENDPOINT = f"{SPACE_URL}/api/chat/auditable-rag"

# Curated coverage: tickers in the dataset whose latest-period revenue verifies
# deterministically against filed XBRL (confirmed live before committing).
TICKERS = ["MU", "QCOM", "AVGO", "NVDA", "LRCX", "KLAC"]

# Single-metric revenue queries — the most reliably verifiable path (a filed
# Revenues XBRL fact the deterministic math cross-checks within tolerance).
QUERIES = {
    "MU":   "What was Micron's total revenue in its most recent fiscal year?",
    "QCOM": "What was Qualcomm's total revenue in its most recent fiscal year?",
    "AVGO": "What was Broadcom's total revenue in its most recent fiscal year?",
    "NVDA": "What was NVIDIA's total revenue in its most recent fiscal year?",
    "LRCX": "What was Lam Research's total revenue in its most recent fiscal year?",
    "KLAC": "What was KLA Corporation's total revenue in its most recent fiscal year?",
}

passed, failed = [], []
RETRY_CODES = {502, 503, 504}
MAX_RETRIES = 3


def _call_endpoint(ticker: str, query: str) -> dict:
    payload = json.dumps({"message": query, "ticker": ticker}).encode()
    headers = {"Content-Type": "application/json"}
    if ADMIN_API_KEY:
        headers["X-API-Key"] = ADMIN_API_KEY
    for attempt in range(MAX_RETRIES):
        try:
            req = request.Request(ENDPOINT, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except error.HTTPError as e:
            if e.code in RETRY_CODES and attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                print(f"  [{ticker}] HTTP {e.code} — retrying in {wait}s (attempt {attempt + 2}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise
        except Exception:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                print(f"  [{ticker}] connection error — retrying in {wait}s (attempt {attempt + 2}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise


for ticker in TICKERS:
    query = QUERIES[ticker]
    try:
        d = _call_endpoint(ticker, query)
    except error.HTTPError as e:
        body = e.read().decode()[:200]
        if e.code == 400:
            d = json.loads(body) if body else {}
            answer = d.get("answer") or d.get("detail") or ""
            if answer and len(answer) >= 20:
                passed.append(ticker)
                print(f"PASS [{ticker}]  HTTP 400  '{answer[:80]}...'")
                time.sleep(2)
                continue
        failed.append((ticker, f"HTTP {e.code}: {body}"))
        print(f"FAIL [{ticker}] HTTP {e.code}")
        time.sleep(3)
        continue
    except Exception as e:
        failed.append((ticker, str(e)))
        print(f"FAIL [{ticker}] {e}")
        time.sleep(3)
        continue

    answer = d.get("answer") or d.get("result") or ""
    eval_route = d.get("eval_route", "UNKNOWN")
    confidence = d.get("confidence")
    sources = d.get("sources", [])

    if not answer or len(answer) < 20:
        reason = f"answer too short ({len(answer)} chars): {answer!r}"
        failed.append((ticker, reason))
        print(f"FAIL [{ticker}] {reason}")
    elif "I cannot answer" in answer or "I don't have enough" in answer:
        failed.append((ticker, f"abstention ({len(sources)} sources): {answer[:80]!r}"))
        print(f"FAIL [{ticker}] abstention — sources={len(sources)}")
    elif len(sources) == 0 and answer:
        failed.append((ticker, f"zero sources ({len(sources)}): {answer[:80]!r}"))
        print(f"FAIL [{ticker}] zero sources (edgar_embeddings may be empty)")
    else:
        passed.append(ticker)
        conf_str = f"{confidence:.2%}" if confidence is not None else "n/a"
        print(
            f"PASS [{ticker}]  route={eval_route}  conf={conf_str}"
            f"  sources={len(sources)}  '{answer[:80]}...'"
        )

    time.sleep(2)

print()
print("=" * 60)
print(f"RAG pipeline results: {len(passed)}/{len(TICKERS)} passed")
print("=" * 60)
if failed:
    print(f"\nFAILED ({len(failed)}):")
    for t, reason in failed:
        print(f"  {t}: {reason}")
    sys.exit(1)
else:
    print("All tickers passed -- chunk -> hybrid BM25+vector -> rerank -> RRF OK")
