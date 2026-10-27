"""Tests for scripts/colab_backfill_checks.py: append-only proof, runner caps, resume bookkeeping."""
import json
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


def test_split_complete_reports_tickers_with_missing_accessions():
    missing = [("b", "10-K", "0-1"), ("C", "10-K", "0-2"), ("B", "10-K", "0-3")]
    assert chk.split_complete(["A", "B", "C", "D"], missing) == (["A", "D"], ["B", "C"])
    assert chk.split_complete(["A", "B"], []) == (["A", "B"], [])


# ── B3: column types and views ──────────────────────────────────────────────

def _typed(path, ddl, views=()):
    con = duckdb.connect(str(path))
    con.execute(ddl)
    for v in views:
        con.execute(v)
    con.close()


T_DDL = "CREATE TABLE t (id INTEGER, v FLOAT, e FLOAT[], s VARCHAR)"
T_ROW = "INSERT INTO t VALUES (1, 0.5, [0.5], 'x')"


@pytest.mark.parametrize("alter", [
    "ALTER TABLE t ALTER id TYPE BIGINT",
    "ALTER TABLE t ALTER v TYPE DOUBLE",
    "ALTER TABLE t ALTER e TYPE DOUBLE[]",
    "ALTER TABLE t ALTER s TYPE BLOB USING s::BLOB",
])
def test_changed_column_type_fails_even_if_values_survive(tmp_path, alter):
    orig, new = tmp_path / "o.duckdb", tmp_path / "n.duckdb"
    _typed(orig, T_DDL + ";" + T_ROW)
    _typed(new, T_DDL + ";" + T_ROW + ";" + alter)
    with pytest.raises(RuntimeError, match="column types changed"):
        chk.append_only_proof(str(orig), str(new))


def test_added_columns_and_reordering_are_tolerated(tmp_path):
    orig, new = tmp_path / "o.duckdb", tmp_path / "n.duckdb"
    _typed(orig, T_DDL + ";" + T_ROW + ";INSERT INTO t VALUES (2, 1.5, [1.5], 'y')")
    _typed(new, "CREATE TABLE t (s VARCHAR, extra BIGINT, e FLOAT[], v FLOAT, id INTEGER);"
                "INSERT INTO t VALUES ('y', 7, [1.5], 1.5, 2), ('x', 7, [0.5], 0.5, 1), ('z', 7, [2.5], 2.5, 3)")
    assert chk.append_only_proof(str(orig), str(new))["t"] == {"before": 2, "after": 3, "added": 1}


VIEW = "CREATE VIEW big AS SELECT id FROM t WHERE id > 0"


def test_view_must_exist_with_same_definition(tmp_path):
    orig, new = tmp_path / "o.duckdb", tmp_path / "n.duckdb"
    _typed(orig, T_DDL + ";" + T_ROW, [VIEW])
    _typed(new, T_DDL + ";" + T_ROW, [VIEW, "CREATE VIEW extra_view AS SELECT 1 AS one"])
    assert chk.append_only_proof(str(orig), str(new))["t"]["added"] == 0  # same view + a new view is fine
    _typed(tmp_path / "gone.duckdb", T_DDL + ";" + T_ROW)
    with pytest.raises(RuntimeError, match="view main.big: missing"):
        chk.append_only_proof(str(orig), str(tmp_path / "gone.duckdb"))
    _typed(tmp_path / "chg.duckdb", T_DDL + ";" + T_ROW, ["CREATE VIEW big AS SELECT id FROM t WHERE id > 5"])
    with pytest.raises(RuntimeError, match="view main.big: definition changed"):
        chk.append_only_proof(str(orig), str(tmp_path / "chg.duckdb"))


# ── B2: atomic checkpoints ──────────────────────────────────────────────────

class Crash(Exception):
    pass


def _src(tmp_path, tag):
    d = tmp_path / f"src-{tag}"
    d.mkdir(exist_ok=True)
    (d / "rag.duckdb").write_bytes(f"db-{tag}".encode() * 100)
    (d / "before.json").write_text(json.dumps({"tag": tag}))
    return str(d / "rag.duckdb"), {"before.json": str(d / "before.json")}


def _write(tmp_path, ck, tag, on_step=None, pinned="P1"):
    db, files = _src(tmp_path, tag)
    return chk.write_checkpoint(str(ck), db, files, {"tag": tag, "completed": [tag]}, pinned, on_step)


def test_checkpoint_round_trip_and_restore(tmp_path):
    ck = tmp_path / "ck"
    manifest = _write(tmp_path, ck, "a")
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert why == "ok" and got["meta"] == {"tag": "a", "completed": ["a"]}
    assert got["db_sha256"] == manifest["db_sha256"] == chk.sha256_file(got["db"])
    assert chk.read_checkpoint(str(ck))[1] == "ok"  # no revision requested: any is accepted
    out = tmp_path / "out"
    out.mkdir()
    chk.restore_checkpoint(got, str(out / "rag.duckdb"), {"before.json": str(out / "b.json")})
    assert (out / "rag.duckdb").read_bytes() == b"db-a" * 100 and json.loads((out / "b.json").read_text()) == {"tag": "a"}
    with pytest.raises(RuntimeError, match="no nope.json"):
        chk.restore_checkpoint(got, str(out / "x"), {"nope.json": str(out / "n")})


