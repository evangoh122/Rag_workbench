"""One-off orchestrator: MiMo writes scripts/embed_additional.py, DeepSeek reviews it.

Outputs:
  scripts/embed_additional.GENERATED.py   <- raw MiMo output (for human/Claude validation)
  scripts/_embed_additional_review.md      <- DeepSeek review of the generated code
"""
import os, json, urllib.request, re
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

SPEC = r'''
Write a complete, runnable Python script for the file `scripts/embed_additional.py`
in an existing repo. Output ONLY the Python source code, no markdown fences, no
prose before or after.

PURPOSE
For companies that ALREADY have filings embedded in DuckDB table `edgar_embeddings`,
add the 2 most recent ANNUAL filings (10-K, or 20-F for foreign filers) and the 1
most recent 10-Q. Dedup by (ticker, accession) so already-present filings are skipped.

CLI FLAGS (use argparse)
  --forms {annual,10-Q}   default "annual". annual => fetch form 10-K AND 20-F with
                          latest(2); "10-Q" => fetch form 10-Q with latest(1).
  --dry-run               print planned fetch/skip per ticker, write NOTHING to DB.
  --tickers A,B,C         optional comma list; default = all distinct tickers already
                          present in edgar_embeddings.
  --log PATH              optional loguru file sink.

ENVIRONMENT SETUP (do this at top, BEFORE importing api/scripts modules)
  - sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
  - load_dotenv(ROOT/".env")
  - os.environ["EMBEDDING_PROVIDER"] = "sentence-transformers"
  - os.environ["ST_EMBEDDING_MODEL"] = "Qwen/Qwen3-Embedding-0.6B"
  - os.environ["EMBEDDING_DIM"] = "1024"
  - os.environ.setdefault("EDGAR_USER_AGENT", "Evan Goh evangohsg@gmail.com")
  - import warnings; from bs4 import XMLParsedAsHTMLWarning;
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

IMPORTS AVAILABLE (use these exact names; do not reimplement)
  from api.config import Config                      # Config.DB_PATH (str)
  from api.services.embeddings import get_embeddings # returns model or None
  from api.services.structure_chunker import StructureChunker
  from api.services._edgar_identity import ensure_edgar_identity
  from scripts.embed_edgar import (
      parse_html_file, _extract_sections_with_labels, _ensure_schema, _TICKER_CIK,
  )
  from edgar import Company
  import duckdb
  from datetime import datetime, timezone
  from loguru import logger

KEY SIGNATURES / BEHAVIOR
  - get_embeddings() -> object with .embed_documents(list[str]) -> list[list[float]]
    (1024-dim normalized vectors). Returns None if unavailable -> log error + exit(1).
  - StructureChunker(max_chunk_size=1500, min_chunk_size=200, similarity_threshold=0.15)
  - chunker.chunk(section_text, section_label=..., ticker=..., period=..., form_type=...,
      provenance_header=...) -> list of Chunk objects, each with:
        chunk.text (str)
        chunk.metadata.section_label, chunk.metadata.chunk_index,
        chunk.metadata.section_type, chunk.metadata.content_type
  - parse_html_file(path) -> (clean_full_text:str, raw_content:str)
  - _extract_sections_with_labels(text) -> list[(section_label, section_text)]
    (10-K Item sections; 20-F falls back to [("full_text", text)] which is correct here)
  - _TICKER_CIK: dict[str,str] ticker(upper) -> CIK
  - ensure_edgar_identity() sets the SEC user agent; call once at start.

EDGAR FETCH (edgartools)
  - Company(ticker).get_filings(form=F) -> Filings; index 0 = most recent.
  - For annual: for F in ("10-K","20-F"): take .latest(2) (may be a single Filing if
    only one exists, or a Filings collection; handle both by iterating safely).
  - For 10-Q: F="10-Q", .latest(1).
  - For each Filing object `fl`:
      accession = fl.accession_number          # KEEP DASHES e.g. "0000006281-25-000153"
      form_type = fl.form
      yy = accession.split("-")[1]
      period_of_report = f"20{yy}-12-31" if int(yy) < 50 else f"19{yy}-12-31"
      write fl.text() to a temp file path under ./data/edgar_downloads/<ticker>/<form>/
        <accession-no-dashes>/primary-document.html (mkdir parents, skip write if exists)
      then parse_html_file(path) to get (text, _).
  - Wrap each ticker/filing in try/except and continue on error (log it).

DEDUP
  - Before processing a filing, check:
      SELECT 1 FROM edgar_embeddings WHERE ticker=? AND accession=? LIMIT 1
    If present, log "skip (already present)" and continue. In --dry-run, only print.

DB WRITE (mirror scripts/embed_edgar.py exactly)
  - duckdb.connect(Config.DB_PATH); try conn.execute("LOAD vss") (ignore failure).
  - _ensure_schema(conn)
  - cik = _TICKER_CIK.get(ticker.upper(), "")
  - ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
  - provenance_header = f"[TICKER:{ticker.upper()} | SECTION:{section_label} | "
                        f"PERIOD:{period_of_report} | FORM:{form_type}]\n"
  - sections = _extract_sections_with_labels(text); build all_chunks by chunking each section.
  - DELETE existing rows for (ticker, accession) before insert (idempotent re-run).
  - Embed in batches of 4: vecs = model.embed_documents(batch_texts).
  - INSERT columns EXACTLY:
      (ticker, accession, text, embedding, updated_at, cik, section_id, form_type,
       period_of_report, chunk_index, section_type, content_type)
    values: ticker, accession, chunk.text, vecs[j], ts, cik,
      chunk.metadata.section_label, form_type, period_of_report,
      chunk.metadata.chunk_index, chunk.metadata.section_type, chunk.metadata.content_type
  - conn.commit() after each filing. Use gc.collect() + del large vars between filings.
  - Print a final summary: per ticker, filings added vs skipped, total chunks stored.

ROBUSTNESS
  - latest(n) may return a single Filing (not iterable) when only 1 exists; normalize to a list.
  - Never crash the whole run on one ticker/filing; log and continue.
  - In --dry-run do not connect for writes is fine, but you DO need read access to check dedup.

Produce the full file now. Code only.
'''

