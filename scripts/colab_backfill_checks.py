"""Checks used by notebooks/colab_backfill.ipynb (no GPU, Colab or network needed to test).

    append_only_proof(original_db, new_db)   row-level proof that nothing original changed
    validate_caps(tickers, quarters, ...)    the HF runner's caps (scripts/run_hf_backfill.sh)
    pending_groups / mark_done / split_complete   completed-set bookkeeping for Colab resume
    write_checkpoint / read_checkpoint / restore_checkpoint   atomic, verified checkpoints

The notebook embeds into a copy of the pinned production DB and stages the result in a
private repo; this module is the guard that the copy only ever gained rows.
"""
import array
import contextlib
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import time

import duckdb

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
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            # Some filesystems explicitly report that directory fsync is unsupported.
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    finally:
        os.close(fd)


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


def _require_fd_support() -> None:
    """The descriptor-bound reads need openat-style opens (Linux/Colab); refuse loudly elsewhere."""
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd):
        raise RuntimeError("this platform lacks O_DIRECTORY/O_NOFOLLOW/dir_fd; checkpoints need Linux (Colab)")


class _Refused(Exception):
    """A checkpoint member failed a descriptor-level check; the message is the user-facing reason."""


def _open_dir(parent_fd: int, name: str, what: str) -> int:
    """Open directory `name` inside `parent_fd` without following a symlink; fstat-verify it."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        raise _Refused(f"{what} is missing or is not a real directory (symlinks are refused)") from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise _Refused(f"{what} is not a real directory")
    return fd


def _open_file(dir_fd: int, name: str, what: str) -> int:
    """Open regular file `name` inside `dir_fd` (no symlink at the last component); fstat-verify it."""
    if not _safe_name(name):
        raise _Refused(f"manifest names an invalid file {name!r}")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError as exc:
        raise _Refused(f"{what} is missing or is not a regular file (symlinks are refused)") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise _Refused(f"{what} is missing or is not a regular file (symlinks are refused)")
    return fd


def _read_all(fd: int) -> bytes:
    chunks = []
    while block := os.read(fd, 1 << 20):
        chunks.append(block)
    return b"".join(chunks)


def _sha256_fd(fd: int) -> str:
    h = hashlib.sha256()
    while block := os.read(fd, 1 << 20):
        h.update(block)
    return h.hexdigest()


def read_checkpoint(ckpt_dir: str, pinned_sha: str | None = None, on_step=None) -> tuple[dict | None, str]:
    """Return (checkpoint, 'ok') for a verified current checkpoint, else (None, reason).

    Verified means: CURRENT is a regular file naming a well-formed version directory (a real directory
    directly inside `ckpt_dir`) whose manifest agrees with it, matches `pinned_sha` (when given), and
    every listed file is a plain regular file in that directory whose sha256 equals the manifest's.
    The root is resolved once (a symlinked root such as a mounted drive is fine); from there everything
    is opened relative to directory descriptors with O_NOFOLLOW and hashed from the open descriptor, never
    re-opened by pathname, so swapping a directory for a symlink mid-read cannot redirect it. Symlinks,
    path-like names, torn writes, edits and other revisions are refused. `on_step(name)` ('root',
    'version', 'manifest') lets tests act between steps.
    """
    _require_fd_support()
    step = on_step or (lambda name: None)
    root = os.path.realpath(ckpt_dir)
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None, "no checkpoint"
    fds = [root_fd]
    try:
        try:
            cur_fd = os.open(CURRENT, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        except FileNotFoundError:
            return None, "no checkpoint"
        except OSError:
            return None, "CURRENT is not a regular file (symlinks are refused)"
        fds.append(cur_fd)
        if not stat.S_ISREG(os.fstat(cur_fd).st_mode):
            return None, "CURRENT is not a regular file (symlinks are refused)"
        try:
            version = os.read(cur_fd, 4096).decode("utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"CURRENT unreadable: {exc}"
        if not VERSION_RE.match(version):
            return None, f"CURRENT is not a valid version name: {version[:40]!r}"
        step("root")
        vfd = _open_dir(root_fd, version, "version directory")
        fds.append(vfd)
        step("version")
        mfd = _open_file(vfd, MANIFEST, "manifest")
        fds.append(mfd)
        try:
            manifest = json.loads(_read_all(mfd).decode("utf-8"))
        except (OSError, ValueError) as exc:
            return None, f"manifest unreadable: {exc}"
        step("manifest")
        if not isinstance(manifest, dict) or manifest.get("version") != version:
            return None, "manifest does not belong to the current version"
        if pinned_sha is not None and manifest.get("pinned_sha") != pinned_sha:
            return None, f"checkpoint is for revision {manifest.get('pinned_sha')}, not {pinned_sha}"
        hashes = manifest.get("files")
        if not isinstance(hashes, dict) or DB_NAME not in hashes or manifest.get("db_sha256") != hashes[DB_NAME]:
            return None, "manifest has no consistent database hash"
        paths = {}
        for name, want in hashes.items():
            fd = _open_file(vfd, name, name)
            try:
                if _sha256_fd(fd) != want:
                    return None, f"{name} is missing or does not match its manifest hash"
            finally:
                os.close(fd)
            paths[name] = os.path.join(root, version, name)
        db = paths.pop(DB_NAME)
        return {"dir": os.path.join(root, version), "db": db, "files": paths, "meta": manifest.get("meta", {}),
                "pinned_sha": manifest.get("pinned_sha"), "db_sha256": manifest["db_sha256"],
                "hashes": {k: v for k, v in hashes.items() if k != DB_NAME}}, "ok"
    except _Refused as exc:
        return None, str(exc)
    finally:
        for fd in fds:
            os.close(fd)


def _copy_fd_verified(src_fd: int, dest: str, want: str, label: str, make_writable: bool = False) -> None:
    """Copy the open descriptor to `dest` via a temp sibling; replace dest only if the COPIED bytes hash to `want`."""
    tmp = f"{dest}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    h = hashlib.sha256()
    try:
        with open(tmp, "wb") as out:
            while block := os.read(src_fd, 1 << 20):
                h.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        if h.hexdigest() != want:
            raise RuntimeError(f"restored {label} does not match the checkpoint manifest")
        if make_writable:
            os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IWUSR)
        os.replace(tmp, dest)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def restore_checkpoint(ckpt: dict, db_dest: str, file_dests: dict, on_step=None) -> None:
    """Copy a verified checkpoint to the working paths from descriptors, hashing the bytes copied.

    The version directory is re-opened here relative to its (resolved) parent with O_NOFOLLOW and every
    source is opened via that directory descriptor, so a swap after `read_checkpoint` cannot redirect the
    copy; each destination is only replaced once the copied bytes match the manifest hash.
    """
    _require_fd_support()
    step = on_step or (lambda name: None)
    vdir = ckpt["dir"]
    root, version = os.path.dirname(vdir), os.path.basename(vdir)
    if not VERSION_RE.match(version):
        raise RuntimeError(f"invalid checkpoint version directory {version!r}")
    wanted = {DB_NAME: (db_dest, ckpt["db_sha256"], "database", True)}
    for name, dest in file_dests.items():
        if name not in ckpt["files"] or name not in ckpt.get("hashes", {}):
            raise RuntimeError(f"checkpoint has no {name}")
        wanted[name] = (dest, ckpt["hashes"][name], name, False)
    for name, path in {DB_NAME: ckpt["db"], **ckpt["files"]}.items():
        if not _safe_name(name) or path != os.path.join(vdir, name):
            raise RuntimeError(f"{name} is not inside the checkpoint directory")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise RuntimeError(f"checkpoint root is unreadable: {exc}") from exc
    fds = [root_fd]
    try:
        step("root")
        vfd = _open_dir(root_fd, version, "version directory")
        fds.append(vfd)
        step("version")
        for name, (dest, want, label, writable) in wanted.items():
            fd = _open_file(vfd, name, name)
            try:
                _copy_fd_verified(fd, dest, want, label, writable)
            finally:
                os.close(fd)
    except _Refused as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        for fd in fds:
            os.close(fd)


# ── DuckDB compaction ───────────────────────────────────────────────────────
# The Colab run appends in many checkpointed groups; DuckDB keeps the blocks it freed, so the file ends up
# ~2x its compact size. EXPORT DATABASE -> IMPORT DATABASE into a fresh file rewrites it densely. The result
# replaces the target only after a content-identity proof against the source passes.

def _db_size(path: str) -> dict:
    con = duckdb.connect(path, read_only=True)
    try:
        cur = con.execute("PRAGMA database_size")
        cols = [d[0] for d in cur.description]
        row = dict(zip(cols, cur.fetchone()))
    finally:
        con.close()
    return {"bytes": os.path.getsize(path), "block_size": int(row["block_size"]),
            "total_blocks": int(row["total_blocks"]), "free_blocks": int(row["free_blocks"])}


def _schema_fingerprint(con, catalog: str) -> dict:
    """Everything about the schema that a copy must preserve (tables, columns+types, indexes, constraints, views)."""
    tables = _base_tables(con, catalog)
    cols = {t: [(c, _column_types(con, catalog, t)[c]) for c in _columns(con, catalog, t)] for t in tables}
    indexes = sorted(con.execute(
        "SELECT table_name, index_name, sql FROM duckdb_indexes() WHERE database_name = ?", [catalog]).fetchall())
    constraints = sorted(con.execute(
        "SELECT table_name, constraint_type, constraint_text FROM duckdb_constraints() WHERE database_name = ?",
        [catalog]).fetchall())
    return {"tables": tables, "columns": cols, "indexes": indexes, "constraints": constraints,
            "views": sorted(_views(con, catalog).items())}


_FLOAT_SCALAR_WIDTH = {"FLOAT": 4, "REAL": 4, "DOUBLE": 8}
_FLOAT_ARRAY_RE = re.compile(r"^(FLOAT|REAL|DOUBLE)\[\d*\]$")


def _float_kind(data_type: str):
    """(width in bytes, is_list) for FLOAT/DOUBLE scalars and arrays, else None."""
    kind = data_type.upper().replace(" ", "")
    if kind in _FLOAT_SCALAR_WIDTH:
        return _FLOAT_SCALAR_WIDTH[kind], False
    match = _FLOAT_ARRAY_RE.match(kind)
    if match:
        return _FLOAT_SCALAR_WIDTH[match.group(1)], True
    return None


def _float_bytes(values, width: int) -> bytes:
    """Little-endian IEEE-754 bytes for a list of floats, preserving every bit.

    `array` round-trips the values through the exact C float/double representation, so signed
    zero, subnormals and infinities keep their bits; every NaN canonicalises to the platform
    quiet-NaN pattern (identical-bit NaNs compare equal, a NaN vs a number does not).
    """
    try:
        return array.array("f" if width == 4 else "d", values).tobytes()
    except TypeError:  # a NULL inside the array: encode element-wise with sentinels
        out = bytearray()
        for value in values:
            out += b"\x00" if value is None else b"\x01" + _float_bytes([value], width)
        return bytes(out)


def _float_bits_signature(con, catalog: str, table: str, column: str, width: int, is_list: bool) -> dict:
    """Order-independent, bit-exact digest of one FLOAT/DOUBLE column (scalar or array).

    Whole values (a float, an entire embedding vector, or NULL) are hashed one at a time and
    summed modulo 2**128, so the digest is a multiset fingerprint that distinguishes +0.0 from
    -0.0, subnormals, infinities and NaN where DuckDB's `hash` and `EXCEPT ALL` compare equal.
    Also returns how many non-finite (NaN/Inf) values were seen so callers can flag them.
    """
    cursor = con.execute(f"SELECT {_ident(column)} FROM {catalog}.main.{_ident(table)}")
    count, digest, nonfinite = 0, 0, 0
    while True:
        rows = cursor.fetchmany(4096)
        if not rows:
            break
        for (value,) in rows:
            count += 1
            if value is None:
                payload = b"N"
            else:
                values = value if is_list else [value]
                nonfinite += sum(1 for item in values if item is not None and not math.isfinite(item))
                payload = (b"L" if is_list else b"S") + len(values).to_bytes(8, "little") + _float_bytes(values, width)
            digest = (digest + int.from_bytes(hashlib.blake2b(payload, digest_size=16).digest(), "big")) % (1 << 128)
    return {"count": count, "digest": digest, "nonfinite": nonfinite}


def compact_identity_proof(src_db: str, dst_db: str) -> dict:
    """Prove dst_db holds exactly the same content as src_db. Raise RuntimeError on ANY difference.

    Same tables, columns (order and type), indexes, constraints and views; equal row counts; the row multisets
    are equal in both directions (EXCEPT ALL over every column) and a per-table order-independent hash over
    whole rows agrees. Because DuckDB treats +0.0 == -0.0 and compares NaN as equal, every FLOAT/DOUBLE column
    (scalars and arrays, so embeddings) is additionally compared by a bit-exact multiset digest of its IEEE-754
    bytes. NaN policy: all NaNs canonicalise to the same quiet-NaN bit pattern, so identical-bit NaNs pass;
    a NaN (or Inf) present on only one side, a flipped zero sign, or any subnormal/bit difference is a failure.
    Non-finite values that match on both sides are counted in the report. Both files are opened read-only.
    """
    for path in (src_db, dst_db):
        if not os.path.isfile(path):
            raise RuntimeError(f"compaction proof: missing file {path}")
    if os.path.realpath(src_db) == os.path.realpath(dst_db):
        raise RuntimeError("compaction proof: source and compacted DB are the same file")
    con = duckdb.connect()
    problems: list[str] = []
    report: dict = {}
    try:
        con.execute(f"ATTACH '{src_db.replace(chr(39), chr(39) * 2)}' AS src (READ_ONLY)")
        con.execute(f"ATTACH '{dst_db.replace(chr(39), chr(39) * 2)}' AS dst (READ_ONLY)")
        a, b = _schema_fingerprint(con, "src"), _schema_fingerprint(con, "dst")
        for key in a:
            if a[key] != b[key]:
                problems.append(f"schema differs ({key})")
        if not a["tables"]:
            problems.append("source DB has no tables")
        for t in sorted(set(a["tables"]) & set(b["tables"])):
            if a["columns"][t] != b["columns"][t]:
                continue  # already reported as a schema difference; the row comparison needs equal columns
            q = _ident(t)
            n_src = con.execute(f"SELECT count(*) FROM src.main.{q}").fetchone()[0]
            n_dst = con.execute(f"SELECT count(*) FROM dst.main.{q}").fetchone()[0]
            h_src = con.execute(f"SELECT coalesce(sum(hash(x)::HUGEINT), 0) FROM src.main.{q} x").fetchone()[0]
            h_dst = con.execute(f"SELECT coalesce(sum(hash(x)::HUGEINT), 0) FROM dst.main.{q} x").fetchone()[0]
            lost = con.execute(f"SELECT count(*) FROM (SELECT * FROM src.main.{q} "
                               f"EXCEPT ALL SELECT * FROM dst.main.{q})").fetchone()[0]
            extra = con.execute(f"SELECT count(*) FROM (SELECT * FROM dst.main.{q} "
                                f"EXCEPT ALL SELECT * FROM src.main.{q})").fetchone()[0]
            if n_src != n_dst:
                problems.append(f"{t}: row count {n_src} -> {n_dst}")
            if lost:
                problems.append(f"{t}: {lost} source row(s) missing or changed in the compacted DB")
            if extra:
                problems.append(f"{t}: {extra} row(s) in the compacted DB not in the source")
            if h_src != h_dst:
                problems.append(f"{t}: row-multiset hash differs")
            nonfinite = 0
            for column, data_type in a["columns"][t]:
                spec = _float_kind(data_type)
                if spec is None:
                    continue
                s_sig = _float_bits_signature(con, "src", t, column, *spec)
                d_sig = _float_bits_signature(con, "dst", t, column, *spec)
                nonfinite += s_sig["nonfinite"]
                if s_sig != d_sig:
                    problems.append(f"{t}.{column}: float bits differ (signed zero, NaN/Inf or subnormal)")
            report[t] = {"rows": n_src, "hash": str(h_src), "nonfinite": nonfinite}
    finally:
        con.close()
    if problems:
        raise RuntimeError("COMPACTION PROOF FAILED: " + "; ".join(problems))
    return report


def _free_bytes(path: str) -> int:
    return shutil.disk_usage(path).free


def _refuse_symlink(path: str, what: str) -> None:
    """Refuse an existing symlink at a path we are about to create/open/replace."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode):
        raise RuntimeError(f"compaction: {what} {path} is a symlink; refusing")


