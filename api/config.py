import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the root directory
load_dotenv(Path(__file__).parent.parent / ".env")

class Config:
    DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")
    REVIEW_DB_PATH = os.getenv("REVIEW_DB_PATH", "./data/review_queue.duckdb")

    # ── LangSmith (tracing & observability) ──────────────────────────────────
    LANGSMITH_API_KEY: str | None = os.getenv("LANGSMITH_API_KEY") or None
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "rag-workbench")
    LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    # Phase 8: Drift alert thresholds
    DRIFT_AGREEMENT_FLOOR: float = float(os.getenv("DRIFT_AGREEMENT_FLOOR", "0.95"))
    DRIFT_CONCEPT_SPIKE_THRESHOLD: int = int(os.getenv("DRIFT_CONCEPT_SPIKE_THRESHOLD", "50"))
    
    # Provider Settings
    CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "deepseek").lower()
    CHAT_MODEL = os.getenv("CHAT_MODEL")
    
    # API Keys
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    # Embedding Settings
    EMBEDDING_MODEL = "models/text-embedding-004"
    EMBEDDING_DIM = 768

    @classmethod
    def get_provider_config(cls):
        providers = {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "default_model": "deepseek-chat",
                "api_key": cls.DEEPSEEK_API_KEY,
            },
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-4o",
                "api_key": cls.OPENAI_API_KEY,
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "default_model": "claude-sonnet-4-6",
                "api_key": cls.ANTHROPIC_API_KEY,
            },
            "ollama": {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                "default_model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                "api_key": "ollama",
            }
        }
        cfg = providers.get(cls.CHAT_PROVIDER, providers["deepseek"])
        return {
            "base_url": cfg["base_url"],
            "model": cls.CHAT_MODEL or cfg["default_model"],
            "api_key": cfg["api_key"],
        }


# ── LangSmith initialisation (runs once at import time) ───────────────────────
if Config.LANGSMITH_TRACING and Config.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = Config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = Config.LANGSMITH_PROJECT
