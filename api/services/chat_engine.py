import re
from typing import Optional, List, Dict, Any
import pandas as pd
from openai import OpenAI
from langsmith import traceable
from api.config import Config
from api.db.database import db_manager

SCHEMA = """
You have access to a DuckDB financial database with these tables:

SEC EDGAR financials:
- xbrl_facts(id, ticker, cik, concept, value, unit, period_end, period_start, form_type, accession, filed, fiscal_year, fiscal_period)
  * concept: bare concept name, NO prefix — e.g. 'Revenues', 'NetIncomeLoss', 'Assets'
  * value: DOUBLE in actual dollars (not thousands or millions)
  * period_end / period_start: TEXT in ISO-8601 format e.g. '2023-09-30'
  * fiscal_year: INTEGER e.g. 2023
  * fiscal_period: 'FY' for annual, 'Q1'/'Q2'/'Q3'/'Q4' for quarterly

Company metadata:
- ticker_embeddings(ticker, description, sector, industry)

Knowledge graph:
- graph_triples(id, subject, predicate, object, source_file, confidence)

Filing text:
- filing_chunks(id, ticker, cik, form_type, accession, chunk_index, chunk_text, filed)

Available tickers: AAPL, TSLA, MSFT

Confirmed concept names (present for AAPL, TSLA, MSFT):
  NetIncomeLoss, Assets, Liabilities, StockholdersEquity,
  OperatingIncomeLoss, GrossProfit, CostOfGoodsAndServicesSold,
  ResearchAndDevelopmentExpense, NetCashProvidedByUsedInOperatingActivities,
  CashAndCashEquivalentsAtCarryingValue, LongTermDebt,
  EarningsPerShareBasic, CommonStockSharesOutstanding,
  PaymentsToAcquirePropertyPlantAndEquipment

Note: 'Revenues' only exists for some tickers/years. For AAPL revenue,
use GrossProfit + CostOfGoodsAndServicesSold instead.

Notes:
- Use DuckDB SQL syntax.
- Dates stored as TEXT ISO-8601. Cast with ::DATE as needed.
- Always LIMIT to 100 rows unless asked for more.
- For latest annual data: WHERE fiscal_period = 'FY' ORDER BY fiscal_year DESC LIMIT 1.
"""

SYSTEM_PROMPT = f"""You are a financial data analyst assistant. The user will ask questions about their market data.

{SCHEMA}

Rules:
1. If the question requires data, respond with ONLY a valid DuckDB SQL query. No markdown, no explanation.
2. If the question is conversational or cannot be answered with SQL, respond with a plain English answer starting with "ANSWER:".
3. Never make up data. Only query what exists in the schema above.
4. Keep SQL readable and add brief inline comments for complex logic.
5. Only generate read-only SELECT or WITH queries.
"""

def get_sql_client(cfg: dict = None):
    if cfg is None:
        cfg = Config.get_provider_config()
    if Config.CHAT_PROVIDER == "anthropic":
        raise ValueError("Anthropic provider not supported for SQL mode. Use deepseek, openai, or ollama.")
    return OpenAI(api_key=cfg["api_key"] or "local", base_url=cfg["base_url"])

def clean_sql(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return text.strip().rstrip(";")

def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n\r]*", " ", sql)
    return sql.strip()

def validate_read_only_sql(sql: str) -> Optional[str]:
    compact = strip_sql_comments(sql)
    if not compact:
        return "The model did not return a SQL query."

    if len(compact) > 4096:
        return "Rejected overly long SQL statement."

    if compact.count(";") > 1:
        return "Rejected SQL with multiple statements."

    first = compact.lstrip().split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        return "Rejected SQL because only SELECT and WITH queries are allowed."

    blocked = {
        "alter", "attach", "call", "checkpoint", "copy", "create",
        "delete", "detach", "drop", "export", "from_csv", "glob",
        "httpfs", "import", "insert", "install", "load", "pragma",
        "read_blob", "read_csv", "read_csv_auto", "read_json",
        "read_parquet", "read_text", "set", "update", "vacuum",
        "sqlite_scan", "sqlite_attach", "postgres_scan",
        "postgres_attach", "mysql_scan", "mysql_attach",
        "information_schema",
    }
    tokens = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", compact.lower()))
    found = sorted(tokens & blocked)
    if found:
        return f"Rejected SQL containing blocked keyword/function: {', '.join(found)}."

    if re.search(r"\bduckdb_\w+\s*\(", compact.lower()):
        return "Rejected SQL referencing internal DuckDB functions."

    if re.search(r"\bduckdb_\w+\b", compact.lower()):
        return "Rejected SQL referencing internal DuckDB system tables/views."

    return None

@traceable(name="chat_summarise_results")
def summarise_results(question: str, df: pd.DataFrame) -> str:
    if df.empty:
        return "The query returned no results."
    
    cfg = Config.get_provider_config()
    client = OpenAI(api_key=cfg["api_key"] or "local", base_url=cfg["base_url"])
    
    # Simple column selection to avoid token limits
    cols = df.columns[:8] 
    preview = df[cols].head(5).to_markdown(index=False)
    
    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{
                "role": "user",
                "content": (
                    f'The user asked: "{question}"\n\n'
                    f"Query returned {len(df)} rows. Here are the first 5 rows (subset of columns):\n{preview}\n\n"
                    "Write a concise 1-2 sentence plain-English answer summarizing the findings. No markdown."
                ),
            }],
            temperature=0.3,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return f"Query returned {len(df)} rows."

@traceable(name="chat_engine")
def chat_sql(question: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    cfg = Config.get_provider_config()
    client = get_sql_client(cfg)
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
        )
        reply = response.choices[0].message.content.strip()
    except Exception:
        return {"type": "error", "answer": "Failed to generate a response. Please try again."}

    if reply.startswith("ANSWER:"):
        return {
            "type": "text",
            "answer": reply[len("ANSWER:"):].strip(),
        }

    sql = clean_sql(reply)
    validation_error = validate_read_only_sql(sql)
    if validation_error:
        return {"type": "error", "sql": sql, "answer": validation_error}

    try:
        conn = db_manager.get_connection()
        conn.execute("SET threads TO 2")
        conn.execute("SET memory_limit TO '256MB'")
        df = conn.execute(
            f"SELECT * FROM ({sql}) AS chat_result LIMIT ?", [100]
        ).df()
        conn.execute("RESET memory_limit")
        conn.execute("RESET threads")
        answer = summarise_results(question, df)
        return {
            "type": "table",
            "sql": sql,
            "data": df.to_dict(orient="records"),
            "answer": answer
        }
    except Exception:
        return {"type": "error", "answer": "Query execution failed. Please rephrase your question."}