def _open_source(src: str) -> tuple[int, dict]:
    """Open the source read-only without following a symlink; snapshot its identity and bytes.

    The descriptor is kept open for the whole operation (so the inode cannot be swapped underneath
    us) and carries an exclusive advisory lock where the filesystem supports one. The snapshot is
    re-checked from this same descriptor immediately before the commit.
    """
    try:
        fd = os.open(src, os.O_RDONLY | _NOFOLLOW)
    except OSError as exc:
        raise RuntimeError(f"compaction: cannot open source {src} without following links: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"compaction: source {src} is not a regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"compaction: another process holds a write lock on the source {src}; refusing") from exc
        except OSError:
            pass  # advisory locks are not supported on every Colab/Drive mount; the re-hash still guards us
        snapshot = {"dev": st.st_dev, "ino": st.st_ino, "size": st.st_size,
                    "mtime_ns": st.st_mtime_ns, "sha256": _sha256_fd(fd)}
        return fd, snapshot
    except BaseException:
        os.close(fd)
        raise


def _source_changed(fd: int, src: str, snapshot: dict) -> str | None:
    """Why the source no longer matches the pre-export snapshot, or None if it is unchanged."""
    st = os.fstat(fd)
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
            snapshot["dev"], snapshot["ino"], snapshot["size"], snapshot["mtime_ns"]):
        return "size, inode or mtime changed"
    try:
        path_st = os.lstat(src)
    except FileNotFoundError:
        return "path disappeared"
    if (path_st.st_dev, path_st.st_ino) != (snapshot["dev"], snapshot["ino"]):
        return "path now names a different file"
    if os.lseek(fd, 0, os.SEEK_SET) != 0 or _sha256_fd(fd) != snapshot["sha256"]:
        return "contents changed"
    return None


