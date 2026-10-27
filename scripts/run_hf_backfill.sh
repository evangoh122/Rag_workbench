#!/usr/bin/env bash
# HF Jobs GPU backfill runner. STAGING ONLY: it never writes to the production
# dataset and never restarts the Space. Publishing is the separate, guarded
# `python -m scripts.hf_backfill publish` step documented in README.md.
#
# DRY RUN BY DEFAULT: prints the plan (tickers, forms, quarters, estimated
# filings) and exits 0 without downloading or embedding anything. To execute,
# set BACKFILL_CONFIRM=yes or pass --execute.
#
# Env:
#   DATASET_REPO      source dataset (read only), e.g. <user>/Rag-workbench
#   HF_TOKEN          read token
#   BACKFILL_TICKERS  required, comma list (bounds the run), e.g. AAPL,MSFT
#   BACKFILL_MAX_TICKERS  cap on the list length (default 10, allowed 1..50)
#   BACKFILL_FORMS    annual | 10-Q (default annual)
#   BACKFILL_QUARTERS for 10-Q, integer 1..8 (default 3)
#   BACKFILL_TIMEOUT_SECONDS  hard deadline for the whole run, enforced here with
#                     `timeout` (default 18000 = 5h, allowed 60..21600)
#   BACKFILL_CONFIRM  yes -> execute (same as --execute)
#   STAGING_DIR       output dir (default <repo>/data/hf_backfill_staging; must be
#                     under the repo root or PERSIST_DIR, else the run aborts)
#   PYTHON            interpreter command (default `uv run --locked --no-dev python`)
set -euo pipefail

# Never trust a recursion marker from the job environment (older versions used
# BACKFILL_INNER); the re-exec below is marked only by a one-time token dir.
unset BACKFILL_INNER

die() { echo "::error::$*" >&2; exit 2; }

is_int() { [[ "$1" =~ ^[0-9]+$ ]]; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXECUTE=0
INNER_DIR=""
[ "${BACKFILL_CONFIRM:-}" = "yes" ] && EXECUTE=1
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --inner=?*) INNER_DIR="${arg#--inner=}" ;;
    *) die "unknown argument: $arg" ;;
  esac
done

# ── validation (always, so a dry run fails on the same bad input) ───────────
: "${DATASET_REPO:?DATASET_REPO required}"
TICKERS="${BACKFILL_TICKERS:?BACKFILL_TICKERS required (bounded ticker list, e.g. AAPL,MSFT)}"
FORMS="${BACKFILL_FORMS:-annual}"
QUARTERS="${BACKFILL_QUARTERS:-3}"
MAX_TICKERS="${BACKFILL_MAX_TICKERS:-10}"
DEADLINE="${BACKFILL_TIMEOUT_SECONDS:-18000}"

is_int "$MAX_TICKERS" && [ "$MAX_TICKERS" -ge 1 ] && [ "$MAX_TICKERS" -le 50 ] \
  || die "BACKFILL_MAX_TICKERS must be an integer in 1..50 (got '$MAX_TICKERS')"
is_int "$DEADLINE" && [ "$DEADLINE" -ge 60 ] && [ "$DEADLINE" -le 21600 ] \
  || die "BACKFILL_TIMEOUT_SECONDS must be an integer in 60..21600 (got '$DEADLINE')"
case "$FORMS" in annual|10-Q) ;; *) die "BACKFILL_FORMS must be 'annual' or '10-Q' (got '$FORMS')" ;; esac
is_int "$QUARTERS" && [ "$QUARTERS" -ge 1 ] && [ "$QUARTERS" -le 8 ] \
  || die "BACKFILL_QUARTERS must be an integer in 1..8 (got '$QUARTERS')"

IFS=',' read -r -a TICKER_LIST <<< "$TICKERS"
[ "${#TICKER_LIST[@]}" -ge 1 ] || die "BACKFILL_TICKERS is empty"
for t in "${TICKER_LIST[@]}"; do
  [[ "$t" =~ ^[A-Za-z0-9.-]{1,10}$ ]] || die "invalid ticker '$t' in BACKFILL_TICKERS"
