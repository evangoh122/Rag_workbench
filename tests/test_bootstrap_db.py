import duckdb

from scripts.bootstrap_db import create_tables


def test_create_tables_migrates_existing_xbrl_frame_column():
    """Bootstrap table creation adds frame to a legacy XBRL schema."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE SEQUENCE xbrl_facts_seq START 1")
    conn.execute("CREATE SEQUENCE filing_chunks_seq START 1")
    conn.execute("""
        CREATE TABLE xbrl_facts (
            id INTEGER PRIMARY KEY DEFAULT(nextval('xbrl_facts_seq')),
            ticker VARCHAR NOT NULL,
            cik VARCHAR NOT NULL,
            concept VARCHAR NOT NULL,
            value DOUBLE,
            unit VARCHAR,
            period_end VARCHAR,
            period_start VARCHAR,
            form_type VARCHAR,
            accession VARCHAR,
            filed VARCHAR,
            fiscal_year INTEGER,
            fiscal_period VARCHAR
        )
    """)

    create_tables(conn)

    columns = {row[0] for row in conn.execute("DESCRIBE xbrl_facts").fetchall()}
    assert "frame" in columns
    conn.close()
