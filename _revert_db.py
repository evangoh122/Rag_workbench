"""Revert the HF dataset DB to the previous working version."""
import os
from huggingface_hub import HfApi

token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
api = HfApi(token=token)

# Revert rag.duckdb to the previous commit
print("Reverting rag.duckdb to previous version...")
api.revert_commit(
    repo_id="egoh33/Rag-workbench",
    repo_type="dataset",
    commit_id="5353b69850b3",  # our broken upload
)
print("Reverted!")

# Verify
info = api.repo_info("egoh33/Rag-workbench", repo_type="dataset")
for s in info.siblings:
    if s.rfilename == "rag.duckdb":
        print(f"rag.duckdb exists, size={s.size}")
