"""
restore_review_db.py — Boot step: restore the runtime/review DuckDB from the
private HF dataset's Parquet snapshots before uvicorn opens the connection.

Runs in the container entrypoint after fetch_db_from_dataset.py. Best-effort: if
there is no snapshot, no token, or any error, it logs and exits 0 so the app
still starts with a fresh (empty) review DB. See api/services/runtime_snapshot.py.
"""
from __future__ import annotations

from api.services.runtime_snapshot import restore_review_db

if __name__ == "__main__":
    restore_review_db()
