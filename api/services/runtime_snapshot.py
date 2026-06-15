"""
runtime_snapshot.py — Persist the runtime/review DuckDB to the private HF dataset.

WHY: the HF Space runs on `cpu-basic` with no persistent volume (`storage: None`),
so `review_queue.duckdb` — audit_runs, HITL review_decisions/reviewer_verdicts,
calibration_history, eval_runs/eval_results, analytics_events — lives on the
ephemeral container disk and is wiped on every restart. To make it durable
WITHOUT paying for Space persistent storage, we snapshot the tables to Parquet
and push them to the private HF dataset (egoh33/Rag-workbench) under `runtime/`,
then restore them on boot.

Parquet (not a raw .duckdb copy) is deliberate: it is engine/version-agnostic, so
it also sidesteps the DuckDB storage-format mismatch between local (1.5.x) and the
Space (1.0.x). See memory `ops-duckdb-storage-format-mismatch`.

Cadence: a once-a-day background task (SNAPSHOT_INTERVAL_HOURS, default 24) plus a
best-effort snapshot on graceful shutdown. Worst-case loss on a hard kill is one
day of audit rows.

Safety: snapshot/restore only run on the Space (SPACE_ID set) or when
RUNTIME_SNAPSHOT_ENABLED=true, so local dev never auto-pushes its review DB.

Env:
  RUNTIME_SNAPSHOT_REPO     dataset repo id        (default: DB_DATASET_REPO or egoh33/Rag-workbench)
  RUNTIME_SNAPSHOT_ENABLED  force on/off           (default: on iff running on a Space)
  SNAPSHOT_INTERVAL_HOURS   periodic cadence       (default: 24)
  HF_TOKEN                  write token (required to upload to the private dataset)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from loguru import logger

from api.config import config

REPO = os.getenv("RUNTIME_SNAPSHOT_REPO") or os.getenv("DB_DATASET_REPO", "egoh33/Rag-workbench")
PREFIX = "runtime"  # dataset folder holding the per-table Parquet snapshots
# A freshly-created review DB is tiny; treat anything above this as "already has data".
_MIN_POPULATED_BYTES = 50_000


def _token() -> str | None:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None


def _on_space() -> bool:
    """True when running inside a HF Space (or explicitly forced)."""
    forced = os.getenv("RUNTIME_SNAPSHOT_ENABLED")
    if forced is not None:
        return forced.strip().lower() in ("1", "true", "yes", "on")
    return bool(os.getenv("SPACE_ID") or os.getenv("SPACE_HOST"))


def snapshot_enabled() -> bool:
    """Whether periodic/shutdown snapshots should run in this process."""
    return _on_space() and _token() is not None


def snapshot_review_db(*, reason: str = "periodic", force: bool = False) -> bool:
    """Export every review table to Parquet and upload to the private dataset in one commit.

    Best-effort: logs and returns False on any failure; never raises. Safe to call
    from a worker thread — it uses a fresh DuckDB cursor for the export so it does
    not contend with request-handler writes.

    `force=True` bypasses the on-Space guard (used by the admin/cron trigger, where
    the snapshot is explicitly requested) but still requires an HF token.
    """
    if not force and not _on_space():
        logger.info("[snapshot] not on a Space (and not forced) — skipping review-DB snapshot")
        return False
    token = _token()
    if not token:
        logger.info("[snapshot] no HF token — skipping review-DB snapshot")
        return False
    try:
        from huggingface_hub import CommitOperationAdd, HfApi

        from api.db.database import db_manager

        # cursor() shares the database but is an independent connection, so the
        # read-only COPY does not clash with concurrent audit writes.
        cur = db_manager.get_review_connection().cursor()
        tables = [r[0] for r in cur.execute("SHOW TABLES").fetchall()]
        if not tables:
            logger.info("[snapshot] review DB has no tables — nothing to snapshot")
            return False

        ops = []
        with tempfile.TemporaryDirectory() as td:
            for t in tables:
                fp = Path(td) / f"{t}.parquet"
                cur.execute(
                    f'COPY (SELECT * FROM "{t}") TO \'{fp.as_posix()}\' (FORMAT PARQUET)'
                )
                ops.append(
                    CommitOperationAdd(
                        path_in_repo=f"{PREFIX}/{t}.parquet",
                        path_or_fileobj=str(fp),
                    )
                )
            HfApi(token=token).create_commit(
                repo_id=REPO,
                repo_type="dataset",
                operations=ops,
                commit_message=f"runtime snapshot ({reason}): {len(tables)} tables",
            )
        logger.info(
            "[snapshot] uploaded {} review table(s) to {}/{} (reason={})",
            len(tables), REPO, PREFIX, reason,
        )
        return True
    except Exception as e:  # noqa: BLE001 — durability snapshot must never crash the app
        logger.error("[snapshot] review-DB snapshot failed (non-fatal): {}", e)
        return False


def restore_review_db() -> bool:
    """Restore review tables from the private dataset's Parquet snapshots on boot.

    Skips if the review DB is already populated (warm restart) so a stale snapshot
    never clobbers newer in-container data. Best-effort: never raises.
    """
    if not _on_space():
        logger.info("[restore] not on a Space (and not forced) — skipping review-DB restore")
        return False
    token = _token()
    if not token:
        logger.info("[restore] no HF token — skipping review-DB restore")
        return False

    db_path = config.REVIEW_DB_PATH
    if os.path.exists(db_path) and os.path.getsize(db_path) > _MIN_POPULATED_BYTES:
        logger.info(
            "[restore] review DB already populated at {} ({:.0f} KB) — skipping restore",
            db_path, os.path.getsize(db_path) / 1e3,
        )
        return False

    try:
        import duckdb
        from huggingface_hub import HfApi, hf_hub_download

        api = HfApi(token=token)
        files = [
            f for f in api.list_repo_files(REPO, repo_type="dataset")
            if f.startswith(f"{PREFIX}/") and f.endswith(".parquet")
        ]
        if not files:
            logger.info("[restore] no runtime snapshot found in {}/{} — starting fresh", REPO, PREFIX)
            return False

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = duckdb.connect(db_path)
        try:
            for f in files:
                local = hf_hub_download(repo_id=REPO, filename=f, repo_type="dataset", token=token)
                table = Path(f).stem
                conn.execute(
                    f'CREATE OR REPLACE TABLE "{table}" AS '
                    f"SELECT * FROM read_parquet('{Path(local).as_posix()}')"
                )
            # init_review_tables (run later when the app opens the connection) will
            # re-create the CREATE INDEX IF NOT EXISTS helpers on these restored tables.
        finally:
            conn.close()
        logger.info("[restore] restored {} review table(s) from {}/{}", len(files), REPO, PREFIX)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("[restore] review-DB restore failed (non-fatal): {}", e)
        return False


if __name__ == "__main__":
    # Entry used by the container boot step (scripts.restore_review_db).
    restore_review_db()