REVIEW_PROMPT_TMPL = """You are a senior Python engineer. Review this script that will
be run to embed extra SEC filings into a DuckDB table `edgar_embeddings`.

Check ONLY for real defects, grouped by severity (CRITICAL / MAJOR / MINOR):
- Correctness bugs (latest(n) single-vs-collection handling, vecs[j] index alignment
  with the batch actually embedded, dedup before insert, accession dash format kept,
  period_of_report = 20YY-12-31 from accession middle segment).
- Crash-safety: one bad ticker/filing must not abort the whole run.
- DB: connection/commit handling, SQL parameterization, schema column order matching
  the INSERT, idempotent re-runs (DELETE by ticker+accession).
- --dry-run must not write to the DB.
- Resource leaks (open files/connections).
Be concise. Bullet points. If a CRITICAL bug exists, say so explicitly.

```python
{code}
```
"""


def post_json(url, body, headers=None, timeout=180):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", **(headers or {})
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def call_mimo(prompt, max_tokens=8000):
    key = os.getenv("XIAOMI_API_KEY") or os.getenv("MIMO_API_KEY")
    base = os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1")
    r = post_json(
        f"{base}/chat/completions",
        {
            "model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        },
        {"Authorization": f"Bearer {key}"},
    )
    return r["choices"][0]["message"]["content"]


def call_deepseek(prompt, max_tokens=2500):
    key = os.getenv("DEEPSEEK_API_KEY")
    r = post_json(
        "https://api.deepseek.com/v1/chat/completions",
        {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        },
        {"Authorization": f"Bearer {key}"},
    )
    return r["choices"][0]["message"]["content"]


def strip_fences(s):
    s = s.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", s, re.DOTALL)
    return m.group(1).strip() if m else s


print("[1/2] MiMo generating scripts/embed_additional.py ...")
code = strip_fences(call_mimo(SPEC))
gen_path = ROOT / "scripts" / "embed_additional.GENERATED.py"
gen_path.write_text(code, encoding="utf-8")
print(f"      wrote {gen_path} ({len(code)} chars)")

print("[2/2] DeepSeek reviewing generated code ...")
review = call_deepseek(REVIEW_PROMPT_TMPL.format(code=code[:16000]))
rev_path = ROOT / "scripts" / "_embed_additional_review.md"
rev_path.write_text(review, encoding="utf-8")
print(f"      wrote {rev_path}")
print("\n===== DEEPSEEK REVIEW =====\n")
print(review)
