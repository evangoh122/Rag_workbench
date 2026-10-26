"""Chat SQL must not reach files or the catalog, even if the blocklist is bypassed."""
import time
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from api.services import chat_sandbox
from api.services.chat_engine import chat_sql, validate_read_only_sql
from api.services.chat_sandbox import (
    ChatQueryLimitError,
    build_chat_sandbox,
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
def sandbox(source):
    sb = build_chat_sandbox(source, "SELECT * FROM xbrl_facts")
    yield sb
    sb.close()


@pytest.fixture
def data_file(tmp_path):
    csv = tmp_path / "secret.csv"
    csv.write_text("a,b\n1,2\n")
    return csv


def _exploits(path: str) -> dict[str, str]:
    return {
        "quoted_path": f"SELECT * FROM '{path}'",
        "read_csv": f"SELECT * FROM read_csv('{path}')",
        "sniff_csv": f"SELECT * FROM sniff_csv('{path}')",
        "read_json_auto": f"SELECT * FROM read_json_auto('{path}')",
        "read_ndjson": f"SELECT * FROM read_ndjson('{path}')",
        "parquet_scan": f"SELECT * FROM parquet_scan('{path}')",
        "query": f"SELECT * FROM query('SELECT * FROM ''{path}''')",
        "query_table": "SELECT * FROM query_table('private_tokens')",
        "copy_out": f"COPY xbrl_facts TO '{path}.out.csv'",
    }


def test_sandbox_blocks_file_access_at_engine_level(sandbox, data_file):
    for name, sql in _exploits(str(data_file)).items():
        with pytest.raises(duckdb.Error):
            sandbox.execute(sql).fetchall()


def test_sandbox_config_is_locked(sandbox):
    assert sandbox.execute("SELECT current_setting('enable_external_access')").fetchone()[0] is False
    for sql in (
        "SET enable_external_access=true",
        "SET lock_configuration=false",
        "RESET enable_external_access",
    ):
        with pytest.raises(duckdb.Error):
            sandbox.execute(sql)


def test_sandbox_only_exposes_referenced_allowlisted_tables(source):
    sb = build_chat_sandbox(source, "SELECT * FROM xbrl_facts, private_tokens")
    try:
        names = {r[0] for r in sb.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        assert names == {"xbrl_facts"}
        with pytest.raises(duckdb.CatalogException):
            sb.execute("SELECT * FROM private_tokens")
    finally:
        sb.close()


def test_shared_connection_is_not_locked(source, data_file):
    build_chat_sandbox(source, "SELECT * FROM xbrl_facts").close()
    assert source.execute("SELECT count(*) FROM read_csv(?)", [str(data_file)]).fetchone()[0] == 1


def test_positive_select_over_allowed_table(source):
    df = run_chat_query(source, 'SELECT ticker, value FROM "XBRL_FACTS" ORDER BY value')
    assert df.rows() == [("AAPL", 150.0), ("MSFT", 400.0)]


# --- P1 race: mirroring must use a request-owned cursor -------------------
class _NoDirectExecute:
    """Shared-connection stand-in whose own result slot must never be touched."""

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
    sb = build_chat_sandbox(wrapper, "SELECT * FROM xbrl_facts")
    try:
        assert sb.execute("SELECT count(*) FROM xbrl_facts").fetchone()[0] == 2
    finally:
        sb.close()
    assert len(wrapper.cursors) == 1
    with pytest.raises(duckdb.Error):
        wrapper.cursors[0].execute("SELECT 1")  # closed


def test_pending_result_on_shared_connection_does_not_leak_into_table(source):
    source.execute("SELECT * FROM private_tokens")  # another request's pending result
    sb = build_chat_sandbox(source, "SELECT * FROM xbrl_facts")
    try:
        assert sb.execute("SELECT ticker FROM xbrl_facts ORDER BY 1").fetchall() == [("AAPL",), ("MSFT",)]
    finally:
        sb.close()


# --- P1 limits applied before copying, bounded by bytes ---------------------
def test_byte_budget_refuses_large_tables(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", 1024)
    source.execute("CREATE TABLE polygon_bars AS SELECT range AS ts, repeat('x', 100) AS pad FROM range(100000)")
    with pytest.raises(ChatQueryLimitError, match="too large"):
        build_chat_sandbox(source, "SELECT * FROM polygon_bars")


def test_byte_budget_spans_multiple_tables(source, monkeypatch):
    source.execute("CREATE TABLE polygon_bars AS SELECT range AS ts, repeat('x', 100) AS pad FROM range(2000)")
    source.execute("CREATE TABLE graph_triples AS SELECT range AS id, repeat('y', 100) AS pad FROM range(2000)")
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", 300_000)  # fits one table (~224KB), not two
    build_chat_sandbox(source, "SELECT * FROM polygon_bars").close()
    with pytest.raises(ChatQueryLimitError):
        build_chat_sandbox(source, "SELECT * FROM polygon_bars, graph_triples")


def test_limits_set_before_copy(source, monkeypatch):
    order = []
    real_connect = duckdb.connect

    class Spy:
        def __init__(self, conn):
            self._c = conn

        def execute(self, sql, *a):
            order.append(sql)
            return self._c.execute(sql, *a)

        def __getattr__(self, n):
            return getattr(self._c, n)

    monkeypatch.setattr(chat_sandbox.duckdb, "connect", lambda *a, **k: Spy(real_connect(*a, **k)))
    build_chat_sandbox(source, "SELECT * FROM xbrl_facts").close()
    first_mem = next(i for i, s in enumerate(order) if "memory_limit" in s)
    first_copy = next(i for i, s in enumerate(order) if s.startswith("CREATE TABLE"))
    assert first_mem < first_copy


# --- P2 quoted identifiers, table detection --------------------------------
@pytest.mark.parametrize("sql", ['SELECT * FROM "STOCK_QUOTES"', 'SELECT a FROM "my_table" JOIN "other" ON 1=1'])
def test_plain_quoted_identifiers_accepted(sql):
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


def test_blocklist_allows_normal_select():
    assert validate_read_only_sql("SELECT ticker FROM xbrl_facts LIMIT 5") is None


def test_table_detection_ignores_literals_comments_and_ctes():
    assert referenced_tables("SELECT 'xbrl_facts' AS label") == []
    assert referenced_tables("SELECT 1 -- from xbrl_facts\n/* join polygon_bars */") == []
    assert referenced_tables("WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts") == []
    assert referenced_tables("SELECT * FROM xbrl_facts x JOIN polygon_bars b ON 1=1") == ["polygon_bars", "xbrl_facts"]
    assert referenced_tables("SELECT * FROM private_tokens") == []


def test_literal_and_cte_do_not_copy_big_table(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_MIRROR_BYTES", 1)  # any copy would be refused
    for sql in ("SELECT 'xbrl_facts' AS label", "WITH xbrl_facts AS (SELECT 1 n) SELECT * FROM xbrl_facts"):
        assert run_chat_query(source, sql).height == 1


# --- resource exhaustion ---------------------------------------------------
def test_huge_string_is_refused(source):
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT repeat('x', 300000000)")
    assert validate_read_only_sql("SELECT repeat('x', 300000000)") is not None


def test_cells_and_rows_are_capped(source):
    df = run_chat_query(source, "SELECT string_agg('x', '') OVER () || ('y' || range::VARCHAR) AS s, range AS n FROM range(1000)")
    assert df.height == chat_sandbox.MAX_RESULT_ROWS
    assert max(len(v) for v in df["s"]) <= chat_sandbox.MAX_CELL_CHARS


def test_long_cell_is_truncated(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_CELL_CHARS", 10)
    df = run_chat_query(source, "SELECT string_agg(range::VARCHAR, ',') AS s FROM range(1000)")
    assert len(df["s"][0]) == 10


def test_result_byte_cap(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "MAX_RESULT_BYTES", 100)
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT string_agg(range::VARCHAR, ',') AS s FROM range(5000)")


def test_runaway_query_hits_deadline(source, monkeypatch):
    monkeypatch.setattr(chat_sandbox, "QUERY_DEADLINE_SECONDS", 1.0)
    start = time.monotonic()
    with pytest.raises(ChatQueryLimitError):
        run_chat_query(source, "SELECT sum(range) FROM range(1000000000000)")
    assert time.monotonic() - start < 8


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
