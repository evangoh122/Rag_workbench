"""Isolated DuckDB instance for LLM-generated chat SQL.

``enable_external_access`` and ``lock_configuration`` are instance-wide in
DuckDB, so they cannot be applied to the shared app connection without breaking
the runtime snapshot export (COPY / read_parquet) and other writers.  Instead,
each chat query runs on a throwaway in-memory instance that only contains copies
of the allow-listed tables the query references, with external access disabled
and the configuration locked before the generated SQL executes.

Mirroring reads through a request-owned cursor (never the shared connection's
own result slot) and streams Arrow batches under a byte budget.
"""
import re
import threading
import time
from typing import Any

import duckdb
import polars as pl

# Tables the chat model is told about (see chat_engine.SCHEMA).
ALLOWED_TABLES = frozenset({
    "xbrl_facts", "edgar_embeddings", "ticker_embeddings", "polygon_tickers",
    "polygon_bars", "graph_triples",
})

MAX_MIRROR_BYTES = 256 * 1024 * 1024   # total across all mirrored tables
QUERY_HEADROOM_BYTES = 128 * 1024 * 1024
BATCH_ROWS = 50_000
QUERY_DEADLINE_SECONDS = 10.0
MAX_RESULT_ROWS = 100
MAX_CELL_CHARS = 10_000
MAX_RESULT_BYTES = 2 * 1024 * 1024


class ChatQueryLimitError(Exception):
    """Raised when a chat query exceeds a size or time budget."""


def _strip_literals_and_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n\r]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


_CTE_RE = re.compile(
    r'(?:\bwith\b|,)\s*(?:recursive\s+)?"?([a-z_][a-z0-9_]*)"?\s*(?:\([^()]*\))?\s+as\s*'
    r"(?:(?:not\s+)?materialized\s*)?\(",
    re.IGNORECASE,
)
_REF_RE = re.compile(r'(?:\bfrom\b|\bjoin\b|,)\s*"?([a-z_][a-z0-9_]*)"?', re.IGNORECASE)


def referenced_tables(sql: str) -> list[str]:
    """Allow-listed tables referenced in FROM/JOIN positions, excluding CTE names."""
    text = _strip_literals_and_comments(sql)
    ctes = {m.lower() for m in _CTE_RE.findall(text)}
    refs = {m.lower() for m in _REF_RE.findall(text)}
    return sorted((refs - ctes) & ALLOWED_TABLES)


def _mirror_table(source: Any, sandbox: Any, name: str, budget: list[int], deadline: float) -> None:
    reader = source.execute(f'SELECT * FROM "{name}"').to_arrow_reader(BATCH_ROWS)
    created = False
    for batch in reader:
        if time.monotonic() > deadline:
            raise ChatQueryLimitError("Chat query timed out while loading data.")
        budget[0] -= batch.nbytes
        if budget[0] < 0:
            raise ChatQueryLimitError(f"Table data is too large for chat queries (at {name}).")
        sandbox.register("_mirror", pl.from_arrow(batch))
        if created:
            sandbox.execute(f'INSERT INTO "{name}" SELECT * FROM _mirror')
        else:
            sandbox.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _mirror')
            created = True
        sandbox.unregister("_mirror")
    if not created:  # empty table: keep the schema
        sandbox.register("_mirror", pl.from_arrow(reader.schema.empty_table()))
        sandbox.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _mirror')
        sandbox.unregister("_mirror")


def build_chat_sandbox(source: Any, sql: str, deadline: float | None = None) -> duckdb.DuckDBPyConnection:
    """Return a locked-down in-memory connection holding the tables ``sql`` needs.

    ``source`` is only used through a request-owned cursor that is closed here.
    """
    if deadline is None:
        deadline = time.monotonic() + QUERY_DEADLINE_SECONDS
    sandbox = duckdb.connect(":memory:")
    cursor = source.cursor()
    budget = [MAX_MIRROR_BYTES]
    try:
        # Limits first, so the copy itself is bounded.
        sandbox.execute("SET threads TO 2")
        sandbox.execute(f"SET memory_limit TO '{max(MAX_MIRROR_BYTES * 2 // (1024 * 1024), 64)}MB'")
        for name in referenced_tables(sql):
            try:
                _mirror_table(cursor, sandbox, name, budget, deadline)
            except duckdb.CatalogException:
                continue  # table absent in this database
        used = MAX_MIRROR_BYTES - budget[0]
        limit_mb = (used * 2 + QUERY_HEADROOM_BYTES) // (1024 * 1024) + 1
        sandbox.execute(f"SET memory_limit TO '{limit_mb}MB'")
        sandbox.execute("SET python_enable_replacements=false")
        sandbox.execute("SET enable_external_access=false")
        sandbox.execute("SET lock_configuration=true")
    except BaseException:
        sandbox.close()
        raise
    finally:
        cursor.close()
    return sandbox


# DuckDB does not account single huge string allocations against memory_limit,
# so string-amplifying functions are refused outright.
_AMPLIFIERS_RE = re.compile(r"\b(repeat|lpad|rpad)\b", re.IGNORECASE)


def run_chat_query(source: Any, sql: str) -> pl.DataFrame:
    """Run generated SQL in a sandbox with a deadline and output caps."""
    if _AMPLIFIERS_RE.search(_strip_literals_and_comments(sql)):
        raise ChatQueryLimitError("String-expanding functions are not allowed in chat queries.")
    deadline = time.monotonic() + QUERY_DEADLINE_SECONDS
    sandbox = build_chat_sandbox(source, sql, deadline)
    timer = threading.Timer(max(deadline - time.monotonic(), 0.01), sandbox.interrupt)
    timer.start()
    try:
        cols = sandbox.execute(f"DESCRIBE SELECT * FROM ({sql}) AS q").fetchall()
        aliases = ", ".join(f"c{i}" for i in range(len(cols)))
        exprs = []
        for i, (name, ctype, *_rest) in enumerate(cols):
            alias = '"' + str(name).replace('"', '""') + '"'
            if re.fullmatch(r"(U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?|FLOAT|DOUBLE|BOOLEAN|DATE|TIMESTAMP.*|DECIMAL.*|TIME.*)", ctype):
                exprs.append(f"c{i} AS {alias}")
            else:
                exprs.append(f"left(CAST(c{i} AS VARCHAR), {MAX_CELL_CHARS}) AS {alias}")
        wrapped = f"SELECT {', '.join(exprs)} FROM (SELECT * FROM ({sql}) AS q({aliases})) LIMIT {MAX_RESULT_ROWS}"
        result = sandbox.execute(wrapped).pl()
    except duckdb.InterruptException as exc:
        raise ChatQueryLimitError("Chat query exceeded its time limit.") from exc
    finally:
        timer.cancel()
        sandbox.close()
    if result.estimated_size() > MAX_RESULT_BYTES:
        raise ChatQueryLimitError("Chat query result is too large.")
    return result
