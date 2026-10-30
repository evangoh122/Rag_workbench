"""Isolated execution of LLM-generated chat SQL.

``enable_external_access`` / ``lock_configuration`` are instance-wide in DuckDB,
so they cannot be applied to the shared app connection (runtime snapshot export
needs COPY/read_parquet).  Instead the parent:

1. resolves the tables the query reads from DuckDB's own parsed AST
   (``json_serialize_sql``), failing closed on anything outside the allowlist;
2. copies those tables through a request-owned cursor in a single read
   transaction, as Arrow IPC bytes under a byte budget sized from the table's
   true maximum row width (the child never sees the real DB file);
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
PAGE_BYTES = 8 * 1024 * 1024           # target bytes per page; bounds parent overshoot
MAX_PAGE_ROWS = 200_000
QUERY_DEADLINE_SECONDS = 10.0          # whole operation: load + execute
CHILD_EXTRA_ADDRESS_SPACE = 1024 * 1024 * 1024   # RLIMIT_AS above the loaded baseline
MAX_RESULT_ROWS = 100
MAX_CELL_CHARS = 10_000
MAX_RESULT_BYTES = 2 * 1024 * 1024     # of the JSON actually returned to the route

# Arrow per-column overhead: offsets for variable-width data plus validity bits.
PAGE_COLUMN_OVERHEAD = 8

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
            key = entry["key"].lower()
            body = entry["value"]["query"]["node"]
            # A body sees earlier CTEs; itself only when WITH RECURSIVE.
            body_scope = scope | frozenset(names)
            if body.get("type") == "RECURSIVE_CTE_NODE":
                body_scope |= {key}
            _collect(entry["value"], body_scope, out, bad)
            names.append(key)
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
def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ChatQueryLimitError("Chat query timed out while loading data.")


def _fixed_bytes(arrow_type: pa.DataType) -> int | None:
    """Storage width of a fixed-width Arrow type, or ``None`` if variable."""
    if pa.types.is_boolean(arrow_type):
        return 1
    try:
        return max(1, arrow_type.bit_width // 8)
    except (AttributeError, ValueError):
        return None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _list_width_expr(column: str, value_type: pa.DataType) -> str | None:
    """SQL expression for the payload bytes of one list value."""
    if pa.types.is_string(value_type) or pa.types.is_large_string(value_type):
        return f"coalesce(list_sum(list_transform({column}, x -> strlen(x))), 0)"
    if pa.types.is_binary(value_type) or pa.types.is_large_binary(value_type):
        return f"coalesce(list_sum(list_transform({column}, x -> octet_length(x))), 0)"
    width = _fixed_bytes(value_type)
    if width is None:
        return None
    return f"coalesce(len({column}), 0) * {width}"


def _width_expr(field: pa.Field) -> str:
    """SQL expression giving the payload bytes of one column in one row.

    Lengths are read from DuckDB's string metadata, so measuring them does not
    copy the (possibly huge) values themselves into the parent process.
    """
    column = _quote(field.name)
    arrow_type = field.type
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        expr: str | None = f"coalesce(strlen({column}), 0)"
    elif pa.types.is_binary(arrow_type) or pa.types.is_large_binary(arrow_type):
        expr = f"coalesce(octet_length({column}), 0)"
    elif (pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type)
          or pa.types.is_fixed_size_list(arrow_type)):
        expr = _list_width_expr(column, arrow_type.value_type)
    else:
        width = _fixed_bytes(arrow_type)
        expr = str(width) if width is not None else None
    if expr is None:
        # Unknown/nested type: measure its textual form rather than undercount.
        expr = f"coalesce(strlen(CAST({column} AS VARCHAR)), 0)"
    return expr


def _measure_table(cursor: Any, name: str) -> tuple[pa.Schema, int, int]:
    """Schema, row count and true maximum row payload width for ``name``."""
    schema = cursor.execute(f'SELECT * FROM {_quote(name)} LIMIT 0').to_arrow_table().schema
    widths = " + ".join(_width_expr(field) for field in schema) or "0"
    total, max_row = cursor.execute(
        f'SELECT count(*), max({widths}) FROM {_quote(name)}'
    ).fetchone()
    return schema, int(total or 0), int(max_row or 0)


def _order_clause(cursor: Any, name: str) -> str:
    """Deterministic page order: physical row id, or every column for a view."""
    try:
        cursor.execute(f'SELECT rowid FROM {_quote(name)} LIMIT 0')
    except duckdb.Error:
        return " ORDER BY ALL"
    return " ORDER BY rowid"


def _page_rows(max_row_bytes: int, columns: int) -> int:
    width = max(max_row_bytes, 1) + PAGE_COLUMN_OVERHEAD * max(columns, 1)
    return int(max(1, min(MAX_PAGE_ROWS, PAGE_BYTES // width)))


def mirror_tables(source: Any, names: list[str], deadline: float) -> dict[str, bytes]:
    """Copy tables to Arrow IPC bytes via a request-owned cursor under the budgets.

    The deadline is enforced two ways that cannot miss a later statement: it is
    checked before every execute/fetch, and a watchdog thread keeps interrupting
    the cursor every 50ms once the deadline has passed.

    Every table is copied inside one read transaction so a concurrent writer
    cannot make ``LIMIT``/``OFFSET`` pages skip or repeat rows, and pages are
    ordered by a stable key so the page boundaries are deterministic.
    """
    cursor = source.cursor()
    stop = threading.Event()

    def watchdog() -> None:
        if stop.wait(max(deadline - time.monotonic(), 0)):
            return
        while not stop.is_set():
            try:
                cursor.interrupt()
            except Exception:  # noqa: BLE001 - cursor may already be closed
                return
            stop.wait(0.05)

    thread = threading.Thread(target=watchdog, daemon=True)
    thread.start()
    budget = MAX_MIRROR_BYTES
    blobs: dict[str, bytes] = {}
    committed = False
    try:
        cursor.execute("BEGIN TRANSACTION")
        _check_deadline(deadline)
        for name in names:
            _check_deadline(deadline)
            try:
                schema, total, max_row = _measure_table(cursor, name)
            except duckdb.CatalogException:
                continue  # table absent in this database
            # Refuse before buffering anything: if even the widest row cannot
            # fit the remaining budget, no page size makes this table safe.
            if total and max_row * total > budget:
                raise ChatQueryLimitError(f"Table data is too large for chat queries (at {name}).")
            order = _order_clause(cursor, name)
            n = _page_rows(max_row, len(schema))
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, schema) as writer:
                offset = 0
                while True:
                    _check_deadline(deadline)
                    page = cursor.execute(
                        f'SELECT * FROM {_quote(name)}{order} LIMIT {n} OFFSET {offset}'
                    ).to_arrow_table()
                    budget -= page.nbytes
                    if budget < 0:
                        raise ChatQueryLimitError(f"Table data is too large for chat queries (at {name}).")
                    writer.write_table(page)
                    if page.num_rows < n:
                        break
                    offset += page.num_rows
            blobs[name] = sink.getvalue().to_pybytes()
        cursor.execute("COMMIT")
        committed = True
    except duckdb.InterruptException as exc:
        raise ChatQueryLimitError("Chat query timed out while loading data.") from exc
    finally:
        stop.set()
        thread.join()
        if not committed:
            try:
                cursor.execute("ROLLBACK")
            except Exception:  # noqa: BLE001 - transaction may already be gone
                pass
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
