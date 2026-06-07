import logging
from edgar import set_identity
from api.config import Config

logger = logging.getLogger(__name__)

class CompanyFactsClient:
    def __init__(self):
        """
        Initializes the EDGAR identity using the configured USER_AGENT.
        """
        if not Config.EDGAR_USER_AGENT:
            logger.warning("EDGAR_USER_AGENT not set. SEC requests may be blocked.")
        else:
            set_identity(Config.EDGAR_USER_AGENT)
            logger.info(f"CompanyFactsClient initialized with user agent: {Config.EDGAR_USER_AGENT}")

    def get_fact(self, cik: str, concept: str, period_end: str):
        """
        Stub for getting a specific fact for a company.
        Currently just logs the request.
        
        Args:
            cik: Central Index Key for the company
            concept: XBRL concept (e.g., 'NetIncomeLoss')
            period_end: End date for the fact (YYYY-MM-DD)
        """
        logger.info(f"Fetching fact: CIK={cik}, Concept={concept}, PeriodEnd={period_end}")
        # In Phase 3, this will use edgartools to fetch actual XBRL facts.
        return None
