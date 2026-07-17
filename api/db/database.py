import duckdb
import threading
from api.config import Config
from api.db.review_queue import init_review_tables

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Return the process-wide database manager singleton."""
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
                self._conn = duckdb.connect(Config.DB_PATH)
                # Limit memory/CPU on constrained HF Spaces (prevents SIGSEGV).
                try:
                    self._conn.execute("SET memory_limit='1GB'")
                    self._conn.execute("SET threads=2")
                except Exception:
                    pass
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
                # Speed up /api/graph/triples ORDER BY confidence DESC
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_gt_ticker_confidence
                    ON graph_triples (ticker, confidence DESC)
                """)
                # Phase B: typed nodes + source-ref columns for the Evidence Graph.
                # Idempotent migration so existing DBs expose them to Phase C.
                for _stmt in (
                    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS subject_type VARCHAR",
                    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS object_type  VARCHAR",
                    "ALTER TABLE graph_triples ADD COLUMN IF NOT EXISTS chunk_id     VARCHAR",
                ):
                    try:
                        self._conn.execute(_stmt)
                    except Exception:
                        pass
                # Exact SEC fact provenance. Existing databases predate the
                # companyfacts `frame` field, so migrate them on first access.
                try:
                    self._conn.execute(
                        "ALTER TABLE xbrl_facts ADD COLUMN IF NOT EXISTS frame VARCHAR"
                    )
                except Exception:
                    # Some lightweight/test databases intentionally omit XBRL.
                    pass
            return self._conn

    def get_review_connection(self):
        """Get or create the writable DuckDB connection for review queue tables (thread-safe).

        Uses a dedicated DB file so it does not conflict with the read-only main DB.
        Tables are initialised on first access via init_review_tables.
        """
        with self._review_conn_lock:
            if self._review_conn is None:
                self._review_conn = duckdb.connect(Config.REVIEW_DB_PATH)
                init_review_tables(self._review_conn)
            return self._review_conn

    def get_new_review_connection(self):
        """Open a NEW, independent review-DB connection for a background thread.

        For background threads (e.g. the fire-and-forget consensus rail) that must
        not share the singleton connection object with request handlers. DuckDB
        connections are not safe to use concurrently across threads, so each thread
        gets its own handle.

        Returns ``self._review_conn.cursor()`` — an independent connection on the
        *same* underlying database instance — rather than a fresh
        ``duckdb.connect(REVIEW_DB_PATH)``. The singleton already holds the file
        open read-write, and DuckDB's file-level lock forbids a *second*
        ``connect()`` to the same file from the same process (see
        ``execute_readonly``). A second connect would raise, the consensus worker's
        fail-open try/except would swallow it, and audit persistence + review-queue
        escalation would silently never land. ``.cursor()`` shares the instance
        (same tables, no re-lock).

        Caller owns the connection and must close it; closing a cursor connection
        does not close the parent singleton.
        """
        # Ensure the singleton (and its table init) has run at least once so the
        # base tables exist before the cursor connection touches them.
        parent = self.get_review_connection()
        with self._review_conn_lock:
            return parent.cursor()

    def execute(self, sql: str, params=None):
        """Execute SQL with thread-safe access. Returns the cursor."""
        conn = self.get_connection()
        with self._conn_lock:
            if params:
                return conn.execute(sql, list(params))
            return conn.execute(sql)

    def execute_readonly(self, sql: str, params=None):
        """Execute SQL with thread-safe access (alias for execute).

        DuckDB's file-level locking prevents opening a second connection
        to the same DB file, so this uses the shared connection with the
        same lock. The name documents read-only intent for callers.
        """
        return self.execute(sql, params)

    def close(self):
        """Close and clear the shared main and review database connections."""
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None
        with self._review_conn_lock:
            if self._review_conn:
                self._review_conn.close()
                self._review_conn = None

db_manager = DatabaseManager()
