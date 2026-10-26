"""Isolated execution of LLM-generated chat SQL.

``enable_external_access`` / ``lock_configuration`` are instance-wide in DuckDB,
so they cannot be applied to the shared app connection (runtime snapshot export
needs COPY/read_parquet).  Instead the parent:

1. resolves the tables the query reads from DuckDB's own parsed AST
   (``json_serialize_sql``), failing closed on anything outside the allowlist;
2. copies those tables through a request-owned cursor as Arrow IPC bytes under a
   byte budget (the child never sees the real DB file);
3. runs the SQL in a short-lived child process (``chat_worker.py``) with
   ``RLIMIT_AS``/``RLIMIT_CPU``, external access disabled and config locked,
   under a single absolute wall-clock deadline that covers loading and
   execution, killing and reaping the child on expiry.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

# Tables the chat model is told about (see chat_engine.SCHEMA).
ALLOWED_TABLES = frozenset({
    "xbrl_facts", "edgar_embeddings", "ticker_embeddings", "polygon_tickers",
    "polygon_bars", "graph_triples",
})

MAX_MIRROR_BYTES = 256 * 1024 * 1024   # total across all mirrored tables
BATCH_ROWS = 50_000
QUERY_DEADLINE_SECONDS = 10.0          # whole operation: load + execute
CHILD_EXTRA_ADDRESS_SPACE = 1024 * 1024 * 1024   # RLIMIT_AS above the loaded baseline
MAX_RESULT_ROWS = 100
MAX_CELL_CHARS = 10_000
MAX_RESULT_BYTES = 2 * 1024 * 1024     # of the JSON actually returned to the route

_WORKER = str(Path(__file__).with_name("chat_worker.py"))


class ChatQueryError(Exception):
    """Chat SQL could not be executed (rejected, failed or hit a limit)."""


class ChatQueryLimitError(ChatQueryError):
    """Raised when a chat query exceeds a size or time budget."""


# ---------------------------------------------------------------- table resolution
def _collect(node: Any, scope: frozenset, out: set, bad: set) -> None:
    if isinstance(node, list):
        for item in node:
            _collect(item, scope, out, bad)
        return
    if not isinstance(node, dict):
        return
    inner = scope
    cte_map = node.get("cte_map")
    if isinstance(cte_map, dict) and cte_map.get("map"):
        names: list[str] = []
        for entry in cte_map["map"]:
            names.append(entry["key"].lower())
            # A CTE body sees earlier CTEs (and itself, for RECURSIVE).
            _collect(entry["value"], scope | frozenset(names), out, bad)
        inner = scope | frozenset(names)
    for key, value in node.items():
        if key == "cte_map":
            continue
        _collect(value, inner, out, bad)
    if node.get("type") == "BASE_TABLE":
        name = str(node.get("table_name", "")).lower()
        schema = str(node.get("schema_name", "")).lower()
        catalog = str(node.get("catalog_name", "")).lower()
        if not schema and not catalog and name in scope:
            return  # reference to an in-scope CTE
        if catalog not in ("", "memory") or schema not in ("", "main") or name not in ALLOWED_TABLES:
            bad.add(".".join(p for p in (catalog, schema, name) if p) or "?")
        else:
            out.add(name)


def referenced_tables(sql: str) -> list[str]:
    """Allow-listed base tables read by ``sql``; fail closed on anything else."""
    probe = duckdb.connect(":memory:")
    try:
        parsed = json.loads(probe.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    finally:
        probe.close()
    if parsed.get("error"):
        raise ChatQueryError("Only a single SELECT query can be run.")
    found: set[str] = set()
    bad: set[str] = set()
    _collect(parsed["statements"], frozenset(), found, bad)
    if bad:
        raise ChatQueryError(f"Query references tables that are not available: {', '.join(sorted(bad))}.")
    return sorted(found)


# --------------------------------------------------------------------- mirroring
def mirror_tables(source: Any, names: list[str], deadline: float) -> dict[str, bytes]:
    """Copy tables to Arrow IPC bytes via a request-owned cursor under the budgets."""
    cursor = source.cursor()
    remaining = max(deadline - time.monotonic(), 0.001)
    timer = threading.Timer(remaining, cursor.interrupt)
    timer.start()
    budget = MAX_MIRROR_BYTES
    blobs: dict[str, bytes] = {}
    try:
        for name in names:
            try:
                reader = cursor.execute(f'SELECT * FROM "{name}"').to_arrow_reader(BATCH_ROWS)
            except duckdb.CatalogException:
                continue  # table absent in this database
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, reader.schema) as writer:
                for batch in reader:
                    if time.monotonic() > deadline:
                        raise ChatQueryLimitError("Chat query timed out while loading data.")
                    budget -= batch.nbytes
                    if budget < 0:
                        raise ChatQueryLimitError(f"Table data is too large for chat queries (at {name}).")
                    writer.write_batch(batch)
            blobs[name] = sink.getvalue().to_pybytes()
    except duckdb.InterruptException as exc:
        raise ChatQueryLimitError("Chat query timed out while loading data.") from exc
    finally:
        timer.cancel()
        timer.join()
        cursor.close()
    return blobs


# -------------------------------------------------------------------- child run
def _run_in_worker(blobs: dict[str, bytes], sql: str, deadline: float) -> list[dict]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ChatQueryLimitError("Chat query exceeded its time limit.")
    header = {
        "sql": sql,
        "tables": [[n, len(b)] for n, b in blobs.items()],
        "limits": {
            "as_bytes": CHILD_EXTRA_ADDRESS_SPACE,
            "cpu_seconds": int(remaining) + 2,
            "memory_mb": 512,
            "max_rows": MAX_RESULT_ROWS,
            "max_cell_chars": MAX_CELL_CHARS,
            "max_result_bytes": MAX_RESULT_BYTES,
        },
    }
    payload = json.dumps(header).encode() + b"\n" + b"".join(blobs.values())
    # No ambient credentials; cap glibc per-thread arenas (64MB of address space
    # each) so RLIMIT_AS measures real use, and use the plain system allocator.
    env = {"PATH": os.environ.get("PATH", ""), "MALLOC_ARENA_MAX": "2",
           "ARROW_DEFAULT_MEMORY_POOL": "system"}
    proc = subprocess.Popen(
        [sys.executable, "-I", _WORKER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
    )
    try:
        out, _ = proc.communicate(payload, timeout=max(deadline - time.monotonic(), 0.001))
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise ChatQueryLimitError("Chat query exceeded its time limit.") from exc
    except BaseException:
        proc.kill()
        proc.communicate()
        raise
    finally:
        if proc.poll() is None:  # defensive: never leak the child
            proc.kill()
            proc.wait()
    if proc.returncode != 0 or not out:
        raise ChatQueryLimitError("Chat query was stopped by its resource limits.")
    if len(out) > MAX_RESULT_BYTES + 4096:
        raise ChatQueryLimitError("Chat query result is too large.")
    result = json.loads(out)
    if not result.get("ok"):
        cls = ChatQueryLimitError if result.get("limit") else ChatQueryError
        raise cls(result.get("error", "Query execution failed."))
    return result["rows"]


def run_chat_query(source: Any, sql: str) -> list[dict]:
    """Run generated SQL under one deadline; returns size-capped JSON-ready rows."""
    deadline = time.monotonic() + QUERY_DEADLINE_SECONDS
    names = referenced_tables(sql)
    blobs = mirror_tables(source, names, deadline)
    return _run_in_worker(blobs, sql, deadline)
