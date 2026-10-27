"""Tests for scripts/colab_backfill_checks.py: append-only proof, runner caps, resume bookkeeping."""
import re
from pathlib import Path

import duckdb
import pytest

from scripts import colab_backfill_checks as chk

ROOT = Path(__file__).resolve().parent.parent


def _make(path, rows, extra_tables=True):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE edgar_embeddings (ticker VARCHAR, accession VARCHAR, text VARCHAR, "
                "embedding FLOAT[], section_id VARCHAR, chunk_index INTEGER)")
    for r in rows:
        con.execute("INSERT INTO edgar_embeddings VALUES (?, ?, ?, ?, ?, ?)", r)
    if extra_tables:
        con.execute("CREATE TABLE polygon_tickers (ticker VARCHAR PRIMARY KEY, name VARCHAR)")
        con.execute("INSERT INTO polygon_tickers VALUES ('AAPL', 'Apple'), ('MSFT', 'Microsoft')")
    con.close()


ORIG = [
    ("AAPL", "a-1", "t1", [0.5, 0.25], "s1", 0),
    ("AAPL", "a-1", "t2", [0.5, 0.75], "s1", 1),
    ("MSFT", "m-1", "t3", None, None, 0),
]


@pytest.fixture
def dbs(tmp_path):
    orig, new = tmp_path / "orig.duckdb", tmp_path / "new.duckdb"
    _make(orig, ORIG)
    return orig, new


def _after(new, rows, mutate=None):
    _make(new, rows)
    if mutate:
        con = duckdb.connect(str(new))
        for sql in ([mutate] if isinstance(mutate, str) else mutate):
            con.execute(sql)
        con.close()


NEW_ROW = ("NVDA", "n-1", "t9", [0.1, 0.2], "s1", 0)


def test_pure_append_passes_and_reports_counts(dbs):
    orig, new = dbs
    _after(new, ORIG + [NEW_ROW], "CREATE TABLE brand_new (x INTEGER)")  # extra tables are fine
    report = chk.append_only_proof(str(orig), str(new))
    assert report["edgar_embeddings"] == {"before": 3, "after": 4, "added": 1}
    assert report["polygon_tickers"] == {"before": 2, "after": 2, "added": 0}


def test_identical_db_passes_including_null_rows(dbs):
    orig, new = dbs
    _after(new, ORIG)
    assert chk.append_only_proof(str(orig), str(new))["edgar_embeddings"]["added"] == 0


def test_deleted_row_fails(dbs):
    orig, new = dbs
    _after(new, ORIG[:2] + [NEW_ROW])  # MSFT row gone but count of the table is still >= before
    with pytest.raises(RuntimeError, match="edgar_embeddings: 1 original row"):
        chk.append_only_proof(str(orig), str(new))


def test_shrunk_table_fails(dbs):
    orig, new = dbs
    _after(new, ORIG[:2])
    with pytest.raises(RuntimeError, match="rows shrank 3 -> 2"):
        chk.append_only_proof(str(orig), str(new))


@pytest.mark.parametrize("sql", [
    "UPDATE edgar_embeddings SET text = 'changed' WHERE ticker = 'MSFT'",
    "UPDATE edgar_embeddings SET embedding = [0.5, 0.26] WHERE chunk_index = 0 AND ticker = 'AAPL'",
    "UPDATE edgar_embeddings SET section_id = 's2' WHERE chunk_index = 1",
    "UPDATE polygon_tickers SET name = 'X' WHERE ticker = 'AAPL'",
])
def test_modified_row_fails_even_when_counts_grow(dbs, sql):
    orig, new = dbs
    _after(new, ORIG + [NEW_ROW], sql)
    with pytest.raises(RuntimeError, match="missing or modified"):
        chk.append_only_proof(str(orig), str(new))


def test_duplicate_original_rows_are_compared_as_a_multiset(tmp_path):
    orig, new = tmp_path / "o.duckdb", tmp_path / "n.duckdb"
    dup = ("AAPL", "a-1", "same", [1.0], "s", 0)
    _make(orig, [dup, dup])
    _make(new, [dup, NEW_ROW])  # one copy of the duplicate dropped, count unchanged
    with pytest.raises(RuntimeError, match="original row"):
        chk.append_only_proof(str(orig), str(new))


def test_dropped_table_and_dropped_column_fail(dbs):
    orig, new = dbs
    _after(new, ORIG, "DROP TABLE polygon_tickers")
    with pytest.raises(RuntimeError, match="polygon_tickers: table missing"):
        chk.append_only_proof(str(orig), str(new))
    _after(tmp := new.with_name("n2.duckdb"), ORIG, "ALTER TABLE edgar_embeddings DROP COLUMN text")
    with pytest.raises(RuntimeError, match="columns dropped"):
        chk.append_only_proof(str(orig), str(tmp))


