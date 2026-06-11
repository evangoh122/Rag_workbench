import os
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv


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
    def __init__(self):
        # Load .env from the root directory
        load_dotenv(Path(__file__).parent.parent / ".env")
        self._db_path = None
        self._review_db_path = None

    @property
    def DB_PATH(self) -> str:
        if self._db_path is None:
            self._db_path = _validate_db_path(os.getenv("DB_PATH", "./data/rag.duckdb"))
        return self._db_path

    @property
    def REVIEW_DB_PATH(self) -> str:
        if self._review_db_path is None:
            self._review_db_path = os.getenv("REVIEW_DB_PATH", "./data/review_queue.duckdb")
        return self._review_db_path

    # ── LangSmith (tracing & observability) ──────────────────────────────────
    @property
    def LANGSMITH_API_KEY(self) -> str | None:
        return os.getenv("LANGSMITH_API_KEY") or None

    @property
    def LANGSMITH_PROJECT(self) -> str:
        return os.getenv("LANGSMITH_PROJECT", "rag-workbench")

    @property
    def LANGSMITH_TRACING(self) -> bool:
        return os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    # Phase 8: Drift alert thresholds
    @property
    def DRIFT_AGREEMENT_FLOOR(self) -> float:
        return float(os.getenv("DRIFT_AGREEMENT_FLOOR", "0.95"))

    @property
    def DRIFT_CONCEPT_SPIKE_THRESHOLD(self) -> int:
        return int(os.getenv("DRIFT_CONCEPT_SPIKE_THRESHOLD", "50"))

    # Provider Settings
    @property
    def CHAT_PROVIDER(self) -> str:
        return os.getenv("CHAT_PROVIDER", "deepseek").lower()

    @property
    def CHAT_MODEL(self) -> str | None:
        return os.getenv("CHAT_MODEL")

    # API Keys
    @property
    def DEEPSEEK_API_KEY(self) -> str | None:
        return os.getenv("DEEPSEEK_API_KEY")

    @property
    def OPENAI_API_KEY(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    @property
    def ANTHROPIC_API_KEY(self) -> str | None:
        return os.getenv("ANTHROPIC_API_KEY")

    @property
    def GOOGLE_API_KEY(self) -> str | None:
        return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    @property
    def MIMO_API_KEY(self) -> str | None:
        return os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_API_KEY")

    @property
    def POLYGON_API_KEY(self) -> str | None:
        return os.getenv("POLYGON_API_KEY") or None

    # MiMo reasoning model needs large token budget
    @property
    def MIMO_MAX_TOKENS(self) -> int:
        return int(os.getenv("MIMO_MAX_TOKENS", "16384"))

    @property
    def MIMO_TEMPERATURE(self) -> float:
        return float(os.getenv("MIMO_TEMPERATURE", "0.15"))

    # ── Reranker Settings ─────────────────────────────────────────────────────
    @property
    def RERANKER_MODEL(self) -> str:
        return os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    @property
    def RERANKER_TOP_K(self) -> int:
        return int(os.getenv("RERANKER_TOP_K", "5"))

    # Embedding Settings
    @property
    def EMBEDDING_MODEL(self) -> str:
        return os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    @property
    def EMBEDDING_QUERY_PREFIX(self) -> str:
        return os.getenv("EMBEDDING_QUERY_PREFIX", "")

    @property
    def EMBEDDING_DIM(self) -> int:
        return 768

    def get_provider_config(self):
        providers = {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "default_model": "deepseek-chat",
                "api_key": self.DEEPSEEK_API_KEY,
            },
            "openai": {
                "base_url": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
                "default_model": "gpt-4o",
                "api_key": self.OPENAI_API_KEY,
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "default_model": "claude-sonnet-4-6",
                "api_key": self.ANTHROPIC_API_KEY,
            },
            "ollama": {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                "default_model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                "api_key": "ollama",
            },
            "mimo": {
                "base_url": os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"),
                "default_model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
                "api_key": self.MIMO_API_KEY,
                "max_tokens": self.MIMO_MAX_TOKENS,
                "temperature": self.MIMO_TEMPERATURE,
            },
        }

        if self.CHAT_PROVIDER not in providers:
            logger.warning(f"Unknown CHAT_PROVIDER '{self.CHAT_PROVIDER}', falling back to deepseek")
            return providers["deepseek"]

        cfg = providers[self.CHAT_PROVIDER]

        if not cfg.get("api_key") and self.CHAT_PROVIDER != "ollama":
            logger.warning(f"No API key set for provider '{self.CHAT_PROVIDER}'")

        return {
            "base_url": cfg["base_url"],
            "model": self.CHAT_MODEL or cfg["default_model"],
            "api_key": cfg["api_key"],
        }

    def validate_startup(self):
        """Warn on missing but recommended env vars."""
        provider = self.CHAT_PROVIDER
        if provider == "deepseek" and not self.DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY not set — deepseek provider will fail")
        elif provider == "openai" and not self.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set — openai provider will fail")
        elif provider == "anthropic" and not self.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — anthropic provider will fail")
        elif provider == "mimo" and not self.MIMO_API_KEY:
            logger.warning("MIMO_API_KEY/XIAOMI_API_KEY not set — mimo provider will fail")

        if not self.GOOGLE_API_KEY and provider not in ("ollama", "mimo", "openai", "anthropic"):
            logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set — embeddings may fail if using default")

    def init_langsmith(self):
        """Initialise LangSmith if enabled."""
        if self.LANGSMITH_TRACING and self.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGSMITH_PROJECT


# Global instance
config = Config()

# Export 'Config' as the instance for backward compatibility with 'Config.ATTRIBUTE'
Config = config
