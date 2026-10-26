"""Decide whether the live Space is serving the NEW corpus (used by the Colab publish cell).

Mirrors the gates of embed-annuals.yml / refresh-filings.yml / deploy.yml
(model, stored dim range, single dim variant, company floor) and additionally
requires the served chunk and company counts to equal the uploaded DB's counts,
so the OLD container still answering mid-swap can never count as success.
"""
import json
import time
import urllib.error
import urllib.request

EXPECTED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_DIM = 1024
MIN_COMPANIES = 12


def evaluate_stats(stats: dict, expected_chunks: int, expected_companies: int) -> tuple[bool, str]:
    """Return (ready, one-line status) for a parsed /api/stats response."""
    data = stats.get("data", {}) or {}
    cfg = stats.get("config", {}) or {}
    if "error" in data:
        return False, f"api-error: {data['error']}"
    dmin, dmax = data.get("embedding_dim_min"), data.get("embedding_dim_max")
    variants = data.get("embedding_dim_variants")
    companies = data.get("companies_with_chunks") or 0
    chunks = data.get("filing_chunks")
    status = (f"model={cfg.get('embedding_model')} dim=[{dmin},{dmax}] variants={variants} "
              f"companies={companies}/{expected_companies} chunks={chunks}/{expected_chunks}")
    ready = (
        cfg.get("embedding_model") == EXPECTED_MODEL
        and dmin == EXPECTED_DIM and dmax == EXPECTED_DIM and variants == 1
        and companies >= MIN_COMPANIES
        and companies == expected_companies
        and chunks == expected_chunks
    )
    return ready, status


def fetch_stats(url: str, token: str | None = None, timeout: int = 30) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_for_new_corpus(fetch, expected_chunks, expected_companies, *, timeout_s=900,
                        interval_s=20, sleep=time.sleep, clock=time.monotonic, log=print) -> bool:
    """Poll `fetch()` until the new corpus is served; False if never within timeout_s."""
    deadline = clock() + timeout_s
    while clock() < deadline:
        sleep(interval_s)
        try:
            ready, status = evaluate_stats(fetch(), expected_chunks, expected_companies)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log("waiting for Space...", type(exc).__name__)
            continue
        log("health:", status)
        if ready:
            return True
    return False
