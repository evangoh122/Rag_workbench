"""Checks used by notebooks/colab_backfill.ipynb (no GPU, Colab or network needed to test).

    append_only_proof(original_db, new_db)   row-level proof that nothing original changed
    validate_caps(tickers, quarters, ...)    the HF runner's caps (scripts/run_hf_backfill.sh)
    pending_groups / mark_done / split_complete   completed-set bookkeeping for Colab resume
    write_checkpoint / read_checkpoint / restore_checkpoint   atomic, verified checkpoints

The notebook embeds into a copy of the pinned production DB and stages the result in a
private repo; this module is the guard that the copy only ever gained rows.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import time

import duckdb

from scripts.prepare_db_copy import copy_writable

# Limits copied from scripts/run_hf_backfill.sh (BACKFILL_MAX_TICKERS, BACKFILL_QUARTERS,
# BACKFILL_TIMEOUT_SECONDS). tests/test_colab_notebook.py checks they have not drifted.
MAX_TICKERS_LIMIT = (1, 50)
QUARTERS_LIMIT = (1, 8)
DEADLINE_LIMIT = (60, 21600)
DEFAULT_GROUP_SIZE = 10  # the runner's default BACKFILL_MAX_TICKERS
TICKER_RE = re.compile(r"^[A-Za-z0-9.-]{1,10}$")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _base_tables(con, catalog: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name", [catalog]).fetchall()]


def _columns(con, catalog: str, table: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        "ORDER BY ordinal_position", [catalog, table]).fetchall()]


def _column_types(con, catalog: str, table: str) -> dict[str, str]:
    return dict(con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ?", [catalog, table]).fetchall())


def _views(con, catalog: str) -> dict[tuple[str, str], str]:
    return {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT schema_name, view_name, sql FROM duckdb_views() WHERE database_name = ? AND NOT internal",
        [catalog]).fetchall()}


def append_only_proof(original_db: str, new_db: str) -> dict:
    """Prove new_db is original_db plus appended rows. Raise RuntimeError otherwise.

    Per table in the original: it still exists, keeps every original column with the same type
    (INTEGER -> BIGINT fails), has at least as many rows, and every original row (all original
    columns, as a multiset) is present with identical values (EXCEPT ALL). Every original view
    must still exist with the same definition. Added tables, columns, views and rows, and column
    or row order, are tolerated. Both files are opened read-only. Returns per-table counts.
    """
    for path in (original_db, new_db):
        if not os.path.isfile(path):
            raise RuntimeError(f"append-only proof: missing file {path}")
    if os.path.realpath(original_db) == os.path.realpath(new_db):
        raise RuntimeError("append-only proof: original and new DB are the same file")
    con = duckdb.connect()
    problems: list[str] = []
    report: dict = {}
    try:
        con.execute(f"ATTACH '{original_db.replace(chr(39), chr(39) * 2)}' AS orig (READ_ONLY)")
        con.execute(f"ATTACH '{new_db.replace(chr(39), chr(39) * 2)}' AS new (READ_ONLY)")
        orig_tables = _base_tables(con, "orig")
        if not orig_tables:
            raise RuntimeError("append-only proof: original DB has no tables")
        new_tables = set(_base_tables(con, "new"))
        for t in orig_tables:
            if t not in new_tables:
                problems.append(f"{t}: table missing after")
                continue
            ocols = _columns(con, "orig", t)
            otypes, ntypes = _column_types(con, "orig", t), _column_types(con, "new", t)
            missing = [c for c in ocols if c not in ntypes]
            if missing:
                problems.append(f"{t}: columns dropped {missing}")
                continue
            retyped = [f"{c} {otypes[c]} -> {ntypes[c]}" for c in ocols if otypes[c] != ntypes[c]]
            if retyped:
                problems.append(f"{t}: column types changed {retyped}")
                continue
            cols = ", ".join(_ident(c) for c in ocols)
            n_before = con.execute(f"SELECT count(*) FROM orig.main.{_ident(t)}").fetchone()[0]
            n_after = con.execute(f"SELECT count(*) FROM new.main.{_ident(t)}").fetchone()[0]
            lost = con.execute(
                f"SELECT count(*) FROM (SELECT {cols} FROM orig.main.{_ident(t)} "
                f"EXCEPT ALL SELECT {cols} FROM new.main.{_ident(t)})").fetchone()[0]
            if n_after < n_before:
                problems.append(f"{t}: rows shrank {n_before} -> {n_after}")
            if lost:
                problems.append(f"{t}: {lost} original row(s) missing or modified")
            report[t] = {"before": n_before, "after": n_after, "added": n_after - n_before}
        new_views = _views(con, "new")
        for (schema, name), sql in _views(con, "orig").items():
            if (schema, name) not in new_views:
                problems.append(f"view {schema}.{name}: missing after")
            elif new_views[(schema, name)] != sql:
                problems.append(f"view {schema}.{name}: definition changed")
    finally:
        con.close()
    if problems:
        raise RuntimeError("APPEND-ONLY PROOF FAILED: " + "; ".join(problems))
    return report


def validate_caps(tickers, quarters, group_size, deadline_seconds) -> None:
    """Raise ValueError unless the run stays inside the HF runner's caps."""
    tickers = list(tickers)
    if not tickers:
        raise ValueError("no tickers selected")
    lo, hi = MAX_TICKERS_LIMIT
    if not lo <= len(tickers) <= hi:
        raise ValueError(f"{len(tickers)} tickers outside the runner cap {lo}..{hi}")
    bad = [t for t in tickers if not TICKER_RE.match(t)]
    if bad:
        raise ValueError(f"invalid ticker(s): {bad}")
    if len(set(tickers)) != len(tickers):
        raise ValueError("duplicate tickers")
    if not isinstance(quarters, int) or isinstance(quarters, bool) or not QUARTERS_LIMIT[0] <= quarters <= QUARTERS_LIMIT[1]:
        raise ValueError(f"quarters must be an integer in {QUARTERS_LIMIT[0]}..{QUARTERS_LIMIT[1]}")
    if not isinstance(group_size, int) or isinstance(group_size, bool) or not 1 <= group_size <= DEFAULT_GROUP_SIZE:
        raise ValueError(f"group size must be an integer in 1..{DEFAULT_GROUP_SIZE}")
    if (not isinstance(deadline_seconds, int) or isinstance(deadline_seconds, bool)
            or not DEADLINE_LIMIT[0] <= deadline_seconds <= DEADLINE_LIMIT[1]):
        raise ValueError(f"deadline must be an integer in {DEADLINE_LIMIT[0]}..{DEADLINE_LIMIT[1]} seconds")


