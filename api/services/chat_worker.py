"""Child-process worker for sandboxed chat SQL (run as a script, not imported).

Protocol: stdin = one JSON header line, then the raw Arrow IPC streams named in
the header; stdout = one JSON document.  The worker never sees the real DB file.
Hard OS limits are applied before any generated SQL runs, and DuckDB external
access is disabled and locked.
"""
import decimal
import json
import math
import re
import resource
import sys


def _vsz() -> int:
    with open("/proc/self/statm") as fh:
        return int(fh.read().split()[0]) * resource.getpagesize()


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, decimal.Decimal):
        return float(v)
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


_PLAIN = re.compile(r"(U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?|FLOAT|DOUBLE|BOOLEAN|DATE|TIMESTAMP.*|DECIMAL.*|TIME.*)")


def main() -> None:
    import duckdb  # noqa: PLC0415 - imported before limits so library mappings fit
    import pyarrow as pa  # noqa: PLC0415

    inp = sys.stdin.buffer
    header = json.loads(inp.readline())
    blobs = {name: inp.read(n) for name, n in header["tables"]}
    lim = header["limits"]
    # Limits go in before the generated SQL (or any table load) runs.
    resource.setrlimit(resource.RLIMIT_AS, (_vsz() + lim["as_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (lim["cpu_seconds"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))

    db = duckdb.connect(":memory:")
    db.execute("SET threads TO 2")
    db.execute(f"SET memory_limit TO '{lim['memory_mb']}MB'")
    for name, data in blobs.items():
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            raise ValueError("bad table name")
        db.register("_m", pa.ipc.open_stream(pa.py_buffer(data)).read_all())
        db.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _m')
        db.unregister("_m")
    db.execute("SET python_enable_replacements=false")
    db.execute("SET enable_external_access=false")
    db.execute("SET lock_configuration=true")

    sql = header["sql"]
    cols = db.execute(f"DESCRIBE SELECT * FROM ({sql}) AS q").fetchall()
    aliases = ", ".join(f"c{i}" for i in range(len(cols)))
    cell = lim["max_cell_chars"]
    exprs = []
    for i, (name, ctype, *_r) in enumerate(cols):
        alias = '"' + str(name).replace('"', '""') + '"'
        if _PLAIN.fullmatch(ctype):
            exprs.append(f"c{i} AS {alias}")
        else:
            exprs.append(f"left(CAST(c{i} AS VARCHAR), {cell}) AS {alias}")
    wrapped = (
        f"SELECT {', '.join(exprs)} FROM (SELECT * FROM ({sql}) AS q({aliases})) "
        f"LIMIT {lim['max_rows']}"
    )
    cur = db.execute(wrapped)
    names = [d[0] for d in cur.description]
    rows = [{n: _clean(v) for n, v in zip(names, r)} for r in cur.fetchall()]
    body = json.dumps({"ok": True, "rows": rows})
    if len(json.dumps(rows)) > lim["max_result_bytes"]:
        body = json.dumps({"ok": False, "error": "Chat query result is too large.", "limit": True})
    sys.stdout.write(body)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # noqa: BLE001 - report every failure as JSON
        sys.stdout.write(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
