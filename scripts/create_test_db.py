"""
create_test_db.py — Create a minimal DuckDB with mock XBRL facts for Phase 12 testing.

Generates realistic XBRL data for NVDA, AMD, MU so the shadow deployment
and calibration scripts can run locally without downloading SEC filings.
"""
import os
import duckdb
from pathlib import Path

# Write to a DEDICATED test path — NEVER the production corpus (./data/rag.duckdb),
# which this script deletes to start fresh. Override with TEST_DB_PATH if needed.
DB_PATH = Path(os.getenv("TEST_DB_PATH", "./data/test_rag.duckdb"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Safety guard: refuse to clobber what looks like a real corpus (the test DB is
# ~1 MB; the production corpus is tens of MB). Prevents accidental data loss if
# DB_PATH is ever pointed at the prod file.
if DB_PATH.exists():
    if DB_PATH.stat().st_size > 5_000_000:
        raise SystemExit(
            f"Refusing to overwrite {DB_PATH} ({DB_PATH.stat().st_size/1e6:.1f} MB) — "
            "looks like a real corpus, not a test DB. Set TEST_DB_PATH to a fresh path."
        )
    DB_PATH.unlink()

conn = duckdb.connect(str(DB_PATH))

# Create tables matching the production schema
conn.execute("""
CREATE TABLE IF NOT EXISTS edgar_embeddings (
    ticker VARCHAR,
    accession VARCHAR,
    chunk_index INTEGER,
    chunk_text VARCHAR,
    section_id VARCHAR,
    form_type VARCHAR,
    period_of_report VARCHAR,
    embedding FLOAT[384]
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS graph_triples (
    ticker VARCHAR,
    subject VARCHAR,
    predicate VARCHAR,
    object VARCHAR,
    subject_type VARCHAR,
    object_type VARCHAR,
    chunk_id VARCHAR,
    source_file VARCHAR,
    source_loc VARCHAR,
    confidence DOUBLE
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS xbrl_facts (
    ticker VARCHAR,
    concept VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    period_end VARCHAR,
    accession VARCHAR,
    form_type VARCHAR
)
""")

# Mock XBRL facts — realistic values (in millions USD)
# Based on actual 10-K filings
COMPANIES = {
    "NVDA": {
        "accession": "0001045810-25-000020",
        "form_type": "10-K",
        "periods": ["2025-01-26", "2024-01-28"],
        "facts": {
            "Revenues": [130497e6, 60922e6],
            "CostOfRevenue": [31722e6, 16621e6],
            "GrossProfit": [98775e6, 44301e6],
            "OperatingIncomeLoss": [81453e6, 32972e6],
            "NetIncomeLoss": [72880e6, 29760e6],
            "ResearchAndDevelopmentExpense": [12913e6, 8675e6],
            "Assets": [112663e6, 65728e6],
            "Liabilities": [38764e6, 22772e6],
            "StockholdersEquity": [73899e6, 42956e6],
            "LongTermDebt": [8463e6, 9753e6],
            "CashAndEquivalents": [31436e6, 15328e6],
            "CurrentAssets": [80414e6, 44327e6],
            "CurrentLiabilities": [25053e6, 14330e6],
            "NetCashProvidedByUsedInOperatingActivities": [60853e6, 28090e6],
            "PaymentsToAcquirePropertyPlantAndEquipment": [4217e6, 1069e6],
        },
    },
    "AMD": {
        "accession": "0000002488-25-000012",
        "form_type": "10-K",
        "periods": ["2024-12-28", "2023-12-30"],
        "facts": {
            "Revenues": [25785e6, 22680e6],
            "CostOfRevenue": [12345e6, 10850e6],
            "GrossProfit": [13440e6, 11830e6],
            "OperatingIncomeLoss": [5423e6, 4010e6],
            "NetIncomeLoss": [5474e6, 1320e6],
            "ResearchAndDevelopmentExpense": [6232e6, 5871e6],
            "Assets": [67850e6, 67580e6],
            "Liabilities": [27283e6, 27100e6],
            "StockholdersEquity": [40567e6, 40480e6],
            "LongTermDebt": [1715e6, 1718e6],
            "CashAndEquivalents": [5160e6, 3924e6],
            "CurrentAssets": [26462e6, 22580e6],
            "CurrentLiabilities": [14871e6, 12340e6],
            "NetCashProvidedByUsedInOperatingActivities": [4350e6, 1870e6],
            "PaymentsToAcquirePropertyPlantAndEquipment": [1200e6, 980e6],
        },
    },
    "MU": {
        "accession": "00000723125-25-000012",
        "form_type": "10-K",
        "periods": ["2024-08-29", "2023-08-31"],
        "facts": {
            "Revenues": [25111e6, 15540e6],
            "CostOfRevenue": [17260e6, 13700e6],
            "GrossProfit": [7851e6, 1840e6],
            "OperatingIncomeLoss": [3241e6, -5732e6],
            "NetIncomeLoss": [2768e6, -5833e6],
            "ResearchAndDevelopmentExpense": [3210e6, 3120e6],
            "Assets": [68210e6, 62010e6],
            "Liabilities": [26400e6, 24800e6],
            "StockholdersEquity": [41810e6, 37210e6],
            "LongTermDebt": [12100e6, 11800e6],
            "CashAndEquivalents": [8200e6, 6100e6],
            "CurrentAssets": [24500e6, 20100e6],
            "CurrentLiabilities": [11200e6, 10500e6],
            "NetCashProvidedByUsedInOperatingActivities": [8700e6, 1400e6],
            "PaymentsToAcquirePropertyPlantAndEquipment": [4500e6, 3800e6],
        },
    },
}

# Insert XBRL facts
for ticker, data in COMPANIES.items():
    for concept, values in data["facts"].items():
        for i, (period, value) in enumerate(zip(data["periods"], values)):
            conn.execute(
                """INSERT INTO xbrl_facts (ticker, concept, value, unit, period_end, accession, form_type)
                   VALUES (?, ?, ?, 'USD', ?, ?, ?)""",
                [ticker, concept, float(value), period, data["accession"], data["form_type"]],
            )

# Insert some graph triples
triples = [
    ("NVDA", "NVIDIA", "COMPETES_WITH", "AMD", "Company", "Company", "NVDA:0001045810-25-000020:0", "10-K", "Item 1", 0.95),
    ("NVDA", "NVIDIA", "COMPETES_WITH", "Intel", "Company", "Company", "NVDA:0001045810-25-000020:0", "10-K", "Item 1", 0.90),
    ("NVDA", "NVIDIA", "HAS_REVENUE", "130.5B", "Company", "Metric", "NVDA:0001045810-25-000020:1", "10-K", "Item 8", 0.98),
    ("NVDA", "NVIDIA", "HAS_GROSS_MARGIN", "75.7%", "Company", "Metric", "NVDA:0001045810-25-000020:1", "10-K", "Item 8", 0.98),
    ("AMD", "AMD", "COMPETES_WITH", "NVIDIA", "Company", "Company", "AMD:0000002488-25-000012:0", "10-K", "Item 1", 0.95),
    ("AMD", "AMD", "HAS_REVENUE", "25.8B", "Company", "Metric", "AMD:0000002488-25-000012:1", "10-K", "Item 8", 0.98),
    ("MU", "Micron", "COMPETES_WITH", "Samsung", "Company", "Company", "MU:00000723125-25-000012:0", "10-K", "Item 1", 0.85),
    ("MU", "Micron", "HAS_REVENUE", "25.1B", "Company", "Metric", "MU:00000723125-25-000012:1", "10-K", "Item 8", 0.98),
]
for t in triples:
    conn.execute(
        """INSERT INTO graph_triples (ticker, subject, predicate, object, subject_type, object_type, chunk_id, source_file, source_loc, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        t,
    )

# Insert some embedding chunks
chunks = [
    ("NVDA", "0001045810-25-000020", 0, "NVIDIA Corporation designs and manufactures graphics processing units (GPUs) for gaming, professional visualization, data center, and automotive markets. The company reported record revenue of $130.5 billion for fiscal year 2025.", "Item 1", "10-K", "2025-01-26"),
    ("NVDA", "0001045810-25-000020", 1, "Revenue increased 114% year-over-year driven by strong demand for our data center GPUs used in artificial intelligence and machine learning workloads. Gross margin expanded to 75.7% from 72.9% in the prior year.", "Item 7", "10-K", "2025-01-26"),
    ("AMD", "0000002488-25-000012", 0, "Advanced Micro Devices, Inc. is a global semiconductor company. Our products include x86 microprocessors, GPUs, and adaptive processors for data center, gaming, and embedded markets.", "Item 1", "10-K", "2024-12-28"),
    ("AMD", "0000002488-25-000012", 1, "Revenue for 2024 was $25.8 billion, up 14% from 2023, driven by growth in data center segment. Operating income was $5.4 billion.", "Item 7", "10-K", "2024-12-28"),
    ("MU", "00000723125-25-000012", 0, "Micron Technology, Inc. is a leader in innovative memory and storage solutions. Our products include DRAM, NAND, and NOR flash memory.", "Item 1", "10-K", "2024-08-29"),
    ("MU", "00000723125-25-000012", 1, "Revenue for fiscal 2024 was $25.1 billion, a 62% increase from fiscal 2023, driven by strong AI demand for HBM (High Bandwidth Memory) products.", "Item 7", "10-K", "2024-08-29"),
]
for c in chunks:
    conn.execute(
        """INSERT INTO edgar_embeddings (ticker, accession, chunk_index, chunk_text, section_id, form_type, period_of_report)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        c,
    )

conn.close()

# Verify
conn = duckdb.connect(str(DB_PATH), read_only=True)
xbrl_count = conn.execute("SELECT count(*) FROM xbrl_facts").fetchone()[0]
triple_count = conn.execute("SELECT count(*) FROM graph_triples").fetchone()[0]
chunk_count = conn.execute("SELECT count(*) FROM edgar_embeddings").fetchone()[0]
tickers = conn.execute("SELECT DISTINCT ticker FROM xbrl_facts").fetchall()
conn.close()

print(f"\nCreated test DB at {DB_PATH}")
print(f"   XBRL facts:  {xbrl_count}")
print(f"   Graph triples: {triple_count}")
print(f"   Embeddings:  {chunk_count}")
print(f"   Tickers:     {', '.join(t[0] for t in tickers)}")
