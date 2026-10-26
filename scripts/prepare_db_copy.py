"""Make the HF-cached DuckDB usable as a working copy in CI.

`hf_hub_download` returns a path inside the HF cache whose blob is read-only.
`shutil.copy` preserves those permission bits, so the copied `data/rag.duckdb`
is read-only and the embedding step later dies with "Permission denied".

    uv run python scripts/prepare_db_copy.py copy  <cached_path> data/rag.duckdb
    uv run python scripts/prepare_db_copy.py check data/rag.duckdb

`check` is the fail-fast gate: it opens the DB read-write and does a trivial
write inside a transaction that is rolled back, so nothing is persisted.
"""
import os
import shutil
import stat
import sys

import duckdb


def copy_writable(src: str, dst: str) -> str:
    """Copy contents only (no mode bits) and force the owner write bit on."""
    if os.path.lexists(dst):
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IWUSR)
        os.remove(dst)
    shutil.copyfile(src, dst)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IWUSR)
    return dst


def check_writable(db_path: str) -> None:
    """Raise if the DB cannot be opened read-write and written inside a transaction."""
    if not os.access(db_path, os.W_OK):
        raise PermissionError(f"{db_path} is not writable by the current user")
    con = duckdb.connect(db_path, read_only=False)
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("CREATE TABLE __write_probe (i INTEGER)")
        con.execute("INSERT INTO __write_probe VALUES (1)")
        con.execute("ROLLBACK")
    finally:
        con.close()


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "copy":
        copy_writable(argv[2], argv[3])
        print(f"Copied {argv[2]} -> {argv[3]} ({os.path.getsize(argv[3]) / 1e6:.1f} MB, writable)")
        return 0
    if len(argv) == 3 and argv[1] == "check":
        try:
            check_writable(argv[2])
        except Exception as exc:
            print(f"::error::{argv[2]} is not writable: {exc}")
            return 1
        print(f"{argv[2]} opens read-write; probe write rolled back OK")
        return 0
    print("usage: prepare_db_copy.py copy <src> <dst> | check <db_path>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
