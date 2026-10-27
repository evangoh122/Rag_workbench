"""Tests for scripts/colab_backfill_checks.py: append-only proof, runner caps, resume bookkeeping."""
import json
import os
import re
import threading
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


# ── concurrent writers ──────────────────────────────────────────────────────

def _versions(ck):
    return sorted(d.name for d in ck.iterdir() if d.name.startswith("v-"))


def test_two_synchronised_writers_both_succeed_and_current_is_a_verified_version(tmp_path):
    for round_ in range(8):
        ck = tmp_path / f"ck{round_}"
        srcs = {tag: _src(tmp_path, f"{tag}{round_}") for tag in "ab"}
        barrier = threading.Barrier(2)
        results, errors = {}, []

        def writer(tag):
            db, files = srcs[tag]
            try:
                barrier.wait(timeout=10)
                results[tag] = chk.write_checkpoint(str(ck), db, files, {"tag": tag, "completed": [tag]}, "P1")
            except BaseException as exc:  # noqa: BLE001
                errors.append((tag, repr(exc)))

        threads = [threading.Thread(target=writer, args=(t,)) for t in "ab"]
        [t.start() for t in threads]
        [t.join(timeout=60) for t in threads]
        assert not errors, errors
        got, why = chk.read_checkpoint(str(ck), "P1")
        assert why == "ok"
        current = (ck / "CURRENT").read_text()
        # a returned success means that writer's own, fully verified version existed; CURRENT is one of them
        assert current in {m["version"] for m in results.values()}
        assert got["meta"]["tag"] in {"a", "b"} and (ck / current / "manifest.json").is_file()
        assert not [d for d in ck.iterdir() if d.name.endswith(".tmp")]


def test_writers_are_serialised_by_an_exclusive_lock(tmp_path):
    ck = tmp_path / "ck"
    first_in, release = threading.Event(), threading.Event()
    second_done = threading.Event()
    (da, fa), (db_, fb) = _src(tmp_path, "a"), _src(tmp_path, "b")

    def hold(name):
        if name == "db":
            first_in.set()
            release.wait(timeout=20)

    def first():
        chk.write_checkpoint(str(ck), da, fa, {"tag": "a", "completed": []}, "P1", hold)

    def second():
        chk.write_checkpoint(str(ck), db_, fb, {"tag": "b", "completed": []}, "P1")
        second_done.set()

    t1 = threading.Thread(target=first)
    t1.start()
    assert first_in.wait(timeout=10)
    t2 = threading.Thread(target=second)
    t2.start()
    assert not second_done.wait(timeout=0.5), "second writer ran while the first still held the lock"
    assert len(_versions(ck)) == 1  # it has not even created its version directory
    release.set()
    t1.join(timeout=20)
    t2.join(timeout=20)
    assert second_done.is_set()
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert why == "ok" and got["meta"]["tag"] == "b"  # the last writer wins


