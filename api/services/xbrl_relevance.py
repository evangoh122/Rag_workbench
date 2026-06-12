"""
xbrl_relevance.py — Maps XBRL concepts to financial topic groups and filters
relevant facts by query intent. Returns max 8 facts for contextual display.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

ConceptGroup = str
ConceptName = str


def _to_float(value: Any) -> float | None:
    """Safely cast an XBRL value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

CONCEPT_GROUP_MAP: Dict[ConceptName, ConceptGroup] = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    "SalesRevenueGoodsNet": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    "NetIncomeLoss": "profitability",
    "GrossProfit": "profitability",
    "OperatingIncomeLoss": "profitability",
    "EarningsPerShareBasic": "profitability",
    "EarningsPerShareDiluted": "profitability",
    "CostOfGoodsAndServicesSold": "profitability",
    "CostOfRevenue": "profitability",
    "ResearchAndDevelopmentExpense": "profitability",
    "SellingGeneralAndAdministrativeExpense": "profitability",
    "OperatingExpenses": "profitability",
    "InterestExpense": "profitability",
    "IncomeTaxExpenseBenefit": "profitability",
    "Assets": "leverage",
    "Liabilities": "leverage",
    "StockholdersEquity": "leverage",
    "LongTermDebt": "leverage",
    "LongTermDebtCurrent": "leverage",
    "LiabilitiesCurrent": "leverage",
    "AssetsCurrent": "leverage",
    "DebtInstrumentCarryingAmount": "leverage",
    "CashAndCashEquivalentsAtCarryingValue": "liquidity",
    "OperatingCashFlow": "liquidity",
    "NetCashProvidedByUsedInOperatingActivities": "liquidity",
    "NetCashProvidedByUsedInInvestingActivities": "liquidity",
    "NetCashProvidedByUsedInFinancingActivities": "liquidity",
    "PaymentsToAcquirePropertyPlantAndEquipment": "liquidity",
    "FreeCashFlow": "liquidity",
    "CommonStockSharesOutstanding": "valuation",
    "CommonStockSharesIssued": "valuation",
    "TreasuryStockSharesAcquired": "valuation",
    "MarketCapitalization": "valuation",
    "InterestIncomeExpenseNet": "banking",
    "ProvisionForLoanLeaseAndOtherLosses": "banking",
    "InvestmentIncomeNet": "banking",
    "LoansAndLeasesReceivableNetReportedAmount": "banking",
    "Deposits": "banking",
    "TradingAccountAssets": "banking",
}

QUERY_KEYWORD_TO_GROUP: Dict[str, ConceptGroup] = {
    "revenue": "revenue",
    "sales": "revenue",
    "top line": "revenue",
    "income": "profitability",
    "gross profit": "profitability",
    "gross margin": "profitability",
    "net income": "profitability",
    "profit": "profitability",
    "earnings": "profitability",
    "eps": "profitability",
    "operating income": "profitability",
    "operating margin": "profitability",
    "r&d": "profitability",
    "research": "profitability",
    "expense": "profitability",
    "cost": "profitability",
    "margin": "profitability",
    "debt": "leverage",
    "leverage": "leverage",
    "liability": "leverage",
    "equity": "leverage",
    "balance sheet": "leverage",
    "asset": "leverage",
    "cash": "liquidity",
    "liquidity": "liquidity",
    "free cash": "liquidity",
    "cash flow": "liquidity",
    "capex": "liquidity",
    "capital expenditure": "liquidity",
    "operating cash": "liquidity",
    "share": "valuation",
    "outstanding": "valuation",
    "market cap": "valuation",
    "loan": "banking",
    "deposit": "banking",
    "interest income": "banking",
    "net interest": "banking",
    "provision": "banking",
}

