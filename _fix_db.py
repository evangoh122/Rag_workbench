"""Download old working DB from HF dataset and re-upload it."""
import os
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download, HfApi

token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
api = HfApi(token=token)

# Download the old DB from the previous commit
print("Downloading old working DB from dataset...")
cached = hf_hub_download(
    repo_id="egoh33/Rag-workbench",
    filename="rag.duckdb",
    repo_type="dataset",
    token=token,
    revision="6b9ddf659faa",  # commit before our broken upload
)
print(f"Downloaded to: {cached}")

# Back up current local DB
local_db = Path("data/rag.duckdb")
backup = Path("data/rag.duckdb.bak")
shutil.copy2(local_db, backup)
print(f"Backed up local DB to {backup}")

# Copy old DB over local
shutil.copy2(cached, local_db)
print(f"Restored old DB to {local_db} ({local_db.stat().st_size / 1e6:.1f} MB)")

# Re-upload to HF dataset
print("Uploading old working DB to dataset...")
api.upload_file(
    path_or_fileobj=str(local_db),
    path_in_repo="rag.duckdb",
    repo_id="egoh33/Rag-workbench",
    repo_type="dataset",
    commit_message="revert: restore DuckDB 1.0.x compatible database",
)
print("Upload complete!")

# Restart the Space
print("Restarting HF Space...")
api.restart_space("egoh33/Auditable-Filing-QA")
print("Space restarted!")
