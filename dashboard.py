"""
dashboard.py
RAG Workbench — Chat dashboard (Streamlit).

Single-page chat interface supporting:
  - Database (SQL) mode — text-to-SQL via chat_engine
  - Knowledge Base (RAG) mode — semantic search via rag_engine
"""

import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*urllib3.*match a supported version")

import duckdb
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from loguru import logger

load_dotenv(Path(__file__).parent / ".env")

from chat_engine import chat as _chat
from rag_engine import ask_rag

DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RAG Workbench",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme colours ─────────────────────────────────────────────────────────────
CLR_BG     = "#0e1117"
CLR_CARD   = "#1c2130"
CLR_BORDER = "#2a3246"

st.markdown(
    f"""
<style>
  section[data-testid="stSidebar"] {{ background: #131926; }}
</style>
""",
    unsafe_allow_html=True,
)


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_conn():
    if not Path(DB_PATH).exists():
        return None
    return duckdb.connect(DB_PATH, read_only=True)


def q(sql: str, params=()) -> pd.DataFrame:
    conn = get_conn()
    if conn is None:
        return pd.DataFrame()
    try:
        return conn.execute(sql, list(params)).df()
    except Exception as e:
        logger.warning(f"Query failed: {e}\nSQL: {sql}")
        return pd.DataFrame()
    finally:
        conn.close()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 RAG Workbench")
    st.markdown("---")
    st.caption(f"DB: `{DB_PATH}`")
    provider = os.getenv("CHAT_PROVIDER", "deepseek").lower()
    st.caption(f"Provider: `{provider}`")
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Chat page
# ══════════════════════════════════════════════════════════════════════════════
st.title("💬 Chat with your financial data")

chat_mode = st.radio(
    "Chat Mode",
    ["Database (SQL)", "Knowledge Base (RAG)"],
    horizontal=True,
    help="Database mode generates SQL to query numerical data. RAG mode searches SEC filings and ticker descriptions.",
)

st.caption(
    f"Ask anything about your stocks, options, EDGAR financials, or Polygon history. Powered by {provider.title()}."
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_results" not in st.session_state:
    st.session_state.chat_results = []

# Check API key availability
if (
    not os.getenv("DEEPSEEK_API_KEY")
    and not os.getenv("OPENAI_API_KEY")
    and not os.getenv("ANTHROPIC_API_KEY")
    and not os.getenv("XIAOMI_API_KEY")
    and os.getenv("CHAT_PROVIDER", "ollama") not in ("ollama", "mimo")
):
    st.warning("⚠️  API key not set in .env for your chosen provider.")
    st.stop()

# ── Render existing conversation ───────────────────────────────────────────
for i, msg in enumerate(st.session_state.chat_history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and i // 2 < len(st.session_state.chat_results):
            result = st.session_state.chat_results[i // 2]
            if (
                result
                and result.get("type") == "table"
                and result.get("data") is not None
            ):
                with st.expander(f"📊 Query results ({len(result['data'])} rows)"):
                    if result.get("sql"):
                        st.code(result["sql"], language="sql")
                    st.dataframe(result["data"], use_container_width=True, hide_index=True)

# ── Input ──────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about your data… e.g. 'Show AAPL OHLCV for last 30 days'"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            if chat_mode == "Database (SQL)":
                result = _chat(
                    question=prompt,
                    history=st.session_state.chat_history[:-1],
                )
                answer = result["answer"]
            else:
                answer = ask_rag(prompt)
                result = {"type": "text", "sql": None, "data": None, "answer": answer}

        st.markdown(answer)

        if result.get("type") == "table" and result.get("data") is not None:
            with st.expander(f"📊 Query results ({len(result['data'])} rows)"):
                if result.get("sql"):
                    st.code(result["sql"], language="sql")
                st.dataframe(result["data"], use_container_width=True, hide_index=True)
        elif result.get("type") == "error":
            if result.get("sql"):
                st.code(result["sql"], language="sql")

    st.session_state.chat_history.append({"role": "assistant", "content": answer})
    st.session_state.chat_results.append(result)

# ── Example prompts ────────────────────────────────────────────────────────
if not st.session_state.chat_history:
    st.markdown("**Try asking:**")
    examples = [
        "Show me AAPL closing prices for the last 30 days",
        "Which 10 tickers have the highest average volume in polygon_bars?",
        "What was NVDA's revenue for the last 4 quarters?",
        "Show the latest ETL run status for each job type",
        "Which tickers have the widest bid-ask spreads right now?",
    ]
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        with col:
            if st.button(ex, use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": ex})
                st.rerun()

if st.button("🗑️ Clear chat", key="clear_chat"):
    st.session_state.chat_history = []
    st.session_state.chat_results = []
    st.rerun()