done
[ "${#TICKER_LIST[@]}" -le "$MAX_TICKERS" ] \
  || die "${#TICKER_LIST[@]} tickers exceeds BACKFILL_MAX_TICKERS=$MAX_TICKERS"

if [ "$FORMS" = "10-Q" ]; then PER_TICKER="$QUARTERS"; else PER_TICKER=2; fi
EST=$(( ${#TICKER_LIST[@]} * PER_TICKER ))

echo "PLAN: repo=$DATASET_REPO forms=$FORMS quarters=$QUARTERS tickers=${TICKER_LIST[*]}"
echo "PLAN: up to $EST filings to embed (<= $PER_TICKER per ticker), deadline ${DEADLINE}s"
if [ "$EXECUTE" -ne 1 ]; then
  echo "DRY RUN: nothing downloaded or embedded. Set BACKFILL_CONFIRM=yes or pass --execute to run."
  exit 0
fi

# ── hard deadline: re-exec the whole run under `timeout` ────────────────────
# The outer run always re-execs. The inner run is recognised only by `--inner=DIR`
# where DIR is a private (0700, ours) directory the outer shell just created and
# which holds the token; it is consumed (deleted) on entry, so it cannot be
# replayed and an environment variable cannot fake it. The inner run repeats all
# validation above.
if [ -z "$INNER_DIR" ]; then
  TOKEN_DIR="$(mktemp -d)"
  chmod 700 "$TOKEN_DIR"
  head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$TOKEN_DIR/token"
  exec timeout -k 30 "$DEADLINE" bash "${BASH_SOURCE[0]}" --execute "--inner=$TOKEN_DIR"
fi
[ -d "$INNER_DIR" ] && [ -O "$INNER_DIR" ] && [ ! -L "$INNER_DIR" ] \
  && [ "$(stat -c %a "$INNER_DIR")" = "700" ] && [ -s "$INNER_DIR/token" ] \
  || die "invalid or reused --inner token; refusing to run without the outer deadline"
rm -rf "$INNER_DIR"

# Array, not an unquoted string: no word-splitting surprises.
read -r -a PY <<< "${PYTHON:-uv run --locked --no-dev python}"

# Must live under the project root (or PERSIST_DIR): api/config.py silently swaps
# any other DB_PATH for data/rag.duckdb. Default is inside the repo's data/ dir.
STAGING_DIR="${STAGING_DIR:-$ROOT/data/hf_backfill_staging}"
mkdir -p "$STAGING_DIR"
WORK_DB="$STAGING_DIR/rag.duckdb"
BEFORE="$STAGING_DIR/before.json"
export STAGING_DIR WORK_DB
export DB_PATH="$WORK_DB"

# Fail unless a GPU is visible; never silently embed on CPU for 6h.
"${PY[@]}" -m scripts.hf_backfill check-cuda

# Pin the dataset head, download that exact revision, copy to a writable file.
HEAD_SHA=$("${PY[@]}" - <<'PYCODE'
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
PYCODE
)
HEAD_SHA=$(echo "$HEAD_SHA" | tail -n1)

# Fail closed unless the config code resolves DB_PATH to exactly the staged DB.
"${PY[@]}" -m scripts.hf_backfill effective-db "$WORK_DB"
"${PY[@]}" scripts/prepare_db_copy.py check "$WORK_DB"
"${PY[@]}" -m scripts.hf_backfill snapshot "$WORK_DB" "$BEFORE" --dataset-head "$HEAD_SHA"
"${PY[@]}" scripts/etl_guardrail.py snapshot "$WORK_DB" "$STAGING_DIR/guardrail_before.json"

EXTRA=()
if [ "$FORMS" = "10-Q" ]; then EXTRA=(--quarters "$QUARTERS"); fi
"${PY[@]}" scripts/embed_additional.py --forms "$FORMS" "${EXTRA[@]}" --tickers "$TICKERS"

"${PY[@]}" -m scripts.hf_backfill verify "$WORK_DB" "$BEFORE"
"${PY[@]}" scripts/etl_guardrail.py verify "$WORK_DB" "$STAGING_DIR/guardrail_before.json"

echo "Staged result: $WORK_DB (dataset head at snapshot: $HEAD_SHA). NOT published."
