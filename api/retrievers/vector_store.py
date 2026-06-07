from typing import List
from langchain_core.documents import Document
from api.db.database import db_manager
from api.config import Config
from scripts.embed_tickers import _get_embeddings as get_embeddings
from loguru import logger

class VectorStoreRetriever:
    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def search(self, query: str, table_name: str = "ticker_embeddings") -> List[Document]:
        try:
            conn = db_manager.get_connection()
            embeddings = get_embeddings()
            qvec = embeddings.embed_query(query)

            rows = conn.execute(f"""
                SELECT ticker, text,
                       array_distance(embedding, ?::FLOAT[{Config.EMBEDDING_DIM}]) AS dist
                FROM {table_name}
                ORDER BY dist ASC
                LIMIT {self.top_k}
            """, [qvec]).fetchall()

            return [
                Document(
                    page_content=r[1],
                    metadata={"source": f"vector_search::{table_name}", "ticker": r[0], "distance": r[2]},
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Vector search failed for {table_name}: {e}")
            return []
