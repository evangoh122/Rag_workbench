import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from scripts import hf_backfill, prepare_db_copy

ROOT = Path(__file__).resolve().parent.parent


def _make_db(path, rows):
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE edgar_embeddings (ticker VARCHAR, accession VARCHAR, chunk_index INTEGER, "
        "section_id VARCHAR)"
    )
    for r in rows:
        r = tuple(r) if len(r) == 4 else (*r, "business")
        con.execute("INSERT INTO edgar_embeddings VALUES (?, ?, ?, ?)", r)
    con.close()


@pytest.fixture
def readonly_src(tmp_path):
    src = tmp_path / "cache_blob.duckdb"
    _make_db(src, [("AAPL", "0001-25-000001", 0)])
    os.chmod(src, stat.S_IRUSR)  # what the HF cache hands back
    return src


def test_copy_writable_makes_readwrite_copy(readonly_src, tmp_path):
    dst = tmp_path / "rag.duckdb"
    prepare_db_copy.copy_writable(str(readonly_src), str(dst))
    assert os.access(dst, os.W_OK)
    prepare_db_copy.check_writable(str(dst))


def test_plain_shutil_copy_is_not_writable(readonly_src, tmp_path):
    """Documents the bug: shutil.copy keeps the read-only bits (skipped when root)."""
    import shutil

    if os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    dst = tmp_path / "bad.duckdb"
    shutil.copy(readonly_src, dst)
    with pytest.raises(PermissionError):
        prepare_db_copy.check_writable(str(dst))


def test_copy_writable_overwrites_existing_readonly_dst(readonly_src, tmp_path):
    dst = tmp_path / "rag.duckdb"
    dst.write_bytes(b"old")
    os.chmod(dst, stat.S_IRUSR)
    prepare_db_copy.copy_writable(str(readonly_src), str(dst))
    prepare_db_copy.check_writable(str(dst))


def test_check_writable_rolls_back_probe(tmp_path):
    db = tmp_path / "w.duckdb"
    _make_db(db, [("A", "x", 0)])
    prepare_db_copy.check_writable(str(db))
    con = duckdb.connect(str(db), read_only=True)
    tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
    con.close()
    assert tables == ["edgar_embeddings"]


def test_cli_check_fails_on_readonly(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    db = tmp_path / "ro.duckdb"
    _make_db(db, [("A", "x", 0)])
    os.chmod(db, stat.S_IRUSR)
    assert prepare_db_copy.main(["p", "check", str(db)]) == 1


def test_workflows_use_helper_and_failfast_before_embedding():
    for name in ("refresh-filings.yml", "embed-annuals.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text()
        assert "shutil.copy(" not in text
        assert "copy_writable(path" in text
        assert text.index("prepare_db_copy.py check") < text.index("Snapshot corpus BEFORE")
        assert text.index("prepare_db_copy.py check") < text.index("- name: Embed")


# ── HF backfill helpers ──────────────────────────────────────────────────────


def test_snapshot_records_sha_and_counts(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0), ("A", "x", 1), ("B", "y", 0)])
    out = tmp_path / "before.json"
    snap = hf_backfill.take_snapshot(str(db), str(out), "head123")
    assert snap["rows"] == 3 and snap["filings"] == 2
    assert json.loads(out.read_text())["sha256"] == hf_backfill.sha256_file(str(db))
    assert snap["dataset_head"] == "head123"


def test_verify_detects_duplicates_and_shrink(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0), ("A", "x", 1)])
    before = tmp_path / "b.json"
    hf_backfill.take_snapshot(str(db), str(before))
    assert hf_backfill.verify_after(str(db), str(before))["rows"] == 2

    con = duckdb.connect(str(db))
    con.execute("INSERT INTO edgar_embeddings VALUES ('A', 'x', 1, 'business')")
    con.close()
    with pytest.raises(RuntimeError, match="duplicated"):
        hf_backfill.verify_after(str(db), str(before))

    con = duckdb.connect(str(db))
    con.execute("DELETE FROM edgar_embeddings")
    con.close()
    with pytest.raises(RuntimeError, match="shrank"):
        hf_backfill.verify_after(str(db), str(before))


