import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
env_path = Path("D:/New folder (2)/Rag_workbench/.env")
load_dotenv(dotenv_path=env_path)

# Force the embedding provider to be "sentence-transformers" for local execution
os.environ["EMBEDDING_PROVIDER"] = "sentence-transformers"
os.environ["ST_EMBEDDING_MODEL"] = "Qwen/Qwen3-Embedding-0.6B"
os.environ["EMBEDDING_DIM"] = "1024"

# Use standard lxml parser warning filter for clean log output
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from scripts.bootstrap_db import bootstrap
from scripts.embed_edgar import run_embed_edgar_etl
from scripts.embed_tickers import run_embed_tickers_etl
from api.config import Config

missing_embeddings = ['NXPI', 'MPWR', 'SWKS', 'QRVO', 'TER', 'ENTG', 'ONTO', 'FORM', 'COHU', 'KLIC', 'ICHR', 'VECO', 'AEHR', 'ACLS', 'AMKR', 'RKLB']
missing_xbrl = ['MRVL', 'NXPI', 'MCHP', 'MPWR', 'SWKS', 'QRVO', 'AMAT', 'ONTO', 'FORM', 'COHU', 'VECO', 'AMKR', 'RKLB']

print("==========================================================")
print("STARTING INGESTION OF MISSING COMPANIES")
print("==========================================================")

print("\n[Step 1/4] Seeding missing XBRL facts from SEC EDGAR...")
try:
    bootstrap(missing_xbrl, Config.DB_PATH)
except Exception as e:
    print("Error during XBRL seeding:", e)

print("\n[Step 2/4] Seeding missing narrative/table embeddings from SEC EDGAR...")
try:
    chunks_stored = run_embed_edgar_etl(missing_embeddings)
    print(f"Successfully stored {chunks_stored} chunks in edgar_embeddings.")
except Exception as e:
    print("Error during filing embedding:", e)

print("\n[Step 3/4] Regenerating ticker summary embeddings...")
try:
    tickers_embedded = run_embed_tickers_etl()
    print(f"Ticker summary embeddings regenerated: {tickers_embedded}")
except Exception as e:
    print("Error during ticker summary embedding:", e)

print("\n[Step 4/4] Uploading updated DB to Hugging Face dataset...")
token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
if token:
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        repo_id = "egoh33/Rag-workbench"
        
        # Verify file exists and has size
        db_file = Path(Config.DB_PATH)
        if db_file.exists():
            print(f"Uploading {db_file.name} ({db_file.stat().st_size / 1e6:.1f} MB) to dataset {repo_id}...")
            api.upload_file(
                path_or_fileobj=str(db_file),
                path_in_repo="rag.duckdb",
                repo_id=repo_id,
                repo_type="dataset",
                commit_message="ETL: Ingest and embed missing 15 companies",
            )
            print("Database successfully uploaded to Hugging Face!")
        else:
            print("Error: local DB file not found, cannot upload.")
    except Exception as e:
        print("Error uploading to Hugging Face:", e)
else:
    print("Warning: HF_TOKEN not found in environment, skipping upload.")

print("\n==========================================================")
print("INGESTION WORKFLOW COMPLETE")
print("==========================================================")
