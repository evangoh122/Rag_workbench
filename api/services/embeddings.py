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


class HFInferenceEmbeddings:
    """
    Embeddings via HuggingFace InferenceClient (feature_extraction).
    Falls back to direct HTTP on routing errors (e.g. scaleway 403 on HF Spaces).
    """
    def __init__(self, model_name: str):
        self._model = model_name
        self._api_key = os.getenv("HF_TOKEN", "")
        self._url = f"https://api-inference.huggingface.co/models/{model_name}"
        self._client = None
        self._use_http_fallback = False
        logger.info(f"HFInferenceEmbeddings ready — model={model_name}")

    def _get_client(self):
        if self._client is None and not self._use_http_fallback:
            try:
                from huggingface_hub import InferenceClient
                self._client = InferenceClient(token=self._api_key)
            except ImportError:
                self._use_http_fallback = True
        return self._client

    def _embed(self, text: str) -> list[float]:
        import numpy as np
        client = self._get_client()
        if client is not None:
            try:
                result = client.feature_extraction(text, model=self._model)
            except Exception as e:
                logger.warning("InferenceClient failed ({}: {}) — falling back to direct HTTP", type(e).__name__, e)
                self._client = None
                self._use_http_fallback = True
                client = None
        if client is None:
            import requests
            resp = requests.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"inputs": text},
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
        arr = np.array(result)
        if arr.ndim == 2:
            arr = arr.mean(axis=0)
        elif arr.ndim == 1:
            pass
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        prefix = Config.EMBEDDING_QUERY_PREFIX
        if prefix:
            text = f"{prefix}{text}"
        return self._embed(text)


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
        logger.warning(f"Ollama not available: {e}")
    return _ollama_available


def get_embeddings():
    """
    Return the configured embeddings instance.

    EMBEDDING_PROVIDER controls which backend is used:
      - \"huggingface\" — HF Inference API (direct HTTP), model from HF_EMBEDDING_MODEL
      - \"ollama\"       (default) — local Ollama, model from OLLAMA_EMBED_MODEL
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    provider = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()

    if provider == "huggingface":
        model_name = os.getenv("HF_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
        try:
            _embeddings = HFInferenceEmbeddings(model_name)
            return _embeddings
        except Exception as e:
            logger.error(f"Failed to init HuggingFace embeddings '{model_name}': {e}")
            return None

    # default: ollama
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

    return _embeddings