def pending_groups(forms_plan, tickers, completed, group_size):
    """Yield (form, group) for tickers whose '<form>:<ticker>' key is not in `completed`."""
    done = set(completed)
    for form in forms_plan:
        todo = [t for t in tickers if f"{form}:{t}" not in done]
        for i in range(0, len(todo), group_size):
            yield form, todo[i:i + group_size]


def mark_done(meta: dict, form: str, group) -> dict:
    """Return meta with '<form>:<ticker>' added to its sorted, de-duplicated completed list."""
    keys = set(meta.get("completed", [])) | {f"{form}:{t}" for t in group}
    return {**meta, "completed": sorted(keys)}




def split_complete(group, missing):
    """Split `group` into (complete, incomplete) tickers given the dry-run's still-missing filings.

    `missing` holds (ticker, form, accession) triples from a dry run AFTER the embed call. embed_additional.py
    skips a filing whose embedding failed and still exits 0, so exit status proves nothing: a ticker is
    complete only when none of its expected accessions is still missing from the DB.
    """
    short = {str(m[0]).upper() for m in missing}
    return ([t for t in group if t.upper() not in short], [t for t in group if t.upper() in short])


# ── atomic, verified checkpoints ────────────────────────────────────────────
# Layout:  <dir>/CURRENT            names the live version (switched with os.replace)
#          <dir>/v-<utc>-<rand>/    rag.duckdb + extra files + manifest.json (sha256 of each, pinned revision)
# A version directory is invisible until CURRENT points at it, so a disconnect at any step leaves either
# the previous complete checkpoint or the new complete one, never a mix.

DB_NAME = "rag.duckdb"
CURRENT = "CURRENT"
MANIFEST = "manifest.json"
VERSION_RE = re.compile(r"^v-\d{8}T\d{6}Z-[0-9a-f]{8}$")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
LOCK_NAME = ".lock"
LOCK_TIMEOUT_SECONDS = 120


def _fsync_file(path: str) -> None:
    with open(path, "rb") as f:
        os.fsync(f.fileno())


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:  # some network/FUSE mounts cannot fsync a directory
        pass