def test_no_checkpoint_and_wrong_revision_are_refused(tmp_path):
    assert chk.read_checkpoint(str(tmp_path / "none"))[0] is None
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "a")
    got, why = chk.read_checkpoint(str(ck), "OTHER")
    assert got is None and "revision" in why


@pytest.mark.parametrize("crash_after", ["db", "files", "manifest", "pointer_tmp"])
def test_crash_before_the_pointer_switch_keeps_the_previous_checkpoint(tmp_path, crash_after):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "old")

    def boom(name):
        if name == crash_after:
            raise Crash

    with pytest.raises(Crash):
        _write(tmp_path, ck, "new", on_step=boom)
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert why == "ok" and got["meta"]["tag"] == "old"
    assert json.loads(open(got["files"]["before.json"]).read()) == {"tag": "old"}  # never new DB + old snapshot
    assert got["db"].endswith("rag.duckdb") and open(got["db"], "rb").read() == b"db-old" * 100
    _write(tmp_path, ck, "next")  # the next write recovers and prunes the orphaned partial version
    assert chk.read_checkpoint(str(ck), "P1")[0]["meta"]["tag"] == "next"
    assert len([d for d in ck.iterdir() if d.name.startswith("v-")]) <= 2


def test_crash_before_the_first_pointer_means_no_checkpoint(tmp_path):
    ck = tmp_path / "ck"

    def boom(name):
        if name == "manifest":
            raise Crash

    with pytest.raises(Crash):
        _write(tmp_path, ck, "new", on_step=boom)
    assert chk.read_checkpoint(str(ck))[0] is None


def test_crash_after_the_pointer_switch_has_the_new_checkpoint(tmp_path):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "old")

    def boom(name):
        if name == "pointer":
            raise Crash

    with pytest.raises(Crash):
        _write(tmp_path, ck, "new", on_step=boom)
    assert chk.read_checkpoint(str(ck), "P1")[0]["meta"]["tag"] == "new"


@pytest.mark.parametrize("damage", ["db", "before", "manifest_pinned", "manifest_json", "pointer_garbage",
                                    "pointer_traversal", "pointer_missing_dir", "truncate_db", "drop_file"])
def test_torn_or_tampered_checkpoint_is_refused(tmp_path, damage):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "a")
    vdir = ck / (ck / "CURRENT").read_text()
    if damage == "db":
        (vdir / "rag.duckdb").write_bytes(b"other db")
    elif damage == "before":  # new-DB-with-old-before.json style mix
        (vdir / "before.json").write_text('{"tag": "stale"}')
    elif damage == "manifest_pinned":
        m = json.loads((vdir / "manifest.json").read_text())
        m["pinned_sha"] = "P2"
        (vdir / "manifest.json").write_text(json.dumps(m))
    elif damage == "manifest_json":
        (vdir / "manifest.json").write_text("{not json")
    elif damage == "pointer_garbage":
        (ck / "CURRENT").write_text("whatever")
    elif damage == "pointer_traversal":
        (ck / "CURRENT").write_text("../../etc")
    elif damage == "pointer_missing_dir":
        (ck / "CURRENT").write_text("v-20990101T000000Z-deadbeef")
    elif damage == "truncate_db":
        (vdir / "rag.duckdb").write_bytes((vdir / "rag.duckdb").read_bytes()[:-1])
    elif damage == "drop_file":
        (vdir / "before.json").unlink()
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and why != "ok", damage


def test_checkpoint_file_names_are_validated(tmp_path):
    db, files = _src(tmp_path, "a")
    for bad in ("../x", "rag.duckdb", "manifest.json", "CURRENT", "a/b"):
        with pytest.raises(ValueError):
            chk.write_checkpoint(str(tmp_path / "ck"), db, {bad: files["before.json"]}, {}, "P1")


def test_manifest_of_another_version_is_refused_even_with_identical_files(tmp_path):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "a")
    first = ck / (ck / "CURRENT").read_text()
    _write(tmp_path, ck, "a")  # identical content: only the version differs
    second = ck / (ck / "CURRENT").read_text()
    assert first != second
    (second / "manifest.json").write_text((first / "manifest.json").read_text())
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and "does not belong" in why


def test_pointer_cannot_escape_the_checkpoint_dir(tmp_path):
    other, ck = tmp_path / "other", tmp_path / "ck"
    _write(tmp_path, other, "a")
    _write(tmp_path, ck, "b")
    (ck / "CURRENT").write_text("../other/" + (other / "CURRENT").read_text())
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and "valid version name" in why


def test_restore_rechecks_the_restored_db_hash(tmp_path):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, "a")
    got, _ = chk.read_checkpoint(str(ck), "P1")
    with pytest.raises(RuntimeError, match="does not match the checkpoint manifest"):
        chk.restore_checkpoint({**got, "db_sha256": "0" * 64}, str(tmp_path / "db"), {})