def compact_duckdb(src: str, dst: str, workdir: str, protect=(), on_step=None) -> dict:
    """Rewrite `src` densely (EXPORT DATABASE parquet -> IMPORT DATABASE into a fresh file) and put it at `dst`.

    `dst` may equal `src` (in-place). The fresh file is built in a private temp directory next to `dst`,
    CHECKPOINTed and closed (no .wal), and proven content-identical (including bit-exact embeddings) to `src`
    by compact_identity_proof. The source is opened with O_NOFOLLOW, held under an exclusive advisory lock,
    and its size/inode/mtime and sha256 are re-checked immediately before the atomic replace; if it changed
    in the meantime (a write injected between the proof and the swap) the replace is refused. Symlinked
    source, destination or workdir are refused. `on_step(name)` is called at 'proved' (after the proof,
    before the final re-check) so tests can inject a concurrent write.

    Failure guarantee: before the commit point (`os.replace`) any failure leaves `src` and `dst` untouched
    and removes the temporary files. The temp file is fsynced before the replace. A directory-fsync failure
    *after* the replace is a committed-state outcome: the swap is not undone and cannot be raised as if it
    had not happened, so it is returned as `warning` with `committed=True` instead. Paths in `protect` (for
    example the pinned production cache file) are never read-write opened, replaced or removed: a protected
    src/dst is refused, re-checked just before the swap. Needs ~2x the source size free (export + fresh file).
    Returns before/after bytes and free blocks plus the per-table proof report.
    """
    step = on_step or (lambda name: None)
    if not os.path.isfile(src):
        raise RuntimeError(f"compaction: missing source {src}")
    _refuse_symlink(src, "source")
    _refuse_symlink(dst, "destination")
    _refuse_symlink(workdir, "workdir")
    for p in protect:
        _refuse_symlink(p, "protected path")
    real = {os.path.realpath(p) for p in protect}
    for label, p in (("source", src), ("destination", dst)):
        if os.path.realpath(p) in real:
            raise RuntimeError(f"compaction: {label} {p} is protected (read-only original); refusing")
    for p in (src, dst):
        if os.path.exists(p + ".wal"):
            raise RuntimeError(f"compaction: {p}.wal exists (DB not cleanly closed); refusing")
    size = os.path.getsize(src)
    os.makedirs(workdir, exist_ok=True)
    _refuse_symlink(workdir, "workdir")
    dst_dir = os.path.dirname(os.path.abspath(dst))
    os.makedirs(dst_dir, exist_ok=True)
    need = 2 * size
    if os.stat(workdir).st_dev == os.stat(dst_dir).st_dev:
        free = _free_bytes(dst_dir)
        if free < need:
            raise RuntimeError(f"compaction: not enough disk space: need ~{need} bytes free, have {free}")
    else:
        for d in (workdir, dst_dir):
            free = _free_bytes(d)
            if free < size:
                raise RuntimeError(f"compaction: not enough disk space in {d}: need ~{size} bytes free, have {free}")
    before = _db_size(src)
    export_dir = os.path.join(workdir, f"export-{secrets.token_hex(4)}")
    tmp_dir = os.path.join(dst_dir, f".{os.path.basename(dst)}.compact-{secrets.token_hex(4)}")
    tmp = os.path.join(tmp_dir, "db.duckdb")
    src_fd = None
    committed = False
    warning = None
    try:
        src_fd, snapshot = _open_source(src)
        con = duckdb.connect(src, read_only=True)
        try:
            con.execute(f"EXPORT DATABASE '{export_dir.replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)")
        finally:
            con.close()
        os.mkdir(tmp_dir, 0o700)  # atomic: fails if a symlink/file already sits at this random name
        _refuse_symlink(tmp_dir, "temp destination")
        if not stat.S_ISDIR(os.lstat(tmp_dir).st_mode):
            raise RuntimeError(f"compaction: temp destination {tmp_dir} is not a directory")
        con = duckdb.connect(tmp)
        try:
            con.execute(f"IMPORT DATABASE '{export_dir.replace(chr(39), chr(39) * 2)}'")
            con.execute("CHECKPOINT")
        finally:
            con.close()
        if os.path.exists(tmp + ".wal"):
            raise RuntimeError("compaction: the fresh DB left a .wal after CHECKPOINT; refusing")
        report = compact_identity_proof(src, tmp)  # raises on any diff, before anything is replaced
        after = _db_size(tmp)
        _fsync_file(tmp)  # durable before the replace; nothing after the replace can raise as a failure
        step("proved")
        changed = _source_changed(src_fd, src, snapshot)
        if changed:
            raise RuntimeError(
                f"compaction: source {src} changed after the identity proof ({changed}); refusing to replace")
        if os.path.realpath(src) in real or os.path.realpath(dst) in real:
            raise RuntimeError("compaction: source or destination became the protected original; refusing")
        _refuse_symlink(dst, "destination")
        os.replace(tmp, dst)
        committed = True
        try:
            _fsync_dir(dst_dir)
        except Exception as exc:  # committed: report, never pretend the swap did not happen
            warning = f"directory fsync failed after the swap was committed: {exc}"
    finally:
        if src_fd is not None:
            os.close(src_fd)
        shutil.rmtree(export_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    result = {"bytes_before": before["bytes"], "bytes_after": after["bytes"],
              "free_blocks_before": before["free_blocks"], "free_blocks_after": after["free_blocks"],
              "total_blocks_before": before["total_blocks"], "total_blocks_after": after["total_blocks"],
              "sha256_after": sha256_file(dst), "tables": report,
              "committed": committed, "warning": warning}
    return result
