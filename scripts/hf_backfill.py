"""Helpers for the HF Jobs GPU backfill (scripts/run_hf_backfill.sh).

Run as a module from the repo root (`python -m scripts.hf_backfill ...`) so the
`api` package is importable; running the file directly puts scripts/ on sys.path
and breaks `import api.config`.

    check-cuda                                       fail unless torch.cuda.is_available()
    snapshot  <db> <out.json> [--dataset-head SHA]   sha256 + row/filing counts
    verify    <db> <before.json>                     counts + duplicate-chunk check
    effective-db <db>                                fail unless Config.DB_PATH resolves to <db>
    stage-check  --repo S --prod-repo P              fail unless S is an existing PRIVATE dataset != P
    stage-upload <db> <before.json> --repo S --prod-repo P --run-id ID
                                                     copy the result to S under runs/ID/ (never P)
    publish   <db> <before.json> --repo R --confirm  GUARDED; never run by the runner
    publish   --staging-repo S --run-id ID --repo R --confirm
                                                     same, after downloading runs/ID/ from S

A job container is ephemeral, so the runner uploads its result to a private staging
dataset (stage-upload); only `publish` can touch the production dataset. It refuses without --confirm,
aborts if the dataset head moved since the snapshot was taken, and re-runs the
integrity + duplicate guards on a private snapshot of the staged file and uploads that
same verified snapshot.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

import duckdb

DB_FILENAME = "rag.duckdb"
BEFORE_FILENAME = "before.json"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def counts(db_path: str) -> dict:
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute("SELECT count(*) FROM edgar_embeddings").fetchone()[0]
        filings = con.execute(
            "SELECT count(*) FROM (SELECT DISTINCT ticker, accession FROM edgar_embeddings)"
        ).fetchone()[0]
        return {"rows": rows, "filings": filings}
    finally:
        con.close()


def duplicate_chunks(db_path: str) -> int:
    """Number of (ticker, accession, section_id, chunk_index) keys stored more than once.

    StructureChunker restarts chunk_index at 0 for every section and embed_additional
    stores it unchanged, so chunk_index alone is only unique within a section.
    """
    con = duckdb.connect(db_path, read_only=True)
    try:
        cols = {r[0] for r in con.execute("DESCRIBE edgar_embeddings").fetchall()}
        if "section_id" not in cols:
            raise RuntimeError("edgar_embeddings has no section_id column; cannot check duplicates")
        return con.execute(
            "SELECT count(*) FROM (SELECT 1 FROM edgar_embeddings "
            "GROUP BY ticker, accession, COALESCE(section_id, ''), chunk_index HAVING count(*) > 1)"
        ).fetchone()[0]
    finally:
        con.close()


def effective_db_path() -> str:
    """The DB path embed_additional.py will really open (api.config applies an allowlist)."""
    from api.config import _validate_db_path

    return _validate_db_path(os.getenv("DB_PATH", "./data/rag.duckdb"))


def assert_effective_db(expected: str) -> str:
    """Fail closed if the config code would silently substitute a different DB."""
    got = os.path.realpath(effective_db_path())
    want = os.path.realpath(expected)
    if got != want:
        raise RuntimeError(f"effective DB_PATH {got} != intended staging DB {want}; refusing to embed")
    return got


def check_cuda() -> None:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch.cuda.is_available() is False; refusing to run the GPU backfill on CPU")
    print(f"CUDA OK: {torch.cuda.get_device_name(0)} (torch {torch.__version__})")


def take_snapshot(db_path: str, out_path: str, dataset_head: str | None = None) -> dict:
    snap = {"sha256": sha256_file(db_path), "dataset_head": dataset_head, **counts(db_path)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2)
    return snap


def verify_after(db_path: str, before_path: str) -> dict:
    """Raise on shrink or duplicate chunk keys; return the after-counts."""
    with open(before_path, encoding="utf-8") as f:
        before = json.load(f)
    try:
        after = counts(db_path)
    except duckdb.Error as exc:
        raise RuntimeError(f"staged DB failed integrity check: {exc}") from exc
    errors = []
    if after["rows"] < before["rows"]:
        errors.append(f"rows shrank {before['rows']} -> {after['rows']}")
    if after["filings"] < before["filings"]:
        errors.append(f"filings shrank {before['filings']} -> {after['filings']}")
    dups = duplicate_chunks(db_path)
    if dups:
        errors.append(f"{dups} duplicated (ticker, accession, section_id, chunk_index) keys")
    if errors:
        raise RuntimeError("; ".join(errors))
    return after


def guarded_publish(db_path: str, before_path: str, repo: str, confirm: bool, api=None) -> str:
    """Send db_path to dataset `repo` only if its head still equals the snapshot's."""
    if not confirm:
        raise RuntimeError("publish requires --confirm")
    with open(before_path, encoding="utf-8") as f:
        before = json.load(f)
    if not before.get("dataset_head"):
        raise RuntimeError("snapshot has no dataset_head; cannot prove the dataset is unchanged")
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
    head = api.repo_info(repo, repo_type="dataset").sha
    if head != before["dataset_head"]:
        raise RuntimeError(f"dataset head moved since snapshot: {before['dataset_head']} -> {head}; aborting")
    # Verify and upload the same bytes: snapshot the staged file into a private
    # temp dir, verify the snapshot, and upload that snapshot only if its hash is
    # unchanged. A swap of the staged path after the copy cannot reach the upload.
    with tempfile.TemporaryDirectory(prefix="hf_publish_") as tmp:
        os.chmod(tmp, 0o700)
        snap = os.path.join(tmp, DB_FILENAME)
        shutil.copyfile(db_path, snap)
        digest = sha256_file(snap)
        verify_after(snap, before_path)
        if sha256_file(snap) != digest:
            raise RuntimeError("snapshot changed after verification; refusing to upload")
        api.upload_file(
            path_or_fileobj=snap,
            path_in_repo=DB_FILENAME,
            repo_id=repo,
            repo_type="dataset",
            commit_message="ETL(gpu-backfill): guarded publish",
            parent_commit=head,
        )
    return head


