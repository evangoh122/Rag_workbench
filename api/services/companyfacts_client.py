import functools
import logging
import time
from typing import Optional, List, Any
import duckdb
from edgar import Company, set_identity
from api.config import Config

logger = logging.getLogger(__name__)

class CompanyFactsClient:
    HIGH_SIGNAL_CONCEPTS = {"NetIncomeLoss", "Revenue", "Assets", "Liabilities"}

    def __init__(self):
        """
        Initializes the EDGAR identity using the configured USER_AGENT.
        """
        if not Config.EDGAR_USER_AGENT:
            logger.warning("EDGAR_USER_AGENT not set. SEC requests may be blocked.")
        else:
            set_identity(Config.EDGAR_USER_AGENT)
            logger.info(f"CompanyFactsClient initialized with user agent: {Config.EDGAR_USER_AGENT}")
        
        self._init_db()

    def _init_db(self):
        """Ensures the edgar_facts table exists."""
        with duckdb.connect(Config.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edgar_facts (
                    ticker VARCHAR,
                    cik VARCHAR,
                    taxonomy VARCHAR,
                    concept VARCHAR,
                    label VARCHAR,
                    unit VARCHAR,
                    value DOUBLE,
                    period_start VARCHAR,
                    period_end VARCHAR,
                    form_type VARCHAR,
                    filed_date VARCHAR
                )
            """)

    @functools.lru_cache(maxsize=128)
    def _get_company_object(self, cik: str) -> Company:
        """Cached Company object to avoid redundant lookups."""
        return Company(cik)

    @functools.lru_cache(maxsize=128)
    def _get_company_facts_from_api(self, cik: str):
        """
        Fetches all facts for a company from the SEC API.
        Uses lru_cache to avoid repeated API calls for the same company.
        """
        # Implement rate limiting
        time.sleep(1.0 / Config.SEC_RATE_LIMIT)
        
        try:
            company = self._get_company_object(cik)
            facts = company.get_facts()
            if facts:
                return facts.get_all_facts()
            return []
        except Exception as e:
            logger.error(f"Error fetching facts for CIK {cik}: {e}")
            return []

    def get_fact(self, cik: str, concept: str, period_end: str) -> Optional[float]:
        """
        Gets a specific fact for a company.
        Tries local DuckDB first, then SEC API.
        """
        with duckdb.connect(Config.DB_PATH) as conn:
            # 1. Try DuckDB
            res = conn.execute("""
                SELECT value FROM edgar_facts 
                WHERE cik = ? AND concept = ? AND period_end = ?
                LIMIT 1
            """, [cik, concept, period_end]).fetchone()
            
            if res:
                return res[0]

            # 2. Try SEC API
            logger.info(f"Fact not found in DB, fetching from SEC API: CIK={cik}, Concept={concept}, PeriodEnd={period_end}")
            all_facts = self._get_company_facts_from_api(cik)
            
            try:
                company = self._get_company_object(cik)
                ticker = company.ticker
            except Exception:
                ticker = "UNKNOWN"

            found_value = None
            facts_to_ingest = []
            
            for fact in all_facts:
                is_target = fact.concept == concept and fact.period_end == period_end
                if is_target:
                    found_value = fact.numeric_value
                
                # Ingest if it's the requested fact OR a high-signal concept
                if is_target or (fact.taxonomy == "us-gaap" and fact.concept in self.HIGH_SIGNAL_CONCEPTS):
                    facts_to_ingest.append(fact)

            if facts_to_ingest:
                self._ingest_facts_bulk(conn, ticker, cik, facts_to_ingest)

            return found_value

    def _ingest_facts_bulk(self, conn: duckdb.DuckDBPyConnection, ticker: str, cik: str, facts: List[Any]):
        """Ingests facts into DuckDB using a bulk operation."""
        # Preparation for bulk insert: build a list of tuples
        data = [
            (ticker, cik, f.taxonomy, f.concept, f.label, f.unit, f.numeric_value, f.period_start, f.period_end, f.form_type, f.filing_date)
            for f in facts
        ]
        
        # Use a temporary table for deduped insertion
        conn.execute("CREATE TEMPORARY TABLE temp_facts AS SELECT * FROM edgar_facts WHERE FALSE")
        conn.executemany("INSERT INTO temp_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        
        # Insert only non-existent records
        conn.execute("""
            INSERT INTO edgar_facts 
            SELECT t.* FROM temp_facts t
            LEFT JOIN edgar_facts e ON 
                t.cik = e.cik AND t.concept = e.concept AND t.period_end = e.period_end AND t.value = e.value
            WHERE e.cik IS NULL
        """)
        conn.execute("DROP TABLE temp_facts")