def test_check_cuda_fails_without_gpu(monkeypatch):
    fake = MagicMock()
    fake.cuda.is_available.return_value = False
    monkeypatch.setitem(__import__("sys").modules, "torch", fake)
    with pytest.raises(RuntimeError, match="cuda"):
        hf_backfill.check_cuda()
    assert hf_backfill.main(["check-cuda"]) == 1


def test_publish_requires_confirm_and_unchanged_head(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0)])
    before = tmp_path / "b.json"
    hf_backfill.take_snapshot(str(db), str(before), "aaa")

    api = MagicMock()
    api.repo_info.return_value.sha = "aaa"
    with pytest.raises(RuntimeError, match="--confirm"):
        hf_backfill.guarded_publish(str(db), str(before), "u/r", False, api)
    api.upload_file.assert_not_called()

    api.repo_info.return_value.sha = "bbb"  # head moved
    with pytest.raises(RuntimeError, match="moved"):
        hf_backfill.guarded_publish(str(db), str(before), "u/r", True, api)
    api.upload_file.assert_not_called()

    api.repo_info.return_value.sha = "aaa"
    hf_backfill.guarded_publish(str(db), str(before), "u/r", True, api)
    assert api.upload_file.call_args.kwargs["parent_commit"] == "aaa"


def test_publish_refuses_snapshot_without_head(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0)])
    before = tmp_path / "b.json"
    hf_backfill.take_snapshot(str(db), str(before))
    with pytest.raises(RuntimeError, match="dataset_head"):
        hf_backfill.guarded_publish(str(db), str(before), "u/r", True, MagicMock())


def test_runner_never_publishes_or_restarts():
    lines = (ROOT / "scripts" / "run_hf_backfill.sh").read_text().splitlines()
    text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    for banned in ("upload_file", "upload_folder", "restart_space", "create_commit", "hf_backfill.py publish"):
        assert banned not in text
    assert "check-cuda" in text and text.index("check-cuda") < text.index("embed_additional.py")
    assert text.index("snapshot") < text.index("embed_additional.py") < text.index("verify")
    assert re.search(r"^set -euo pipefail", text, re.M)


def test_gpu_dockerfile_torch_pin_matches_lock_and_base_image():
    text = (ROOT / "Dockerfile.hf-gpu").read_text()
    lock = (ROOT / "uv.lock").read_text()
    locked = re.search(r'name = "torch"\nversion = "(\d+\.\d+\.\d+)"\nsource = \{ registry = "https://pypi', lock).group(1)
    tag = re.search(r"ARG TORCH_CUDA_TAG=(cu\d+)", text).group(1)
    pin = re.search(r'"torch==([\d.]+)\+\$\{TORCH_CUDA_TAG\}"', text)
    assert pin and pin.group(1) == locked  # same torch version as uv.lock
    assert "whl/${TORCH_CUDA_TAG}" in text
    base = re.search(r"FROM nvidia/cuda:(\d+)\.(\d+)", text)
    assert tag == f"cu{base.group(1)}{base.group(2)}"  # wheel CUDA == base image CUDA
    assert "torch.version.cuda" in text and "+cpu" in text  # build-time assertion
    assert "uv sync --locked" in text and "uv lock" not in text


def test_copy_writable_follows_symlink_source(tmp_path):
    real = tmp_path / "blob"
    _make_db(real, [("A", "x", 0)])
    os.chmod(real, stat.S_IRUSR)
    link = tmp_path / "snapshots_link.duckdb"
    link.symlink_to(real)
    dst = tmp_path / "rag.duckdb"
    prepare_db_copy.copy_writable(str(link), str(dst))
    assert not dst.is_symlink() and os.access(dst, os.W_OK)
    prepare_db_copy.check_writable(str(dst))


