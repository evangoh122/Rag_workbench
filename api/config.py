import os
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Load .env from the root directory
load_dotenv(Path(__file__).parent.parent / ".env")


def _validate_db_path(path: str) -> str:
    """Validate DB_PATH is within the project directory (prevent path traversal)."""
    if not path or not path.strip():
        logger.warning("DB_PATH is empty, falling back to default.")
        return str(Path(__file__).parent.parent / "data" / "rag.duckdb")
    resolved = Path(path).resolve()
    project_root = Path(__file__).parent.parent.resolve()
    if not str(resolved).startswith(str(project_root)):
        logger.warning(f"DB_PATH '{path}' is outside project root. Falling back to default.")
        return str(project_root / "data" / "rag.duckdb")
    return str(resolved)


class Config:
    DB_PATH = _validate_db_path(os.getenv("DB_PATH", "./data/rag.duckdb"))
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
    MIMO_API_KEY = os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_API_KEY")

    # Embedding Settings
    EMBEDDING_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
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
                "base_url": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
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
            },
            "mimo": {
                "base_url": os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"),
                "default_model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
                "api_key": cls.MIMO_API_KEY,
            },
        }

        if cls.CHAT_PROVIDER not in providers:
            logger.warning(f"Unknown CHAT_PROVIDER '{cls.CHAT_PROVIDER}', falling back to deepseek")
            return providers["deepseek"]

        cfg = providers[cls.CHAT_PROVIDER]

        if not cfg.get("api_key"):
            logger.warning(f"No API key set for provider '{cls.CHAT_PROVIDER}'")

        return {
            "base_url": cfg["base_url"],
            "model": cls.CHAT_MODEL or cfg["default_model"],
            "api_key": cfg["api_key"],
        }


# ── Startup validation ───────────────────────────────────────────────────────
def _validate_startup():
    """Warn on missing but recommended env vars."""
    if not Config.DEEPSEEK_API_KEY and Config.CHAT_PROVIDER == "deepseek":
        logger.warning("DEEPSEEK_API_KEY not set — deepseek provider will fail")
    if not Config.GOOGLE_API_KEY and Config.CHAT_PROVIDER not in ("ollama", "mimo"):
        logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set — embeddings may fail")


_validate_startup()

# ── LangSmith initialisation (runs once at import time) ───────────────────────
if Config.LANGSMITH_TRACING and Config.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = Config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = Config.LANGSMITH_PROJECT