def test_lock_timeout_gives_a_clear_error(tmp_path):
    import fcntl
    ck = tmp_path / "ck"
    ck.mkdir()
    fd = os.open(ck / ".lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    outcome = []

    def contender():
        try:
            with chk._writer_lock(str(ck), timeout=0.2):
                outcome.append("acquired")
        except RuntimeError as exc:
            outcome.append(str(exc))

    t = threading.Thread(target=contender, daemon=True)  # daemon + bounded join: a broken timeout fails, not hangs
    t.start()
    t.join(timeout=5)
    try:
        assert outcome and "checkpoint lock" in outcome[0], outcome or "timed out waiting for the timeout"
        assert _versions(ck) == []
    finally:
        os.close(fd)  # releases the lock so a leaked contender can finish
        t.join(timeout=5)


def test_temp_pointer_is_writer_unique_and_only_own_temp_is_cleaned(tmp_path):
    ck = tmp_path / "ck"
    ck.mkdir()
    foreign = ck / "CURRENT.999.abcd1234.tmp"
    foreign.write_text("someone else")
    seen = []

    def boom(name):
        if name == "pointer_tmp":
            seen.extend(sorted(d.name for d in ck.iterdir() if d.name.startswith("CURRENT.")))
            raise Crash

    with pytest.raises(Crash):
        _write(tmp_path, ck, "a", on_step=boom)
    own = [n for n in seen if n != foreign.name]
    assert len(own) == 1 and re.fullmatch(rf"CURRENT\.{os.getpid()}\.[0-9a-f]{{8}}\.tmp", own[0])
    assert foreign.read_text() == "someone else"  # not ours: untouched
    assert sorted(d.name for d in ck.iterdir() if d.name.startswith("CURRENT.")) == [foreign.name]
    assert chk.read_checkpoint(str(ck))[0] is None


# ── symlinks and path traversal ─────────────────────────────────────────────

def _checkpoint(tmp_path, tag="a"):
    ck = tmp_path / "ck"
    _write(tmp_path, ck, tag)
    return ck, ck / (ck / "CURRENT").read_text()


def _outside_copy(tmp_path, src):
    dst = tmp_path / "outside" / src.name
    dst.parent.mkdir(exist_ok=True)
    dst.write_bytes(src.read_bytes())  # identical bytes: hashes still match, only the link is wrong
    return dst


def _swap_for_link(path, target):
    path.unlink()
    path.symlink_to(target)


@pytest.mark.parametrize("member", ["rag.duckdb", "before.json", "manifest.json"])
def test_symlinked_member_is_refused_even_when_its_bytes_match(tmp_path, member):
    ck, vdir = _checkpoint(tmp_path)
    outside = _outside_copy(tmp_path, vdir / member)
    _swap_for_link(vdir / member, outside)
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and ("symlink" in why or "not a regular file" in why), why


def test_symlinked_current_is_refused(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    outside = _outside_copy(tmp_path, ck / "CURRENT")
    _swap_for_link(ck / "CURRENT", outside)
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and "CURRENT is not a regular file" in why
    # also a link to a perfectly valid CURRENT inside the tree
    _swap_for_link(ck / "CURRENT", vdir.parent / "CURRENT.real")  # dangling target is refused too
    assert chk.read_checkpoint(str(ck), "P1")[0] is None


def test_symlinked_version_directory_is_refused(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    moved = tmp_path / "elsewhere" / vdir.name
    moved.parent.mkdir()
    vdir.rename(moved)
    vdir.symlink_to(moved)  # the whole version directory (parent of every file) is a link
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and "not a real directory" in why


def test_symlinked_checkpoint_root_itself_is_allowed(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(ck)  # the folder the user chose may sit behind a link (e.g. a mounted drive)
    assert chk.read_checkpoint(str(link), "P1")[1] == "ok"


@pytest.mark.parametrize("name", ["../evil.json", "../../evil.json", "/tmp/evil.json", "a/b", "..", ".", "",
                                  "sub\\evil", "x\0y"])
def test_manifest_file_names_with_separators_or_traversal_are_refused(tmp_path, name):
    ck, vdir = _checkpoint(tmp_path)
    (ck / "evil.json").write_text("{}")  # a file the name would reach if it were followed
    m = json.loads((vdir / "manifest.json").read_text())
    m["files"][name] = chk.sha256_file(str(ck / "evil.json"))
    (vdir / "manifest.json").write_text(json.dumps(m))
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and why != "ok"


def test_absolute_name_pointing_at_a_real_file_is_refused(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    evil = tmp_path / "evil.json"
    evil.write_text("{}")
    m = json.loads((vdir / "manifest.json").read_text())
    m["files"][str(evil)] = chk.sha256_file(str(evil))
    (vdir / "manifest.json").write_text(json.dumps(m))
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert got is None and "invalid file" in why


def test_restore_refuses_a_symlinked_or_foreign_source(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    got, _ = chk.read_checkpoint(str(ck), "P1")
    outside = _outside_copy(tmp_path, vdir / "rag.duckdb")
    _swap_for_link(vdir / "rag.duckdb", outside)  # swapped after the read, before the restore
    with pytest.raises(RuntimeError, match="symlink|regular file"):
        chk.restore_checkpoint(got, str(tmp_path / "db"), {})
    assert not (tmp_path / "db").exists()
    ck2 = tmp_path / "ck2"
    _write(tmp_path, ck2, "z")
    got2, _ = chk.read_checkpoint(str(ck2), "P1")
    foreign = {**got2, "files": {"before.json": str(tmp_path / "outside" / "rag.duckdb")}}
    with pytest.raises(RuntimeError, match="not inside|regular file"):
        chk.restore_checkpoint(foreign, str(tmp_path / "db2"), {"before.json": str(tmp_path / "b")})


def test_restore_rechecks_restored_snapshot_hashes(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    got, _ = chk.read_checkpoint(str(ck), "P1")
    chk.restore_checkpoint(got, str(tmp_path / "db"), {"before.json": str(tmp_path / "b.json")})
    bad = {**got, "hashes": {"before.json": "0" * 64}}
    with pytest.raises(RuntimeError, match="restored before.json does not match"):
        chk.restore_checkpoint(bad, str(tmp_path / "db"), {"before.json": str(tmp_path / "b.json")})


def test_prune_does_not_follow_a_planted_version_link(tmp_path):
    ck = tmp_path / "ck"
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")
    ck.mkdir()
    for ts in ("20200101T000000Z", "20200102T000000Z", "20200103T000000Z"):
        (ck / f"v-{ts}-deadbeef").symlink_to(victim)
    _write(tmp_path, ck, "a")
    assert (victim / "keep.txt").read_text() == "keep"


# ── version-directory TOCTOU (swap a directory for a symlink between check and open) ──

def _attacker_dir(tmp_path, vname):
    """An outside folder shaped like a valid version directory, with attacker metadata and matching hashes."""
    evil = tmp_path / "outside" / vname
    evil.mkdir(parents=True)
    (evil / "rag.duckdb").write_bytes(b"ATTACKER-DB")
    (evil / "before.json").write_text('{"tag": "attacker"}')
    manifest = {"version": vname, "pinned_sha": "P1", "db_sha256": chk.sha256_file(str(evil / "rag.duckdb")),
                "files": {"rag.duckdb": chk.sha256_file(str(evil / "rag.duckdb")),
                          "before.json": chk.sha256_file(str(evil / "before.json"))},
                "meta": {"tag": "attacker", "completed": ["attacker"]}}
    (evil / "manifest.json").write_text(json.dumps(manifest))
    return evil


def _swapper(ck, vdir, evil):
    """A hook that, at the chosen step, makes a barrier-synchronised thread swap vdir for a symlink to evil."""
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def swap():
        try:
            barrier.wait()
            vdir.rename(vdir.with_name(vdir.name + ".moved"))
            vdir.symlink_to(evil)
            barrier.wait()
        except BaseException as exc:  # noqa: BLE001
            errors.append(repr(exc))

    def hook_at(point):
        thread = threading.Thread(target=swap, daemon=True)
        state = {"thread": thread, "started": False}

        def hook(name):
            if name == point:
                state["started"] = True
                thread.start()
                barrier.wait()   # the swapper now swaps while we are paused at this exact point
                barrier.wait()
        return hook, state

    return hook_at, errors


@pytest.mark.parametrize("point", ["root", "version", "manifest"])
def test_read_checkpoint_never_returns_data_from_a_swapped_in_symlink(tmp_path, point):
    ck, vdir = _checkpoint(tmp_path)
    evil = _attacker_dir(tmp_path, vdir.name)
    hook_at, errors = _swapper(ck, vdir, evil)
    hook, state = hook_at(point)
    got, why = chk.read_checkpoint(str(ck), "P1", on_step=hook)
    state["thread"].join(timeout=10)
    assert state["started"] and not errors, errors
    assert vdir.is_symlink()  # the swap really happened while we were mid-read
    if got is None:
        assert point == "root" and "symlinks are refused" in why, (point, why)  # before the directory was opened
    else:
        # the directory was already open: everything came from the ORIGINAL directory's descriptor
        assert point != "root" and got["meta"]["tag"] == "a", got["meta"]
        assert got["meta"]["tag"] != "attacker" and got["db_sha256"] != chk.sha256_file(str(evil / "rag.duckdb"))


@pytest.mark.parametrize("point", ["root", "version"])
def test_restore_checkpoint_never_copies_through_a_swapped_in_symlink(tmp_path, point):
    ck, vdir = _checkpoint(tmp_path)
    got, why = chk.read_checkpoint(str(ck), "P1")
    assert why == "ok"
    evil = _attacker_dir(tmp_path, vdir.name)
    hook_at, errors = _swapper(ck, vdir, evil)
    hook, state = hook_at(point)
    db, snap = tmp_path / "work.duckdb", tmp_path / "work-before.json"
    if point == "root":
        with pytest.raises(RuntimeError, match="symlinks are refused"):
            chk.restore_checkpoint(got, str(db), {"before.json": str(snap)}, on_step=hook)
        assert not db.exists() and not snap.exists()
    else:
        chk.restore_checkpoint(got, str(db), {"before.json": str(snap)}, on_step=hook)
        assert db.read_bytes() == b"db-a" * 100 and json.loads(snap.read_text()) == {"tag": "a"}
    state["thread"].join(timeout=10)
    assert state["started"] and not errors, errors
    assert b"ATTACKER" not in (db.read_bytes() if db.exists() else b"")
    assert not [p for p in tmp_path.iterdir() if ".tmp." in p.name]  # no partial copies left behind


def test_restore_verifies_the_bytes_it_copied_not_an_earlier_read(tmp_path):
    ck, vdir = _checkpoint(tmp_path)
    got, _ = chk.read_checkpoint(str(ck), "P1")
    (vdir / "rag.duckdb").write_bytes(b"changed after the verified read")  # same file, new bytes
    db = tmp_path / "work.duckdb"
    db.write_bytes(b"existing working copy")
    with pytest.raises(RuntimeError, match="restored database does not match"):
        chk.restore_checkpoint(got, str(db), {})
    assert db.read_bytes() == b"existing working copy"  # a bad copy never replaces the destination
    assert not [p for p in tmp_path.iterdir() if ".tmp." in p.name]


def test_fd_support_is_required(monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW")
    with pytest.raises(RuntimeError, match="need Linux"):
        chk.read_checkpoint("/nonexistent")


# ── DuckDB compaction (real DuckDB, many append+checkpoint cycles) ──────────

def _fragmented(path, cycles=25, rows=200):
    """Many append+CHECKPOINT cycles, then a delete: leaves free blocks in the file."""
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE edgar_embeddings (id INTEGER PRIMARY KEY, ticker VARCHAR, text VARCHAR, "
                "embedding FLOAT[])")
    con.execute("CREATE INDEX ix_ticker ON edgar_embeddings(ticker)")
    con.execute("CREATE TABLE polygon_tickers (ticker VARCHAR PRIMARY KEY, name VARCHAR)")
    con.execute("INSERT INTO polygon_tickers VALUES ('AAPL', 'Apple')")
    con.execute("CREATE VIEW v_tickers AS SELECT DISTINCT ticker FROM edgar_embeddings")
    con.close()
    for i in range(cycles):
        con = duckdb.connect(str(path))
        con.execute("INSERT INTO edgar_embeddings SELECT ?*100000 + range, 'T' || (range % 7), repeat('x', 300), "
                    "list_transform(range(32), x -> (random())::FLOAT) FROM range(?)", [i, rows])
        con.execute("CHECKPOINT")
        con.close()
    con = duckdb.connect(str(path))
    con.execute("DELETE FROM edgar_embeddings WHERE id % 3 = 0")
    con.execute("CHECKPOINT")
    con.close()


@pytest.fixture
def frag(tmp_path):
    src = tmp_path / "staged.duckdb"
    _fragmented(src)
    return src


def _snapshot(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute("SELECT id, ticker, embedding FROM edgar_embeddings ORDER BY id").fetchall()
    finally:
        con.close()


def test_compaction_shrinks_file_and_content_is_identical(frag, tmp_path):
    before_bytes, before_rows = frag.stat().st_size, _snapshot(frag)
    res = chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "work"))
    assert res["free_blocks_before"] > 0 and res["free_blocks_after"] < res["free_blocks_before"]
    assert res["bytes_before"] == before_bytes and res["bytes_after"] == frag.stat().st_size < before_bytes
    assert res["sha256_after"] == chk.sha256_file(str(frag))
    assert _snapshot(frag) == before_rows
    assert res["tables"]["edgar_embeddings"]["rows"] == len(before_rows)
    assert not Path(str(frag) + ".wal").exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["staged.duckdb"]  # no temp left behind
    assert list((tmp_path / "work").iterdir()) == []  # export dir cleaned up
    con = duckdb.connect(str(frag), read_only=True)
    assert con.execute("SELECT count(*) FROM duckdb_indexes() WHERE index_name = 'ix_ticker'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM v_tickers").fetchone()[0] == 7
    con.close()


def test_compaction_to_a_separate_dst_leaves_src_untouched(frag, tmp_path):
    sha = chk.sha256_file(str(frag))
    dst = tmp_path / "out" / "compact.duckdb"
    chk.compact_duckdb(str(frag), str(dst), str(tmp_path / "work"))
    assert chk.sha256_file(str(frag)) == sha and dst.exists()
    assert _snapshot(dst) == _snapshot(frag)


def test_injected_diff_raises_and_leaves_src_untouched(frag, tmp_path, monkeypatch):
    real_import_proof = chk.compact_identity_proof
    before_sha = chk.sha256_file(str(frag))
    tamper_sql = [""]

    def tampered(src, dst):  # the fresh file is altered after IMPORT, before the proof
        con = duckdb.connect(dst)
        con.execute(tamper_sql[0])
        con.execute("CHECKPOINT")
        con.close()
        return real_import_proof(src, dst)

    monkeypatch.setattr(chk, "compact_identity_proof", tampered)
    for sql in ("DELETE FROM edgar_embeddings WHERE id = (SELECT min(id) FROM edgar_embeddings)",
                "UPDATE edgar_embeddings SET embedding = [9.0::FLOAT] WHERE id = (SELECT min(id) FROM edgar_embeddings)",
                "INSERT INTO edgar_embeddings VALUES (-1, 'ZZZ', 'extra', [1.0::FLOAT])"):
        tamper_sql[0] = sql
        with pytest.raises(RuntimeError, match="COMPACTION PROOF FAILED"):
            chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "work"))
        assert chk.sha256_file(str(frag)) == before_sha  # src untouched
        assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["staged.duckdb"]



def test_proof_detects_each_kind_of_difference(frag, tmp_path):
    def copy_with(sql, name):
        out = tmp_path / name
        chk.compact_duckdb(str(frag), str(out), str(tmp_path / "w"))
        con = duckdb.connect(str(out))
        con.execute(sql)
        con.execute("CHECKPOINT")
        con.close()
        return out
    ok = copy_with("SELECT 1", "ok.duckdb")
    assert chk.compact_identity_proof(str(frag), str(ok))["edgar_embeddings"]["rows"] > 0
    for name, sql, msg in [
        ("drop.duckdb", "DELETE FROM edgar_embeddings WHERE id = (SELECT max(id) FROM edgar_embeddings)", "row count"),
        ("vec.duckdb", "UPDATE edgar_embeddings SET embedding = list_transform(embedding, x -> x + 0.5::FLOAT) "
                       "WHERE id = (SELECT max(id) FROM edgar_embeddings)", "changed in the compacted"),
        ("idx.duckdb", "DROP INDEX ix_ticker", "indexes"),
        ("col.duckdb", "ALTER TABLE polygon_tickers ADD COLUMN extra INTEGER", "columns"),
        ("tbl.duckdb", "CREATE TABLE brand_new (x INTEGER)", "tables"),
    ]:
        with pytest.raises(RuntimeError, match=msg):
            chk.compact_identity_proof(str(frag), str(copy_with(sql, name)))
    with pytest.raises(RuntimeError, match="same file"):
        chk.compact_identity_proof(str(frag), str(frag))


def test_disk_precheck_refuses_before_touching_anything(frag, tmp_path, monkeypatch):
    sha = chk.sha256_file(str(frag))
    monkeypatch.setattr(chk, "_free_bytes", lambda path: frag.stat().st_size * 2 - 1)
    with pytest.raises(RuntimeError, match="not enough disk space"):
        chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "work"))
    assert chk.sha256_file(str(frag)) == sha
    assert not (tmp_path / "work").exists() or list((tmp_path / "work").iterdir()) == []
    monkeypatch.setattr(chk, "_free_bytes", lambda path: frag.stat().st_size * 2)
    chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "work"))  # exactly 2x is enough


def test_protected_original_is_never_source_or_destination(frag, tmp_path):
    sha = chk.sha256_file(str(frag))
    other = tmp_path / "other.duckdb"
    other.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="protected"):
        chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "w"), protect=[str(frag)])
    with pytest.raises(RuntimeError, match="protected"):
        chk.compact_duckdb(str(frag), str(other), str(tmp_path / "w"), protect=[str(other)])
    assert chk.sha256_file(str(frag)) == sha and other.read_bytes() == b"x"