def _valid_dst(tmp_path):
    dst = tmp_path / "rag.duckdb"
    _make_db(dst, [("KEEP", "x", 0)])
    return dst, dst.read_bytes()


def test_copy_writable_missing_source_keeps_existing_dst(tmp_path):
    dst, before = _valid_dst(tmp_path)
    with pytest.raises(FileNotFoundError):
        prepare_db_copy.copy_writable(str(tmp_path / "nope"), str(dst))
    assert dst.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["rag.duckdb"]  # no temp left


def test_copy_writable_midcopy_failure_keeps_existing_dst(tmp_path, monkeypatch, readonly_src):
    dst, before = _valid_dst(tmp_path)

    def boom(src, tmp):
        Path(tmp).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(prepare_db_copy.shutil, "copyfile", boom)
    with pytest.raises(OSError):
        prepare_db_copy.copy_writable(str(readonly_src), str(dst))
    assert dst.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache_blob.duckdb", "rag.duckdb"]


def test_copy_writable_replaces_symlink_dest_not_target(readonly_src, tmp_path):
    target = tmp_path / "target.duckdb"
    target.write_bytes(b"orig")
    link = tmp_path / "rag.duckdb"
    link.symlink_to(target)
    prepare_db_copy.copy_writable(str(readonly_src), str(link))
    assert not link.is_symlink()
    assert target.read_bytes() == b"orig"
    prepare_db_copy.check_writable(str(link))


def test_copy_writable_dest_may_not_exist(readonly_src, tmp_path):
    dst = tmp_path / "sub_rag.duckdb"
    prepare_db_copy.copy_writable(str(readonly_src), str(dst))
    assert dst.exists()


# ── effective DB path through the real config code ──────────────────────────


def test_effective_db_rejects_path_config_would_substitute(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/hf_backfill_staging/rag.duckdb")
    monkeypatch.setenv("PERSIST_DIR", "")
    with pytest.raises(RuntimeError, match="effective DB_PATH"):
        hf_backfill.assert_effective_db("/tmp/hf_backfill_staging/rag.duckdb")


def test_effective_db_accepts_staging_dir_under_repo(monkeypatch):
    staging = ROOT / "data" / "hf_backfill_staging" / "rag.duckdb"
    monkeypatch.setenv("DB_PATH", str(staging))
    assert hf_backfill.assert_effective_db(str(staging)) == str(staging.resolve())


def test_runner_default_staging_is_allowed_by_config(monkeypatch):
    text = (ROOT / "scripts" / "run_hf_backfill.sh").read_text()
    assert "/tmp/hf_backfill_staging" not in text.replace("# ", "").split("STAGING_DIR=")[1]
    assert 'ROOT/data/hf_backfill_staging' in text
    assert "effective-db" in text and text.index("effective-db") < text.index("embed_additional.py")
    assert 'export DB_PATH="$WORK_DB"' in text


# ── fix round: entry point, duplicate key, execution gate, pre-upload guard ──

PROSE = ("Revenue grew because demand for our products increased across regions. "
         "Management expects continued investment in research and development. ")


def test_real_module_entry_point_imports_api(tmp_path):
    """The runner invokes `python -m scripts.hf_backfill`; `api.config` must import there."""
    db = tmp_path / "data" / "rag.duckdb"
    db.parent.mkdir()
    _make_db(db, [("A", "x", 0)])
    env = {**os.environ, "DB_PATH": str(db), "PERSIST_DIR": ""}
    r = subprocess.run(
        [sys.executable, "-m", "scripts.hf_backfill", "effective-db", str(db)],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert "No module named" not in r.stdout + r.stderr
    # Either the path is accepted or the allowlist rejects it, but never an ImportError.
    assert "EFFECTIVE DB OK" in r.stdout or "effective DB_PATH" in r.stdout


def test_runner_and_docs_invoke_hf_backfill_as_module():
    for name in ("scripts/run_hf_backfill.sh", "README.md"):
        for line in (ROOT / name).read_text().splitlines():
            if "hf_backfill" in line and "python" in line and "run_hf_backfill" not in line:
                assert "scripts/hf_backfill.py" not in line, (name, line)
    assert "-m scripts.hf_backfill" in (ROOT / "scripts" / "run_hf_backfill.sh").read_text()


def test_duplicate_guard_accepts_real_multi_section_chunker_output(tmp_path):
    from api.services.structure_chunker import StructureChunker

    chunker = StructureChunker()
    db = tmp_path / "rag.duckdb"
    _make_db(db, [])
    con = duckdb.connect(str(db))
    for label in ("business", "risk_factors"):
        chunks = chunker.chunk(PROSE * 3, section_label=label, ticker="AAPL", form_type="10-K")
        assert chunks and chunks[0].metadata.chunk_index == 0  # index restarts per section
        for c in chunks:
            con.execute(
                "INSERT INTO edgar_embeddings VALUES (?, ?, ?, ?)",
                ["AAPL", "0001-25-000001", c.metadata.chunk_index, c.metadata.section_label],
            )
    con.close()
    assert hf_backfill.duplicate_chunks(str(db)) == 0
    before = tmp_path / "b.json"
    hf_backfill.take_snapshot(str(db), str(before))
    assert hf_backfill.verify_after(str(db), str(before))["rows"] >= 2


def test_duplicate_guard_still_flags_true_duplicate(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0, "business"), ("A", "x", 0, "risk_factors"), ("A", "x", 0, "business")])
    assert hf_backfill.duplicate_chunks(str(db)) == 1