_DISPLAY_NAMES: Dict[str, str] = {
    "Revenues": "Revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "SalesRevenueNet": "Revenue",
    "SalesRevenueGoodsNet": "Revenue",
    "NetIncomeLoss": "Net Income",
    "GrossProfit": "Gross Profit",
    "OperatingIncomeLoss": "Operating Income",
    "EarningsPerShareBasic": "EPS (Basic)",
    "EarningsPerShareDiluted": "EPS (Diluted)",
    "CostOfGoodsAndServicesSold": "COGS",
    "CostOfRevenue": "Cost of Revenue",
    "ResearchAndDevelopmentExpense": "R&D Expense",
    "OperatingExpenses": "Operating Expenses",
    "InterestExpense": "Interest Expense",
    "Assets": "Total Assets",
    "Liabilities": "Total Liabilities",
    "StockholdersEquity": "Shareholders' Equity",
    "LongTermDebt": "Long-Term Debt",
    "CashAndCashEquivalentsAtCarryingValue": "Cash & Equivalents",
    "NetCashProvidedByUsedInOperatingActivities": "Operating Cash Flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "CapEx",
    "CommonStockSharesOutstanding": "Shares Outstanding",
}


def _classify_query(query: str) -> ConceptGroup:
    """Map a natural-language query to a concept group via keyword matching.
    Accumulates all matched groups and picks the most-represented one."""
    q = query.lower()
    groups: list[ConceptGroup] = []
    for keyword, group in sorted(QUERY_KEYWORD_TO_GROUP.items(),
                                 key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(keyword) + r"\b", q, re.IGNORECASE):
            groups.append(group)
    if not groups:
        return "profitability"
    return Counter(groups).most_common(1)[0][0]


def _rank_facts(facts: List[Dict], primary_group: ConceptGroup, top_n: int = 8) -> List[Dict]:
    """
    Rank and filter XBRL facts to a maximum of top_n records.
    Facts matching the primary concept group get priority,
    followed by complementary groups (liquidity / leverage / profitability).
    """
    if not facts:
        return []

    ranked: List[Tuple[int, Dict]] = []
    secondary_order = {
        "revenue":       ["revenue", "profitability", "liquidity", "leverage"],
        "profitability": ["profitability", "revenue", "liquidity", "leverage"],
        "liquidity":     ["liquidity", "profitability", "leverage", "revenue"],
        "leverage":      ["leverage", "liquidity", "profitability", "revenue"],
        "valuation":     ["valuation", "profitability", "revenue", "liquidity"],
        "banking":       ["banking", "profitability", "liquidity", "leverage"],
    }
    group_priority = secondary_order.get(primary_group,
                                         [primary_group, "profitability", "revenue", "liquidity"])
    group_rank = {g: i for i, g in enumerate(group_priority)}

    for f in facts:
        concept = f.get("concept", "") or f.get("label", "")
        group = CONCEPT_GROUP_MAP.get(concept, "other")
        rank = group_rank.get(group, 99)
        value = f.get("value") or f.get("val")
        has_value = value is not None and str(value).strip() != ""
        if not has_value:
            rank += 50
        ranked.append((rank, f))

    ranked.sort(key=lambda x: (x[0], -(abs(_to_float(x[1].get("value") or x[1].get("val")) or 0))))
    return [f for _, f in ranked[:top_n]]


def get_relevant_facts(query: str, all_facts: List[Dict[str, Any]],
                       max_facts: int = 8) -> Dict[str, Any]:
    """
    Return a structured summary of the most relevant XBRL facts for a query.

    Returns:
        {
            "relevant": List[Dict],   # Top matches (≤max_facts)
            "total": int,             # Total facts in the DB
            "group": str,             # Detected concept group
            "badge_text": str,        # e.g. "XBRL verified • 8 facts"
        }
    """
    if not all_facts:
        return {
            "relevant": [],
            "total": 0,
            "group": "none",
            "badge_text": "",
        }

    group = _classify_query(query)
    relevant = _rank_facts(all_facts, group, max_facts)

    badge_text = f"XBRL verified • {len(all_facts)} facts"
    if len(relevant) < len(all_facts):
        badge_text = f"XBRL verified • {len(relevant)} of {len(all_facts)} shown"

    return {
        "relevant": relevant,
        "total": len(all_facts),
        "group": group,
        "badge_text": badge_text,
    }


def format_fact_for_display(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a fact dict for frontend consumption."""
    concept = fact.get("concept", "") or fact.get("label", "")
    value = fact.get("value") or fact.get("val")
    unit = fact.get("unit", "")
    period = fact.get("period_end", "") or fact.get("period", "")
    label = fact.get("label", "") or _DISPLAY_NAMES.get(concept, concept)
    num = _to_float(value)

    return {
        "concept": concept,
        "label": label,
        "value": num,
        "unit": unit,
        "period": period,
        "is_verified": num is not None,
    }
