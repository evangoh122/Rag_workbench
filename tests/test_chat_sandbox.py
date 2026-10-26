"""Chat SQL must not reach files or the catalog and must stay inside hard limits."""
import json
import resource
import subprocess
import time
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from api.services import chat_sandbox
from api.services.chat_engine import chat_sql, validate_read_only_sql
from api.services.chat_sandbox import (
    ChatQueryError,
    ChatQueryLimitError,
    mirror_tables,
    referenced_tables,
    run_chat_query,
)


@pytest.fixture
def source():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE xbrl_facts(ticker VARCHAR, value DOUBLE)")
    conn.execute("INSERT INTO xbrl_facts VALUES ('AAPL', 150.0), ('MSFT', 400.0)")
    conn.execute("CREATE TABLE private_tokens(token VARCHAR)")
    conn.execute("INSERT INTO private_tokens VALUES ('hunter2')")
    yield conn
    conn.close()


@pytest.fixture
def data_file(tmp_path):
    csv = tmp_path / "secret.csv"
    csv.write_text("a,b\n1,2\n")
    return csv


def _worker(sql, blobs=None, seconds=20.0):
    """Run raw SQL in the child, bypassing parent-side table resolution."""
    return chat_sandbox._run_in_worker(blobs or {}, sql, time.monotonic() + seconds)


def _rss_kb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


# ------------------------------------------------------- engine-level lock-down
def _exploits(path: str) -> dict[str, str]:
    return {
        "quoted_path": f"SELECT * FROM '{path}'",
        "read_csv": f"SELECT * FROM read_csv('{path}')",
        "sniff_csv": f"SELECT * FROM sniff_csv('{path}')",
        "read_json_auto": f"SELECT * FROM read_json_auto('{path}')",
        "read_ndjson": f"SELECT * FROM read_ndjson('{path}')",
        "parquet_scan": f"SELECT * FROM parquet_scan('{path}')",
        "query": f"SELECT * FROM query('SELECT * FROM ''{path}''')",
        "glob": "SELECT * FROM glob('/*')",
        "set_unlock": "SET enable_external_access=true",
        "unlock_config": "SET lock_configuration=false",
    }


def test_child_blocks_file_access_and_unlocking(data_file):
    for name, sql in _exploits(str(data_file)).items():
        with pytest.raises(ChatQueryError):
            _worker(sql)


def test_child_has_external_access_disabled():
    assert list(_worker("SELECT current_setting('enable_external_access') AS v")[0].values()) == [False]


def test_child_only_contains_mirrored_tables(source):
    blobs = mirror_tables(source, ["xbrl_facts"], time.monotonic() + 20)
    assert _worker("SELECT count(*) AS n FROM xbrl_facts", blobs) == [{"n": 2}]
    with pytest.raises(ChatQueryError):
        _worker("SELECT * FROM private_tokens", blobs)


def test_shared_connection_is_not_locked(source, data_file):
    run_chat_query(source, "SELECT * FROM xbrl_facts")
    assert source.execute("SELECT count(*) FROM read_csv(?)", [str(data_file)]).fetchone()[0] == 1


def test_positive_select_over_allowed_table(source):
    rows = run_chat_query(source, 'SELECT ticker, value FROM "XBRL_FACTS" ORDER BY value')
    assert rows == [{"ticker": "AAPL", "value": 150.0}, {"ticker": "MSFT", "value": 400.0}]


def test_child_environment_has_no_ambient_credentials(source, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN_FOR_TEST", "s3cr3t")
    seen = {}
    real = subprocess.Popen

    def spy(*a, **k):
        seen["env"] = k.get("env")
        return real(*a, **k)

    monkeypatch.setattr(chat_sandbox.subprocess, "Popen", spy)
    run_chat_query(source, "SELECT 1 AS x")
    assert "SECRET_TOKEN_FOR_TEST" not in seen["env"]


# ------------------------------------------------------------ request-owned cursor
class _NoDirectExecute:
    def __init__(self, real):
        self._real = real
        self.cursors = []

    def execute(self, *a, **k):
        raise AssertionError("mirroring used the shared connection's execute()")

    def cursor(self):
        cur = self._real.cursor()
        self.cursors.append(cur)
        return cur


def test_mirroring_uses_request_owned_cursor_and_closes_it(source):
    wrapper = _NoDirectExecute(source)
    blobs = mirror_tables(wrapper, ["xbrl_facts"], time.monotonic() + 20)
    assert list(blobs) == ["xbrl_facts"]
    assert len(wrapper.cursors) == 1
    with pytest.raises(duckdb.Error):
        wrapper.cursors[0].execute("SELECT 1")  # closed


def test_pending_result_on_shared_connection_does_not_leak_into_table(source):
    source.execute("SELECT * FROM private_tokens")  # another request's pending result
    assert run_chat_query(source, "SELECT ticker FROM xbrl_facts ORDER BY 1") == [
        {"ticker": "AAPL"}, {"ticker": "MSFT"},
    ]


# ------------------------------------------------------------------ byte budgets
def test_byte_budget_refuses_large_tables(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", 1024)
    source.execute("CREATE TABLE polygon_bars AS SELECT range AS ts, 'x' AS pad FROM range(100000)")
    with pytest.raises(ChatQueryLimitError, match="too large"):
        mirror_tables(source, ["polygon_bars"], time.monotonic() + 20)


def test_byte_budget_spans_multiple_tables(source, monkeypatch):
    source.execute("CREATE TABLE polygon_bars AS SELECT range AS ts, 'x' AS pad FROM range(20000)")
    source.execute("CREATE TABLE graph_triples AS SELECT range AS id, 'y' AS pad FROM range(20000)")
    one = sum(len(b) for b in mirror_tables(source, ["polygon_bars"], time.monotonic() + 20).values())
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", int(one * 1.3))
    mirror_tables(source, ["polygon_bars"], time.monotonic() + 20)
    with pytest.raises(ChatQueryLimitError):
        mirror_tables(source, ["polygon_bars", "graph_triples"], time.monotonic() + 20)


# ----------------------------------------------- memory amplification (child limit)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT printf('%2000000000s', 'x') AS s",
        "SELECT repeat('x', 2000000000) AS s",
        "SELECT lpad('x', 2000000000, 'y') AS s",
        "SELECT string_agg(repeat('x', 100000000), '') AS s FROM range(30)",
    ],
)
def test_memory_amplification_is_stopped_without_parent_growth(source, sql):
    before = _rss_kb()
    with pytest.raises(ChatQueryError):
        run_chat_query(source, sql)
    assert _rss_kb() - before < 150 * 1024  # KiB: parent never materialised it