def _norm_repo(repo: str) -> str:
    return repo.strip().lower()


def _check_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id or "") or ".." in run_id:
        raise RuntimeError(f"invalid run id {run_id!r}; use 1-80 chars of [A-Za-z0-9._-]")
    return run_id


def check_staging_repo(staging_repo: str, prod_repo: str, api=None) -> None:
    """Fail unless staging_repo is an existing private dataset that is not production."""
    if not staging_repo or not staging_repo.strip():
        raise RuntimeError("STAGING_REPO is required to keep the result outside the ephemeral job container")
    if _norm_repo(staging_repo) == _norm_repo(prod_repo):
        raise RuntimeError(f"staging repo {staging_repo} is the production dataset; refusing")
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
    info = api.repo_info(staging_repo, repo_type="dataset")
    if info.private is not True:
        raise RuntimeError(f"staging repo {staging_repo} is not private; refusing to upload")


def stage_upload(db_path: str, before_path: str, staging_repo: str, prod_repo: str, run_id: str, api=None) -> str:
    """Upload the staged DB + snapshot to runs/<run_id>/ of the private staging repo, in one commit."""
    _check_run_id(run_id)
    for path in (db_path, before_path):
        if not os.path.isfile(path):
            raise RuntimeError(f"cannot stage missing file {path}")
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
    check_staging_repo(staging_repo, prod_repo, api)
    from huggingface_hub import CommitOperationAdd

    prefix = f"runs/{run_id}"
    api.create_commit(
        repo_id=staging_repo,
        repo_type="dataset",
        operations=[
            CommitOperationAdd(path_in_repo=f"{prefix}/{DB_FILENAME}", path_or_fileobj=db_path),
            CommitOperationAdd(path_in_repo=f"{prefix}/{BEFORE_FILENAME}", path_or_fileobj=before_path),
        ],
        commit_message=f"stage gpu-backfill {run_id}",
    )
    return prefix


