import duckdb
import threading
from .config import Config

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._conn = None
        return cls._instance

    def get_connection(self):
        if self._conn is None:
            # We open a persistent connection. 
            # Note: In a production web server, we might use a pool, 
            # but for DuckDB, a shared connection is often sufficient 
            # or we can open one per request if needed.
            # Using read_only=True for general queries as requested by standard practices.
            self._conn = duckdb.connect(Config.DB_PATH, read_only=True)
            try:
                self._conn.execute("LOAD vss")
            except Exception:
                pass
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

db_manager = DatabaseManager()
