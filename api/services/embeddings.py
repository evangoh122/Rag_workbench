import os
from loguru import logger
from langchain_ollama import OllamaEmbeddings
from api.config import Config

class PrefixedOllamaEmbeddings(OllamaEmbeddings):
    """OllamaEmbeddings wrapper that prepends a prefix to queries."""
    def embed_query(self, text: str) -> list[float]:
        prefix = Config.EMBEDDING_QUERY_PREFIX
        if prefix:
            text = f"{prefix}{text}"
        return super().embed_query(text)

_embeddings = None
_ollama_available = None  # None = not checked, True/False = checked


def is_ollama_available() -> bool:
    """Check if Ollama is reachable. Caches the result."""
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    try:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/").removesuffix("/v1")
        model = Config.EMBEDDING_MODEL
        test = PrefixedOllamaEmbeddings(model=model, base_url=base_url)
        test.embed_query("test")
        _ollama_available = True
        logger.info(f"Ollama available at {base_url}")
    except Exception as e:
        _ollama_available = False
        logger.warning(f"Ollama not available at {base_url}: {e}")
    return _ollama_available


def get_embeddings():
    """
    Get the singleton PrefixedOllamaEmbeddings instance.

    Returns None if Ollama is not available instead of raising.
    Callers should handle None and fall back to keyword-based retrieval.
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    if not is_ollama_available():
        return None

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    base_url = base_url.rstrip("/").removesuffix("/v1")
    model = Config.EMBEDDING_MODEL

    try:
        _embeddings = PrefixedOllamaEmbeddings(model=model, base_url=base_url)
        logger.info(f"Ollama embeddings initialized ({model})")
    except Exception as e:
        _embeddings = None
        logger.error(f"Failed to initialize Ollama embeddings: {e}")
        return None

    return _embeddings
