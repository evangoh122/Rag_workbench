import duckdb
import logging
import threading
from api.config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._conn = None
                cls._instance._conn_lock = threading.Lock()
        return cls._instance

    def get_connection(self):
        """Get or create the shared DuckDB connection (thread-safe)."""
        with self._conn_lock:
            if self._conn is None:
                self._conn = duckdb.connect(Config.DB_PATH, read_only=True)
                try:
                    self._conn.execute("LOAD vss")
                except Exception:
                    pass
            return self._conn

    def execute(self, sql: str, params=None):
        """Execute SQL with thread-safe access. Returns the cursor."""
        conn = self.get_connection()
        with self._conn_lock:
            if params:
                return conn.execute(sql, list(params))
            return conn.execute(sql)

    def lock(self):
        """Return the connection lock for external use."""
        return self._conn_lock

    def close(self):
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None

db_manager = DatabaseManager()