@contextlib.contextmanager
def _writer_lock(ckpt_dir: str, timeout: float = LOCK_TIMEOUT_SECONDS):
    """Exclusive advisory lock so concurrent writers run one at a time (the last one wins)."""
    fd = os.open(os.path.join(ckpt_dir, LOCK_NAME), os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"another process has held the checkpoint lock in {ckpt_dir} for {timeout}s; "
                        "is a second notebook session writing to the same folder?") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the flock


def write_checkpoint(ckpt_dir: str, db_path: str, files: dict, meta: dict, pinned_sha: str, on_step=None) -> dict:
    """Write a new checkpoint version and atomically make it current. Returns its manifest.

    `files` maps a plain file name to the source path. `on_step(name)` is called after each durable step
    ('db', 'files', 'manifest', 'pointer_tmp', 'pointer'); tests raise from it to simulate a disconnect.
    Writers are serialised by an exclusive lock held for the whole write, and each uses its own temp
    pointer, so a returned manifest always names the version CURRENT pointed at when this call finished.
    """
    step = on_step or (lambda name: None)
    for name in files:
        if not _safe_name(name) or name in (DB_NAME, MANIFEST, CURRENT, LOCK_NAME):
            raise ValueError(f"invalid checkpoint file name {name!r}")
    os.makedirs(ckpt_dir, exist_ok=True)
    with _writer_lock(ckpt_dir):
        return _write_locked(ckpt_dir, db_path, files, meta, pinned_sha, step)