# Stub interpreter: logs argv, consumes stdin, prints a fake dataset head.
STUB = """#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
if [ "$1" = "-" ]; then cat >/dev/null; echo deadbeef; fi
exit 0
"""

BASE_ENV = {"DATASET_REPO": "u/r", "BACKFILL_TICKERS": "AAPL,MSFT"}


def _run_runner(tmp_path, extra_env=None, args=(), timeout=60):
    stub = tmp_path / "stubpy"
    stub.write_text(STUB)
    stub.chmod(0o755)
    log = tmp_path / "stub.log"
    log.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BACKFILL_", "DATASET_"))}
    env.update(BASE_ENV, PYTHON=str(stub), STUB_LOG=str(log), STAGING_DIR=str(tmp_path / "stage"))
    env.update(extra_env or {})
    r = subprocess.run(["bash", str(ROOT / "scripts" / "run_hf_backfill.sh"), *args],
                       env=env, capture_output=True, text=True, timeout=timeout)
    return r, log.read_text()


def test_runner_is_dry_run_by_default(tmp_path):
    r, calls = _run_runner(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "DRY RUN" in r.stdout and "AAPL" in r.stdout and "4 filings" in r.stdout
    assert calls == ""
    assert not (tmp_path / "stage").exists()


@pytest.mark.parametrize("how", ["env", "flag"])
def test_runner_executes_only_with_explicit_gate(tmp_path, how):
    kw = {"extra_env": {"BACKFILL_CONFIRM": "yes"}} if how == "env" else {"args": ["--execute"]}
    r, calls = _run_runner(tmp_path, **kw)
    assert r.returncode == 0, r.stderr
    assert "embed_additional.py" in calls and "-m scripts.hf_backfill check-cuda" in calls
    assert "--tickers AAPL,MSFT" in calls


def test_runner_confirm_must_be_exactly_yes(tmp_path):
    r, calls = _run_runner(tmp_path, {"BACKFILL_CONFIRM": "true"})
    assert "DRY RUN" in r.stdout and calls == ""


@pytest.mark.parametrize(
    "env",
    [
        {"BACKFILL_TICKERS": "A,B,C", "BACKFILL_MAX_TICKERS": "2"},
        {"BACKFILL_MAX_TICKERS": "0"},
        {"BACKFILL_MAX_TICKERS": "51"},
        {"BACKFILL_MAX_TICKERS": "ten"},
        {"BACKFILL_TICKERS": "AAPL;rm -rf /"},
        {"BACKFILL_TICKERS": "AAPL,,MSFT"},
        {"BACKFILL_FORMS": "10-K"},
        {"BACKFILL_FORMS": "10-Q", "BACKFILL_QUARTERS": "0"},
        {"BACKFILL_FORMS": "10-Q", "BACKFILL_QUARTERS": "9"},
        {"BACKFILL_FORMS": "10-Q", "BACKFILL_QUARTERS": "abc"},
        {"BACKFILL_QUARTERS": "-1"},
        {"BACKFILL_TIMEOUT_SECONDS": "59"},
        {"BACKFILL_TIMEOUT_SECONDS": "21601"},
        {"BACKFILL_TIMEOUT_SECONDS": "soon"},
    ],
)
@pytest.mark.parametrize("confirm", ["yes", ""])
def test_runner_rejects_invalid_caps_loudly(tmp_path, env, confirm):
    r, calls = _run_runner(tmp_path, {**env, "BACKFILL_CONFIRM": confirm})
    assert r.returncode != 0
    assert "::error::" in r.stderr
    assert calls == ""


def test_runner_enforces_deadline_with_timeout(tmp_path):
    """A fake `timeout` on PATH records the deadline the script really passes."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "timeout"
    fake.write_text('#!/usr/bin/env bash\necho "TIMEOUT $*" >> "$STUB_LOG"\nshift 3\nexec "$@"\n')
    fake.chmod(0o755)
    r, calls = _run_runner(
        tmp_path,
        {"BACKFILL_CONFIRM": "yes", "BACKFILL_TIMEOUT_SECONDS": "1234",
         "PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert r.returncode == 0, r.stderr
    assert calls.splitlines()[0].startswith("TIMEOUT -k 30 1234 env BACKFILL_INNER=1 bash")


def test_runner_does_not_expand_python_unquoted():
    text = (ROOT / "scripts" / "run_hf_backfill.sh").read_text()
    assert not re.search(r"^\s*\$PY\b", text, re.M) and "$($PY" not in text
    assert '"${PY[@]}"' in text and "set -euo pipefail" in text


def test_publish_reruns_guards_on_staged_file_before_upload(tmp_path):
    db = tmp_path / "rag.duckdb"
    _make_db(db, [("A", "x", 0), ("A", "x", 1)])
    before = tmp_path / "b.json"
    hf_backfill.take_snapshot(str(db), str(before), "aaa")
    api = MagicMock()
    api.repo_info.return_value.sha = "aaa"

    # corrupted staged file
    db.write_bytes(b"not a duckdb file" * 100)
    with pytest.raises(RuntimeError, match="integrity"):
        hf_backfill.guarded_publish(str(db), str(before), "u/r", True, api)
    api.upload_file.assert_not_called()

    # duplicate introduced after the runner's verify
    _make_db(db.with_name("d.duckdb"), [("A", "x", 0), ("A", "x", 0)])
    with pytest.raises(RuntimeError, match="duplicated"):
        hf_backfill.guarded_publish(str(db.with_name("d.duckdb")), str(before), "u/r", True, api)
    api.upload_file.assert_not_called()


def test_gpu_dockerfile_runs_non_root_with_writable_dirs():
    text = (ROOT / "Dockerfile.hf-gpu").read_text()
    user = re.search(r"^USER (\S+)", text, re.M)
    assert user and user.group(1) not in ("root", "0")
    for var in ("HOME=", "HF_HOME=", "UV_CACHE_DIR="):
        assert var in text
    assert text.index("USER app") > text.index("COPY --chown=app:app . .")
