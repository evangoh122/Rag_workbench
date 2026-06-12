"""
CI validation script — full 31-ticker RAG pipeline smoke test.
Called by .github/workflows/deploy.yml after data is seeded.
Reads SPACE_URL from environment.
"""
import json
import os
import sys
import time
from urllib import error, request

SPACE_URL = os.environ["SPACE_URL"]
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

for ticker in TICKERS:
    query = QUERIES[ticker]
    payload = json.dumps({"message": query, "ticker": ticker}).encode()
    req = request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            d = json.loads(resp.read())
    except error.HTTPError as e:
        body = e.read().decode()[:200]
        failed.append((ticker, f"HTTP {e.code}: {body}"))
        print(f"FAIL [{ticker}] HTTP {e.code}")
        time.sleep(2)
        continue
    except Exception as e:
        failed.append((ticker, str(e)))
        print(f"FAIL [{ticker}] {e}")
        time.sleep(2)
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

    time.sleep(1)

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
