import json
import os
import re
import stat
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from scripts import hf_backfill, prepare_db_copy

ROOT = Path(__file__).resolve().parent.parent


def _make_db(path, rows):
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE edgar_embeddings (ticker VARCHAR, accession VARCHAR, chunk_index INTEGER)"
    )
    for r in rows:
        con.execute("INSERT INTO edgar_embeddings VALUES (?, ?, ?)", r)
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
    con.execute("INSERT INTO edgar_embeddings VALUES ('A', 'x', 1)")
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


def test_copy_writable_missing_source_raises_and_keeps_dst(tmp_path):
    dst = tmp_path / "rag.duckdb"
    with pytest.raises(FileNotFoundError):
        prepare_db_copy.copy_writable(str(tmp_path / "nope"), str(dst))
    assert not dst.exists()