def test_rlimit_as_is_what_stops_the_child(source, monkeypatch):
    """Deterministic: the same query succeeds without the cap and dies with it."""
    sql = "SELECT repeat('x', 300000000) AS s"
    assert len(run_chat_query(source, sql)[0]["s"]) == chat_sandbox.MAX_CELL_CHARS
    monkeypatch.setattr(chat_sandbox, "CHILD_EXTRA_ADDRESS_SPACE", 400 * 1024 * 1024)
    assert run_chat_query(source, "SELECT 1 AS ok") == [{"ok": 1}]  # still usable
    with pytest.raises(ChatQueryError):
        run_chat_query(source, sql)


@pytest.mark.parametrize(
    "sql", ["SELECT printf('%300000000s', 'x') AS s", "SELECT repeat('x', 300000000) AS s"]
)
def test_moderate_amplification_is_capped_and_parent_does_not_grow(source, sql):
    before = _rss_kb()
    try:
        rows = run_chat_query(source, sql)
        assert len(rows[0]["s"]) <= chat_sandbox.MAX_CELL_CHARS
    except ChatQueryError:
        pass  # also acceptable: stopped by the child's limits
    assert _rss_kb() - before < 150 * 1024


# --------------------------------------------------------------------- deadline
def test_runaway_cpu_query_killed_at_deadline(source, monkeypatch):
    # RLIMIT_CPU backs this up at deadline+2s, so require the kill well before it.
    monkeypatch.setattr(chat_sandbox, "QUERY_DEADLINE_SECONDS", 1.0)
    start = time.monotonic()
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT sum(sin(range)) FROM range(1000000000000)")
    assert time.monotonic() - start < 2.4


def test_child_is_reaped_after_timeout(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "QUERY_DEADLINE_SECONDS", 1.0)
    procs = []
    real = subprocess.Popen

    def spy(*a, **k):
        p = real(*a, **k)
        procs.append(p)
        return p

    monkeypatch.setattr(chat_sandbox.subprocess, "Popen", spy)
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT sum(sin(range)) FROM range(1000000000000)")
    assert procs and all(p.poll() is not None for p in procs)


def test_deadline_covers_slow_source_view_during_loading(monkeypatch):
    monkeypatch.setattr(chat_sandbox, "QUERY_DEADLINE_SECONDS", 1.5)
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE VIEW xbrl_facts AS SELECT sum(sin(range)) AS s FROM range(1000000000000)")
    start = time.monotonic()
    try:
        with pytest.raises(ChatQueryLimitError):
            run_chat_query(conn, "SELECT * FROM xbrl_facts")
    finally:
        conn.close()
    assert time.monotonic() - start < 8


def test_pause_between_phases_cannot_extend_deadline(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "QUERY_DEADLINE_SECONDS", 2.0)
    real = chat_sandbox.mirror_tables

    def slow(*a, **k):
        out = real(*a, **k)
        time.sleep(1.5)  # a pause after loading eats into the same budget
        return out

    monkeypatch.setattr(chat_sandbox, "mirror_tables", slow)
    start = time.monotonic()
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT sum(sin(range)) FROM range(1000000000000), xbrl_facts")
    assert time.monotonic() - start < 3.6


# -------------------------------------------------------------------- output caps
def test_rows_and_cells_are_capped(source):
    rows = run_chat_query(source, "SELECT string_agg(range::VARCHAR, ',') OVER () AS s, range AS n FROM range(5000)")
    assert len(rows) == chat_sandbox.MAX_RESULT_ROWS
    assert max(len(r["s"]) for r in rows) <= chat_sandbox.MAX_CELL_CHARS


