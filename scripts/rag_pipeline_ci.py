"""
CI validation script — full 31-ticker RAG pipeline smoke test.
Called by .github/workflows/deploy.yml after data is seeded.
Reads SPACE_URL and optional ADMIN_API_KEY from environment.
"""
import json
import os
import sys
import time
from urllib import error, request

SPACE_URL = os.environ["SPACE_URL"]
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
ENDPOINT = f"{SPACE_URL}/api/chat/auditable-rag"

# Full semiconductor coverage list (mirrors TICKER_TO_CIK in admin.py)
TICKERS = [
    "ADI",  "AMD",  "AVGO", "INTC", "MU",   "NVDA", "QCOM", "TXN",
    "TSM",  "MRVL", "NXPI", "MCHP", "MPWR", "SWKS", "QRVO", "ON",
    "AMAT", "LRCX", "KLAC", "TER",  "ENTG", "ONTO", "FORM", "PLAB",
    "COHU", "KLIC", "ICHR", "VECO", "AEHR", "ACLS", "AMKR",
]

QUERIES = {
    "ADI":  "What was Analog Devices' revenue and gross margin in their most recent 10-K?",
    "AMD":  "What were AMD's net income and R&D expenses?",
    "AVGO": "What is Broadcom's revenue and operating margin?",
    "INTC": "What is Intel's free cash flow and capital expenditure?",
    "MU":   "What is Micron's gross margin and long-term debt?",
    "NVDA": "What was NVIDIA's total revenue and gross profit?",
    "QCOM": "What are Qualcomm's revenues and earnings per share?",
    "TXN":  "What is Texas Instruments' operating income and cash flow?",
    "TSM":  "What is TSMC's revenue growth and net income?",
    "MRVL": "What were Marvell's revenues and operating expenses?",
    "NXPI": "What is NXP Semiconductors' gross margin and debt?",
    "MCHP": "What are Microchip Technology's revenues and R&D spend?",
    "MPWR": "What is Monolithic Power's revenue and net income?",
    "SWKS": "What were Skyworks' revenues and operating income?",
    "QRVO": "What is Qorvo's gross margin and free cash flow?",
    "ON":   "What are onsemi's revenues and capital expenditures?",
    "AMAT": "What is Applied Materials' revenue and operating margin?",
    "LRCX": "What were Lam Research's revenues and gross profit?",
    "KLAC": "What is KLA Corporation's net income and R&D expense?",
    "TER":  "What are Teradyne's revenues and operating income?",
    "ENTG": "What is Entegris' revenue and long-term debt?",
    "ONTO": "What were Onto Innovation's revenues and net income?",
    "FORM": "What is FormFactor's revenue and gross margin?",
    "PLAB": "What are Photronics' revenues and net income?",
    "COHU": "What is Cohu's revenue and operating income?",
    "KLIC": "What are Kulicke & Soffa's revenues and earnings?",
    "ICHR": "What is Ichor Holdings' revenue and gross margin?",
    "VECO": "What were Veeco's revenues and R&D expenses?",
    "AEHR": "What is Aehr Test Systems' revenue and net income?",
    "ACLS": "What are Axcelis Technologies' revenues and operating income?",
    "AMKR": "What is Amkor Technology's revenue and gross profit?",
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
