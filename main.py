"""
main.py
RAG Workbench — embedding job entry point.

Ownership: Claude (Architecture)
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*urllib3.*match a supported version")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

_DEFAULT_TICKERS = (
    "AAPL,MSFT,NVDA,TSLA,AMZN,META,GOOGL,GOOG,JPM,BAC,"
    "GS,MS,WFC,AMD,INTC,QCOM,AVGO,MU,AMAT,V,MA,PYPL,"
    "JNJ,PFE,LLY,ABBV,MRK,XOM,CVX,OXY,NFLX,DIS"
)

TICKER_SYMBOLS = [
    s.strip()
    for s in os.getenv("EMBED_TICKERS", _DEFAULT_TICKERS).split(",")
    if s.strip()
]

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"),
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")


def main():
    parser = argparse.ArgumentParser(description="RAG Workbench — embedding jobs")
    parser.add_argument(
        "--job",
        choices=["embed-tickers", "embed-edgar"],
        required=True,
        help="embed-tickers: embed polygon ticker descriptions; embed-edgar: embed 10-K filings",
    )
    args = parser.parse_args()

    if args.job == "embed-tickers":
        from scripts.embed_tickers import run_embed_tickers_etl
        n = run_embed_tickers_etl()
        logger.info(f"Done — embedded {n} tickers")

    elif args.job == "embed-edgar":
        from scripts.embed_edgar import run_embed_edgar_etl
        logger.info(f"Processing {len(TICKER_SYMBOLS)} tickers: {', '.join(TICKER_SYMBOLS[:10])}{'…' if len(TICKER_SYMBOLS) > 10 else ''}")
        n = run_embed_edgar_etl(TICKER_SYMBOLS)
        logger.info(f"Done — stored {n} EDGAR chunks")


if __name__ == "__main__":
    main()
