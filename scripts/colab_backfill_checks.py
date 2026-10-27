"""Checks used by notebooks/colab_backfill.ipynb (no GPU, Colab or network needed to test).

    append_only_proof(original_db, new_db)   row-level proof that nothing original changed
    validate_caps(tickers, quarters, ...)    the HF runner's caps (scripts/run_hf_backfill.sh)
    pending_groups / mark_done               completed-set bookkeeping for Colab resume

The notebook embeds into a copy of the pinned production DB and stages the result in a
private repo; this module is the guard that the copy only ever gained rows.
"""
import json
import os
import re

import duckdb

# Limits copied from scripts/run_hf_backfill.sh (BACKFILL_MAX_TICKERS, BACKFILL_QUARTERS,
# BACKFILL_TIMEOUT_SECONDS). tests/test_colab_notebook.py checks they have not drifted.
MAX_TICKERS_LIMIT = (1, 50)
QUARTERS_LIMIT = (1, 8)
DEADLINE_LIMIT = (60, 21600)
DEFAULT_GROUP_SIZE = 10  # the runner's default BACKFILL_MAX_TICKERS
TICKER_RE = re.compile(r"^[A-Za-z0-9.-]{1,10}$")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _base_tables(con, catalog: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name", [catalog]).fetchall()]


def _columns(con, catalog: str, table: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position", [catalog, table]).fetchall()]


def append_only_proof(original_db: str, new_db: str) -> dict:
    """Prove new_db is original_db plus appended rows. Raise RuntimeError otherwise.

    Per table in the original: it still exists, keeps every original column, has at least as
    many rows, and every original row (all original columns, as a multiset) is present with
    identical values (EXCEPT ALL). Both files are opened read-only. Returns per-table counts.
    """
    for path in (original_db, new_db):
        if not os.path.isfile(path):
            raise RuntimeError(f"append-only proof: missing file {path}")
    if os.path.realpath(original_db) == os.path.realpath(new_db):
        raise RuntimeError("append-only proof: original and new DB are the same file")
    con = duckdb.connect()
    problems: list[str] = []
    report: dict = {}
    try:
        con.execute(f"ATTACH '{original_db.replace(chr(39), chr(39) * 2)}' AS orig (READ_ONLY)")
        con.execute(f"ATTACH '{new_db.replace(chr(39), chr(39) * 2)}' AS new (READ_ONLY)")
        orig_tables = _base_tables(con, "orig")
        if not orig_tables:
            raise RuntimeError("append-only proof: original DB has no tables")
        new_tables = set(_base_tables(con, "new"))
        for t in orig_tables:
            if t not in new_tables:
                problems.append(f"{t}: table missing after")
                continue
            ocols = _columns(con, "orig", t)
            missing = [c for c in ocols if c not in set(_columns(con, "new", t))]
            if missing:
                problems.append(f"{t}: columns dropped {missing}")
                continue
            cols = ", ".join(_ident(c) for c in ocols)
            n_before = con.execute(f"SELECT count(*) FROM orig.main.{_ident(t)}").fetchone()[0]
            n_after = con.execute(f"SELECT count(*) FROM new.main.{_ident(t)}").fetchone()[0]
            lost = con.execute(
                f"SELECT count(*) FROM (SELECT {cols} FROM orig.main.{_ident(t)} "
                f"EXCEPT ALL SELECT {cols} FROM new.main.{_ident(t)})").fetchone()[0]
            if n_after < n_before:
                problems.append(f"{t}: rows shrank {n_before} -> {n_after}")
            if lost:
                problems.append(f"{t}: {lost} original row(s) missing or modified")
            report[t] = {"before": n_before, "after": n_after, "added": n_after - n_before}
    finally:
        con.close()
    if problems:
        raise RuntimeError("APPEND-ONLY PROOF FAILED: " + "; ".join(problems))
    return report


def validate_caps(tickers, quarters, group_size, deadline_seconds) -> None:
    """Raise ValueError unless the run stays inside the HF runner's caps."""
    tickers = list(tickers)
    if not tickers:
        raise ValueError("no tickers selected")
    lo, hi = MAX_TICKERS_LIMIT
    if not lo <= len(tickers) <= hi:
        raise ValueError(f"{len(tickers)} tickers outside the runner cap {lo}..{hi}")
    bad = [t for t in tickers if not TICKER_RE.match(t)]
    if bad:
        raise ValueError(f"invalid ticker(s): {bad}")
    if len(set(tickers)) != len(tickers):
        raise ValueError("duplicate tickers")
    if not isinstance(quarters, int) or isinstance(quarters, bool) or not QUARTERS_LIMIT[0] <= quarters <= QUARTERS_LIMIT[1]:
        raise ValueError(f"quarters must be an integer in {QUARTERS_LIMIT[0]}..{QUARTERS_LIMIT[1]}")
    if not isinstance(group_size, int) or isinstance(group_size, bool) or not 1 <= group_size <= DEFAULT_GROUP_SIZE:
        raise ValueError(f"group size must be an integer in 1..{DEFAULT_GROUP_SIZE}")
    if (not isinstance(deadline_seconds, int) or isinstance(deadline_seconds, bool)
            or not DEADLINE_LIMIT[0] <= deadline_seconds <= DEADLINE_LIMIT[1]):
        raise ValueError(f"deadline must be an integer in {DEADLINE_LIMIT[0]}..{DEADLINE_LIMIT[1]} seconds")


def pending_groups(forms_plan, tickers, completed, group_size):
    """Yield (form, group) for tickers whose '<form>:<ticker>' key is not in `completed`."""
    done = set(completed)
    for form in forms_plan:
        todo = [t for t in tickers if f"{form}:{t}" not in done]
        for i in range(0, len(todo), group_size):
            yield form, todo[i:i + group_size]


def mark_done(meta: dict, form: str, group) -> dict:
    """Return meta with '<form>:<ticker>' added to its sorted, de-duplicated completed list."""
    keys = set(meta.get("completed", [])) | {f"{form}:{t}" for t in group}
    return {**meta, "completed": sorted(keys)}


def load_meta(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
