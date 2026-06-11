import os
from loguru import logger
from langchain_ollama import OllamaEmbeddings
from api.config import Config

_embeddings = None

def get_embeddings():
    """Get the singleton OllamaEmbeddings instance."""
    global _embeddings
    if _embeddings is None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # Strip trailing slash and /v1 suffix robustly
        base_url = base_url.rstrip("/").removesuffix("/v1")
        
        model = Config.EMBEDDING_MODEL
        logger.info(f"Initializing Ollama embeddings ({model}) at {base_url}...")
        
        try:
            _embeddings = OllamaEmbeddings(
                model=model,
                base_url=base_url,
            )
            # Verify connection with a test embed
            _embeddings.embed_query("test")
            logger.info("Ollama embeddings connection verified")
        except Exception as e:
            _embeddings = None
            logger.error(f"Failed to connect to Ollama at {base_url}: {e}")
            raise RuntimeError(
                f"Ollama not available at {base_url}. "
                "Ensure Ollama is running and {model} is pulled."
            ) from e
    return _embeddings