def _write_locked(ckpt_dir, db_path, files, meta, pinned_sha, step) -> dict:
    version = f"v-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}"
    vdir = os.path.join(ckpt_dir, version)
    os.mkdir(vdir)
    hashes = {}
    dst = os.path.join(vdir, DB_NAME)
    shutil.copyfile(db_path, dst)
    _fsync_file(dst)
    hashes[DB_NAME] = sha256_file(dst)  # hash the copy: it is what a resume will read
    step("db")
    for name, src in files.items():
        dst = os.path.join(vdir, name)
        shutil.copyfile(src, dst)
        _fsync_file(dst)
        hashes[name] = sha256_file(dst)
    step("files")
    manifest = {"version": version, "pinned_sha": pinned_sha, "db_sha256": hashes[DB_NAME],
                "files": hashes, "meta": meta}
    with open(os.path.join(vdir, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
        f.flush()
        os.fsync(f.fileno())
    _fsync_dir(vdir)
    step("manifest")
    tmp = os.path.join(ckpt_dir, f"{CURRENT}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(version)
            f.flush()
            os.fsync(f.fileno())
        step("pointer_tmp")
        os.replace(tmp, os.path.join(ckpt_dir, CURRENT))
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)  # our own temp pointer only
        raise
    _fsync_dir(ckpt_dir)
    step("pointer")
    _prune(ckpt_dir, version)
    return manifest


def _prune(ckpt_dir: str, current: str) -> None:
    """Keep the current version and the newest other one; drop older and orphaned version dirs."""
    others = sorted((d for d in os.listdir(ckpt_dir) if VERSION_RE.match(d) and d != current), reverse=True)
    for d in others[1:]:
        path = os.path.join(ckpt_dir, d)
        if not os.path.islink(path):  # never follow a planted link out of the tree
            shutil.rmtree(path, ignore_errors=True)


def _safe_name(name) -> bool:
    """A plain file name: no separators, no '.'/'..', not absolute, no NUL."""
    return (isinstance(name, str) and name not in ("", ".", "..") and "/" not in name and "\\" not in name
            and "\0" not in name and not os.path.isabs(name) and os.path.basename(name) == name)


def _is_plain(path: str, want=stat.S_ISREG) -> bool:
    """True when `path` itself (not what it points to) is a regular file / directory, not a symlink."""
    try:
        return want(os.lstat(path).st_mode)
    except OSError:
        return False


def _inside(parent: str, path: str) -> bool:
    """True when the fully resolved `path` is directly under the fully resolved `parent`."""
    rp, rd = os.path.realpath(path), os.path.realpath(parent)
    try:
        return os.path.commonpath([rp, rd]) == rd and os.path.dirname(rp) == rd
    except ValueError:
        return False


def _read_nofollow(path: str) -> bytes:
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        return f.read()


def _sha256_nofollow(path: str) -> str:
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _member_problem(vdir: str, name: str) -> str | None:
    if not _safe_name(name):
        return f"manifest names an invalid file {name!r}"
    path = os.path.join(vdir, name)
    if not _is_plain(path):
        return f"{name} is missing or is not a regular file (symlinks are refused)"
    if not _inside(vdir, path):
        return f"{name} resolves outside the checkpoint"
    return None


def read_checkpoint(ckpt_dir: str, pinned_sha: str | None = None) -> tuple[dict | None, str]:
    """Return (checkpoint, 'ok') for a verified current checkpoint, else (None, reason).

    Verified means: CURRENT is a regular file naming a well-formed version directory (a real directory
    inside `ckpt_dir`) whose manifest agrees with it, matches `pinned_sha` (when given), and every listed
    file is a plain regular file inside that directory whose sha256 equals the manifest's. Symlinks
    anywhere in that chain, path-like file names, torn writes, edits and other revisions are refused.
    """
    root = os.path.realpath(ckpt_dir)  # the folder the caller chose may itself sit behind a link
    cur = os.path.join(root, CURRENT)
    if not os.path.lexists(cur):
        return None, "no checkpoint"
    if not _is_plain(cur):
        return None, "CURRENT is not a regular file (symlinks are refused)"
    try:
        version = _read_nofollow(cur).decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"CURRENT unreadable: {exc}"
    if not VERSION_RE.match(version):
        return None, f"CURRENT is not a valid version name: {version[:40]!r}"
    vdir = os.path.join(root, version)
    if not _is_plain(vdir, stat.S_ISDIR):
        return None, "version directory is missing or is not a real directory (symlinks are refused)"
    mpath = os.path.join(vdir, MANIFEST)
    if not _is_plain(mpath):
        return None, "manifest unreadable: missing or not a regular file"
    try:
        manifest = json.loads(_read_nofollow(mpath).decode("utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"manifest unreadable: {exc}"
    if not isinstance(manifest, dict) or manifest.get("version") != version:
        return None, "manifest does not belong to the current version"
    if pinned_sha is not None and manifest.get("pinned_sha") != pinned_sha:
        return None, f"checkpoint is for revision {manifest.get('pinned_sha')}, not {pinned_sha}"
    hashes = manifest.get("files")
    if not isinstance(hashes, dict) or DB_NAME not in hashes or manifest.get("db_sha256") != hashes[DB_NAME]:
        return None, "manifest has no consistent database hash"
    paths = {}
    for name, want in hashes.items():
        problem = _member_problem(vdir, name)
        if problem:
            return None, problem
        path = os.path.join(vdir, name)
        try:
            ok = _sha256_nofollow(path) == want
        except OSError:
            ok = False
        if not ok:
            return None, f"{name} is missing or does not match its manifest hash"
        paths[name] = path
    db = paths.pop(DB_NAME)
    return {"dir": vdir, "db": db, "files": paths, "meta": manifest.get("meta", {}),
            "pinned_sha": manifest.get("pinned_sha"), "db_sha256": manifest["db_sha256"],
            "hashes": {k: v for k, v in hashes.items() if k != DB_NAME}}, "ok"


def restore_checkpoint(ckpt: dict, db_dest: str, file_dests: dict) -> None:
    """Copy a verified checkpoint to the working paths and re-check every restored file's hash.

    Sources are re-checked here (plain files directly inside the checkpoint's version directory), so a
    hand-made or stale `ckpt` dict cannot make this copy something from outside the tree.
    """
    vdir = ckpt["dir"]
    if not _is_plain(vdir, stat.S_ISDIR):
        raise RuntimeError("checkpoint directory is not a real directory")
    sources = {DB_NAME: ckpt["db"], **ckpt["files"]}
    for name, path in sources.items():
        problem = _member_problem(vdir, name)
        if problem or os.path.realpath(path) != os.path.join(os.path.realpath(vdir), name):
            raise RuntimeError(problem or f"{name} is not inside the checkpoint directory")
    copy_writable(ckpt["db"], db_dest)
    if sha256_file(db_dest) != ckpt["db_sha256"]:
        raise RuntimeError("restored database does not match the checkpoint manifest")
    for name, dest in file_dests.items():
        if name not in ckpt["files"]:
            raise RuntimeError(f"checkpoint has no {name}")
        shutil.copyfile(ckpt["files"][name], dest)
        want = ckpt.get("hashes", {}).get(name)
        if want is not None and sha256_file(dest) != want:
            raise RuntimeError(f"restored {name} does not match the checkpoint manifest")
