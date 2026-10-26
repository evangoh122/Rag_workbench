#!/usr/bin/env bash
# HF Jobs GPU backfill runner. STAGING ONLY: it never writes to the production
# dataset and never restarts the Space. Publishing is the separate, guarded
# `scripts/hf_backfill.py publish` step documented in README.md.
#
# Env:
#   DATASET_REPO      source dataset (read only), e.g. <user>/Rag-workbench
#   HF_TOKEN          read token
#   BACKFILL_TICKERS  required, comma list (bounds the run), e.g. AAPL,MSFT
#   BACKFILL_FORMS    annual | 10-Q (default annual)
#   BACKFILL_QUARTERS for 10-Q (default 3)
#   STAGING_DIR       output dir (default <repo>/data/hf_backfill_staging; must be
#                     under the repo root or PERSIST_DIR, else the run aborts)
set -euo pipefail

: "${DATASET_REPO:?DATASET_REPO required}"
TICKERS="${BACKFILL_TICKERS:?BACKFILL_TICKERS required (bounded ticker list, e.g. AAPL,MSFT)}"
# Must live under the project root (or PERSIST_DIR): api/config.py silently swaps
# any other DB_PATH for data/rag.duckdb. Default is inside the repo's data/ dir.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING_DIR="${STAGING_DIR:-$ROOT/data/hf_backfill_staging}"
FORMS="${BACKFILL_FORMS:-annual}"
QUARTERS="${BACKFILL_QUARTERS:-3}"
PY="${PYTHON:-uv run --locked --no-dev python}"

mkdir -p "$STAGING_DIR"
WORK_DB="$STAGING_DIR/rag.duckdb"
BEFORE="$STAGING_DIR/before.json"
export STAGING_DIR WORK_DB
export DB_PATH="$WORK_DB"

# Fail unless a GPU is visible; never silently embed on CPU for 6h.
$PY scripts/hf_backfill.py check-cuda

# Pin the dataset head, download that exact revision, copy to a writable file.
HEAD_SHA=$($PY - <<'PY'
import os
from huggingface_hub import HfApi, hf_hub_download
from scripts.prepare_db_copy import copy_writable
repo = os.environ["DATASET_REPO"]
token = os.environ.get("HF_TOKEN")
head = HfApi(token=token).repo_info(repo, repo_type="dataset").sha
path = hf_hub_download(repo_id=repo, filename="rag.duckdb", repo_type="dataset",
                       revision=head, token=token)
copy_writable(path, os.environ["WORK_DB"])
print(head)
PY
)
HEAD_SHA=$(echo "$HEAD_SHA" | tail -n1)

# Fail closed unless the config code resolves DB_PATH to exactly the staged DB.
$PY scripts/hf_backfill.py effective-db "$WORK_DB"
$PY scripts/prepare_db_copy.py check "$WORK_DB"
$PY scripts/hf_backfill.py snapshot "$WORK_DB" "$BEFORE" --dataset-head "$HEAD_SHA"
$PY scripts/etl_guardrail.py snapshot "$WORK_DB" "$STAGING_DIR/guardrail_before.json"

EXTRA=()
if [ "$FORMS" = "10-Q" ]; then EXTRA=(--quarters "$QUARTERS"); fi
$PY scripts/embed_additional.py --forms "$FORMS" "${EXTRA[@]}" --tickers "$TICKERS"

$PY scripts/hf_backfill.py verify "$WORK_DB" "$BEFORE"
$PY scripts/etl_guardrail.py verify "$WORK_DB" "$STAGING_DIR/guardrail_before.json"

echo "Staged result: $WORK_DB (dataset head at snapshot: $HEAD_SHA). NOT published."
