import duckdb
import threading
from api.config import Config

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._conn = None
                cls._instance._conn_lock = threading.Lock()
                cls._instance._review_conn = None
                cls._instance._review_conn_lock = threading.Lock()
        return cls._instance

    def get_connection(self):
        """Get or create the shared DuckDB connection (thread-safe).

        Opens the main DB in read-write mode so that graph_triples and other
        tables can be created on first access.  The VSS extension is loaded
        when available (required for vector-similarity search).
        """
        with self._conn_lock:
            if self._conn is None:
                # Open read-write so init scripts can create tables.
                self._conn = duckdb.connect(Config.DB_PATH)
                try:
                    self._conn.execute("LOAD vss")
                except (duckdb.IOException, Exception):
                    pass
                # Ensure graph_triples table exists (BUG-10 fix).
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS graph_triples (
                        id          VARCHAR PRIMARY KEY,
                        ticker      VARCHAR NOT NULL DEFAULT '',
                        subject     VARCHAR NOT NULL,
                        predicate   VARCHAR NOT NULL,
                        object      VARCHAR NOT NULL,
                        confidence  DOUBLE  DEFAULT 1.0,
                        source_file VARCHAR,
                        source_loc  VARCHAR
                    )
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_gt_ticker_subj
                    ON graph_triples (ticker, subject)
                """)
            return self._conn

    def get_review_connection(self):
        """Get or create the writable DuckDB connection for review queue tables (thread-safe).

        Uses a dedicated DB file so it does not conflict with the read-only main DB.
        Tables are initialised on first access via init_review_tables.
        """
        with self._review_conn_lock:
            if self._review_conn is None:
                self._review_conn = duckdb.connect(Config.REVIEW_DB_PATH)
                from api.db.review_queue import init_review_tables
                init_review_tables(self._review_conn)
            return self._review_conn

    def execute(self, sql: str, params=None):
        """Execute SQL with thread-safe access. Returns the cursor."""
        conn = self.get_connection()
        with self._conn_lock:
            if params:
                return conn.execute(sql, list(params))
            return conn.execute(sql)

    def close(self):
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None
        with self._review_conn_lock:
            if self._review_conn:
                self._review_conn.close()
                self._review_conn = None

db_manager = DatabaseManager()