def fetch_staged(staging_repo: str, prod_repo: str, run_id: str, dest_dir: str, api=None) -> tuple[str, str]:
    """Download runs/<run_id>/ files from the staging repo; refuse if absent or the DB hash differs from before.json."""
    _check_run_id(run_id)
    if _norm_repo(staging_repo) == _norm_repo(prod_repo):
        raise RuntimeError(f"staging repo {staging_repo} is the production dataset; refusing")
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=os.environ["HF_TOKEN"])
    paths = []
    for name in (DB_FILENAME, BEFORE_FILENAME):
        try:
            cached = api.hf_hub_download(
                repo_id=staging_repo, repo_type="dataset", filename=f"runs/{run_id}/{name}"
            )
        except Exception as exc:
            raise RuntimeError(f"staged file runs/{run_id}/{name} missing in {staging_repo}: {exc}") from exc
        dst = os.path.join(dest_dir, name)
        shutil.copyfile(cached, dst)
        paths.append(dst)
    with open(paths[1], encoding="utf-8") as f:
        want = json.load(f).get("sha256")
    if not want or sha256_file(paths[0]) != want:
        raise RuntimeError("staged rag.duckdb sha256 does not match before.json; refusing")
    return paths[0], paths[1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-cuda")
    s = sub.add_parser("snapshot")
    s.add_argument("db")
    s.add_argument("out")
    s.add_argument("--dataset-head", default=None)
    v = sub.add_parser("verify")
    v.add_argument("db")
    v.add_argument("before")
    e = sub.add_parser("effective-db")
    e.add_argument("db")
    c = sub.add_parser("stage-check")
    c.add_argument("--repo", required=True)
    c.add_argument("--prod-repo", required=True)
    g = sub.add_parser("stage-upload")
    g.add_argument("db")
    g.add_argument("before")
    g.add_argument("--repo", required=True)
    g.add_argument("--prod-repo", required=True)
    g.add_argument("--run-id", required=True)
    u = sub.add_parser("publish")
    u.add_argument("db", nargs="?")
    u.add_argument("before", nargs="?")
    u.add_argument("--staging-repo", default=None)
    u.add_argument("--run-id", default=None)
    u.add_argument("--repo", required=True)
    u.add_argument("--confirm", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.cmd == "check-cuda":
            check_cuda()
        elif a.cmd == "effective-db":
            print(f"EFFECTIVE DB OK: {assert_effective_db(a.db)}")
        elif a.cmd == "snapshot":
            snap = take_snapshot(a.db, a.out, a.dataset_head)
            print(f"SNAPSHOT: sha256={snap['sha256']} rows={snap['rows']} filings={snap['filings']}")
        elif a.cmd == "verify":
            after = verify_after(a.db, a.before)
            print(f"VERIFY OK: rows={after['rows']} filings={after['filings']}, no duplicate chunks")
        elif a.cmd == "stage-check":
            check_staging_repo(a.repo, a.prod_repo)
            print(f"STAGING REPO OK: {a.repo} is private and not production")
        elif a.cmd == "stage-upload":
            prefix = stage_upload(a.db, a.before, a.repo, a.prod_repo, a.run_id)
            print(f"STAGED to {a.repo}:{prefix}")
        elif a.staging_repo:
            if a.db or a.before or not a.run_id:
                raise RuntimeError("use either <db> <before> or --staging-repo with --run-id, not both")
            with tempfile.TemporaryDirectory(prefix="hf_fetch_") as tmp:
                os.chmod(tmp, 0o700)
                db, before = fetch_staged(a.staging_repo, a.repo, a.run_id, tmp)
                head = guarded_publish(db, before, a.repo, a.confirm)
            print(f"PUBLISHED on top of {head}")
        else:
            if not a.db or not a.before:
                raise RuntimeError("publish needs <db> <before> or --staging-repo with --run-id")
            head = guarded_publish(a.db, a.before, a.repo, a.confirm)
            print(f"PUBLISHED on top of {head}")
    except Exception as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