def test_added_column_is_allowed(dbs):
    orig, new = dbs
    _after(new, ORIG + [NEW_ROW], "ALTER TABLE edgar_embeddings ADD COLUMN extra VARCHAR")
    assert chk.append_only_proof(str(orig), str(new))["edgar_embeddings"]["added"] == 1


def test_missing_file_same_file_and_empty_original(dbs, tmp_path):
    orig, new = dbs
    with pytest.raises(RuntimeError, match="missing file"):
        chk.append_only_proof(str(orig), str(new))
    with pytest.raises(RuntimeError, match="same file"):
        chk.append_only_proof(str(orig), str(orig))
    empty = tmp_path / "e.duckdb"
    duckdb.connect(str(empty)).close()
    _make(new, ORIG)
    with pytest.raises(RuntimeError, match="no tables"):
        chk.append_only_proof(str(empty), str(new))


def test_proof_opens_both_files_read_only(dbs):
    orig, new = dbs
    _after(new, ORIG + [NEW_ROW])
    before = (orig.read_bytes(), new.read_bytes())
    chk.append_only_proof(str(orig), str(new))
    assert (orig.read_bytes(), new.read_bytes()) == before
    assert not (orig.with_name(orig.name + ".wal")).exists()


# ── caps ────────────────────────────────────────────────────────────────────

def test_caps_accept_a_full_scope():
    chk.validate_caps([f"T{i}" for i in range(36)], 3, 8, 7200)
    chk.validate_caps(["A"], 1, 1, 60)
    chk.validate_caps([f"T{i}" for i in range(50)], 8, 10, 21600)


@pytest.mark.parametrize("args", [
    ([], 3, 8, 7200),
    ([f"T{i}" for i in range(51)], 3, 8, 7200),
    (["A", "A"], 3, 8, 7200),
    (["bad ticker"], 3, 8, 7200),
    (["TOOLONGTICKER1"], 3, 8, 7200),
    (["A"], 0, 8, 7200), (["A"], 9, 8, 7200), (["A"], True, 8, 7200), (["A"], "3", 8, 7200),
    (["A"], 3, 0, 7200), (["A"], 3, 11, 7200),
    (["A"], 3, 8, 59), (["A"], 3, 8, 21601), (["A"], 3, 8, 7200.0),
])
def test_caps_reject_out_of_range(args):
    with pytest.raises(ValueError):
        chk.validate_caps(*args)


def test_caps_match_the_runner_script():
    sh = (ROOT / "scripts" / "run_hf_backfill.sh").read_text()

    def bounds(var):
        m = re.search(rf'"\${var}" -ge (\d+) \].*?"\${var}" -le (\d+)', sh)
        assert m, var
        return int(m.group(1)), int(m.group(2))

    assert bounds("MAX_TICKERS") == chk.MAX_TICKERS_LIMIT
    assert bounds("DEADLINE") == chk.DEADLINE_LIMIT
    assert bounds("QUARTERS") == chk.QUARTERS_LIMIT
    assert int(re.search(r'MAX_TICKERS="\$\{BACKFILL_MAX_TICKERS:-(\d+)\}"', sh).group(1)) == chk.DEFAULT_GROUP_SIZE
    assert chk.TICKER_RE.pattern == re.search(r"\[\[ \"\$t\" =~ (\^.*\$) \]\]", sh).group(1)


# ── resume bookkeeping ──────────────────────────────────────────────────────

def test_pending_groups_skips_completed_and_chunks():
    tickers = ["A", "B", "C", "D", "E"]
    got = list(chk.pending_groups(["annual", "10-Q"], tickers, ["annual:B", "annual:C", "10-Q:A"], 2))
    assert got == [("annual", ["A", "D"]), ("annual", ["E"]), ("10-Q", ["B", "C"]), ("10-Q", ["D", "E"])]
    assert list(chk.pending_groups(["annual"], ["A"], ["annual:A"], 8)) == []


def test_mark_done_is_idempotent_sorted_and_non_mutating():
    meta = {"run_id": "r", "completed": ["annual:B"]}
    out = chk.mark_done(chk.mark_done(meta, "10-Q", ["Z", "A"]), "10-Q", ["A"])
    assert out["completed"] == ["10-Q:A", "10-Q:Z", "annual:B"] and out["run_id"] == "r"
    assert meta == {"run_id": "r", "completed": ["annual:B"]}


def test_load_meta(tmp_path):
    assert chk.load_meta(str(tmp_path / "none.json")) is None
    p = tmp_path / "m.json"
    p.write_text('{"a": 1}')
    assert chk.load_meta(str(p)) == {"a": 1}