def test_wal_present_or_missing_source_is_refused(frag, tmp_path):
    Path(str(frag) + ".wal").write_bytes(b"w")
    with pytest.raises(RuntimeError, match="wal"):
        chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "w"))
    Path(str(frag) + ".wal").unlink()
    with pytest.raises(RuntimeError, match="missing source"):
        chk.compact_duckdb(str(tmp_path / "nope.duckdb"), str(frag), str(tmp_path / "w"))


def test_wal_left_by_fresh_db_is_refused(frag, tmp_path, monkeypatch):
    sha = chk.sha256_file(str(frag))
    real_connect = duckdb.connect

    class Dirty:  # proxy: on close, leave a .wal behind as a crashed writer would
        def __init__(self, con, path):
            self._con, self._path = con, path

        def __getattr__(self, name):
            return getattr(self._con, name)

        def close(self):
            self._con.close()
            Path(self._path + ".wal").write_bytes(b"w")

    def connect(path=":memory:", *a, **k):
        con = real_connect(path, *a, **k)
        return Dirty(con, str(path)) if ".compact-" in str(path) else con

    monkeypatch.setattr(chk.duckdb, "connect", connect)
    with pytest.raises(RuntimeError, match=r"\.wal"):
        chk.compact_duckdb(str(frag), str(frag), str(tmp_path / "w"))
    assert chk.sha256_file(str(frag)) == sha
