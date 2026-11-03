"""Coverage freshness uses actual DuckDB aggregates, never a clock fallback."""
import asyncio
from unittest.mock import patch

import duckdb
import pytest

from api.routes.stats import _coverage_updates, db_manager, get_stats


@pytest.fixture
def conn():
    with duckdb.connect(':memory:') as connection:
        connection.execute('CREATE TABLE edgar_embeddings (ticker VARCHAR, updated_at VARCHAR)')
        yield connection


def test_latest_updates_and_route(conn):
    conn.execute("""INSERT INTO edgar_embeddings VALUES
        ('MU', '2026-10-26T23:00:00-02:00'),
        ('MU', '2026-10-27T11:41:43+00:00'),
        ('NVDA', '2026-10-28T01:30:00+08:00'),
        ('NVDA', 'invalid'), ('AMD', NULL)""")
    expected = {
        'last_updated': '2026-10-27T17:30:00+00:00',
        'ticker_last_updated': {
            'AMD': None, 'MU': '2026-10-27T11:41:43+00:00',
            'NVDA': '2026-10-27T17:30:00+00:00',
        },
    }
    assert _coverage_updates(conn) == expected
    with patch.object(db_manager, 'get_connection', return_value=conn), patch.object(
        db_manager, 'get_review_connection', return_value=conn
    ):
        data = asyncio.run(get_stats())['data']
    assert data['last_updated'] == expected['last_updated']
    assert data['ticker_last_updated'] == expected['ticker_last_updated']


def test_empty_invalid_and_missing_schema(conn):
    assert _coverage_updates(conn) == {'last_updated': None, 'ticker_last_updated': {}}
    conn.execute("INSERT INTO edgar_embeddings VALUES ('MU', 'invalid')")
    assert _coverage_updates(conn) == {'last_updated': None, 'ticker_last_updated': {'MU': None}}
    conn.execute('DROP TABLE edgar_embeddings')
    assert _coverage_updates(conn) == {'last_updated': None, 'ticker_last_updated': {}}
