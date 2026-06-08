"""
sec_client.py — EDGAR data ingestion using edgartools and Polars.

Provides functions to download filings, extract XBRL facts as Polars DataFrames,
and chunk text sections for RAG.
"""
import os
import logging
from typing import List, Dict, Optional
import polars as pl
from edgar import Company, set_identity

logger = logging.getLogger(__name__)

def _ensure_identity():
    user_agent = os.getenv("EDGAR_USER_AGENT")
    if not user_agent:
        # For development, we might have a default or skip
        logger.warning("EDGAR_USER_AGENT not set. SEC API calls may fail.")
    else:
        set_identity(user_agent)

def get_latest_10k_facts(ticker: str) -> pl.DataFrame:
    """
    Download the latest 10-K for a ticker and extract XBRL facts into a Polars DataFrame.
    Columns: Concept, Value, Unit, Period
    """
    _ensure_identity()
    try:
        company = Company(ticker)
        filing = company.get_filing(form="10-K")
        financials = filing.financials
        
        if not financials:
            return pl.DataFrame()

        # Combine facts from all statements
        all_facts = []
        for statement in [financials.balance_sheet, financials.income_statement, financials.cash_flow_statement]:
            if statement is not None:
                # statement is an edgar.financials.Statement object
                df_pd = statement.to_pandas()
                # Convert to polars
                df_pl = pl.from_pandas(df_pd)
                all_facts.append(df_pl)
        
        if not all_facts:
            return pl.DataFrame()
            
        return pl.concat(all_facts, how="diagonal")
    except Exception as e:
        logger.error(f"Error fetching XBRL facts for {ticker}: {e}")
        return pl.DataFrame()

def chunk_filing_sections(ticker: str, accession_number: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Chunk the text sections of a 10-K filing.
    Returns a list of dictionaries with chunk_text and metadata.
    """
    _ensure_identity()
    try:
        company = Company(ticker)
        if accession_number:
            filing = company.get_filing(accession_number=accession_number)
        else:
            filing = company.get_filing(form="10-K")
            
        # Get sections using edgartools
        # edgartools supports getting sections for 10-K
        sections = filing.sections
        chunks = []
        
        for section_name in sections:
            try:
                text = filing.get_section(section_name)
                # Trivial chunking by paragraph or fixed size for this scaffold
                # In a real app, use a more sophisticated splitter
                section_chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
                for i, chunk in enumerate(section_chunks):
                    chunks.append({
                        "chunk_text": chunk,
                        "metadata": {
                            "section_name": section_name,
                            "accession_number": filing.accession_number,
                            "ticker": ticker,
                            "chunk_index": i
                        }
                    })
            except Exception as se:
                logger.warning(f"Could not extract section {section_name}: {se}")
                
        return chunks
    except Exception as e:
        logger.error(f"Error chunking filing for {ticker}: {e}")
        return []