def test_cap_applies_to_serialized_json_not_raw_size(source, monkeypatch):
    sql = "SELECT string_agg(chr(10), chr(10)) OVER () AS s FROM range(100000)"
    raw = chat_sandbox.MAX_RESULT_ROWS * chat_sandbox.MAX_CELL_CHARS
    # Raw text fits, but "\n" doubles when JSON-escaped, so the payload does not.
    monkeypatch.setattr(chat_sandbox, "MAX_RESULT_BYTES", int(raw * 1.5))
    with pytest.raises(ChatQueryLimitError, match="too large"):
        run_chat_query(source, sql)


def test_returned_json_stays_under_cap(source):
    rows = run_chat_query(source, "SELECT string_agg(chr(10), chr(10)) OVER () AS s FROM range(100000)")
    assert len(json.dumps(rows)) <= chat_sandbox.MAX_RESULT_BYTES


# ----------------------------------------------------------------- validator
@pytest.mark.parametrize("sql", ['SELECT * FROM "STOCK_QUOTES"', 'SELECT a FROM "my_table" JOIN "other" ON 1=1',
                                 "SELECT 'repeat' AS label", "SELECT 1 AS repeat", "SELECT printf('%d', 1)"])
def test_validator_accepts_plain_queries(sql):
    assert validate_read_only_sql(sql) is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM '/etc/passwd'",
        'SELECT * FROM "/etc/passwd"',
        'SELECT * FROM "data.csv"',
        'SELECT * FROM "C:\\x\\y"',
        'SELECT * FROM "*.parquet"',
        "SELECT * FROM sniff_csv('/etc/passwd')",
        "SELECT * FROM read_json_auto('/x.json')",
        "SELECT * FROM read_ndjson('/x.json')",
        "SELECT * FROM parquet_scan('/x.parquet')",
        "SELECT * FROM query('select 1')",
        "SELECT * FROM query_table('xbrl_facts')",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM pragma_table_info('xbrl_facts')",
        "SELECT current_setting('enable_external_access')",
    ],
)
def test_blocklist_defense_in_depth(sql):
    assert validate_read_only_sql(sql) is not None


# --------------------------------------------------- AST-based table resolution
@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT * FROM main.xbrl_facts", ["xbrl_facts"]),
        ('SELECT * FROM "main"."XBRL_FACTS"', ["xbrl_facts"]),
        ("SELECT * FROM memory.main.xbrl_facts", ["xbrl_facts"]),
        ("SELECT '--' AS label, ticker FROM xbrl_facts", ["xbrl_facts"]),
        ("SELECT 'xbrl_facts' AS label", []),
        ("SELECT 1 -- from xbrl_facts\n", []),
        ("SELECT 1 a, xbrl_facts b FROM (VALUES (1)) t(xbrl_facts)", []),
        ("WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts", []),
        ("WITH a AS (SELECT 1 n), b AS (SELECT * FROM a) SELECT * FROM b", []),
        # nested scoping: inner CTE shadows only inside its subquery
        ("SELECT * FROM (WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts) s, polygon_bars", ["polygon_bars"]),
        ("WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts JOIN (SELECT * FROM polygon_bars) p ON 1=1", ["polygon_bars"]),
        # a CTE defined later does not shadow an earlier real reference
        ("WITH a AS (SELECT * FROM polygon_bars), polygon_bars AS (SELECT 1) SELECT * FROM a, polygon_bars", ["polygon_bars"]),
        ("SELECT * FROM xbrl_facts x JOIN polygon_bars b ON 1=1 WHERE x.ticker IN (SELECT ticker FROM graph_triples)",
         ["graph_triples", "polygon_bars", "xbrl_facts"]),
    ],
)
def test_ast_table_resolution(sql, expected):
    assert referenced_tables(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM private_tokens",
        "SELECT * FROM '/etc/passwd'",
        "SELECT * FROM other_db.main.xbrl_facts",
        "SELECT * FROM xbrl_facts JOIN private_tokens ON 1=1",
        "COPY xbrl_facts TO 'x.csv'",
    ],
)
def test_ast_resolution_fails_closed(sql):
    with pytest.raises(ChatQueryError):
        referenced_tables(sql)


def test_literal_and_cte_do_not_copy_big_table(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", 1)  # any copy would be refused
    for sql in ("SELECT 'xbrl_facts' AS label", "WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts"):
        assert len(run_chat_query(source, sql)) == 1


def test_end_to_end_exploit_rejected_by_chat_sql(source, data_file, monkeypatch):
    monkeypatch.setattr("api.services.chat_engine.validate_read_only_sql", lambda s: None)
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = (
        f"SELECT * FROM xbrl_facts, read_csv('{data_file}')"
    )
    with patch("api.services.chat_engine.get_sql_client", return_value=client), \
         patch("api.services.chat_engine.Config.get_provider_config", return_value={"model": "m"}), \
         patch("api.services.chat_engine.db_manager.get_connection", return_value=source):
        result = chat_sql("read the file")
    assert result["type"] == "error"
    assert "data" not in result
