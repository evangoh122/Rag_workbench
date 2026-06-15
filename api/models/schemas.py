from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    ticker: Optional[str] = Field(default="NVDA", max_length=10)
    history: Optional[List[Dict[str, str]]] = Field(default=None, max_length=50)


# ── Structured Output Models ─────────────────────────────────────────────────

class SourceItem(BaseModel):
    """A retrieved source chunk with metadata. Matches frontend Source interface."""
    ticker: str = ""
    accession: str = ""
    section: str = ""
    text: str = ""
    edgar_url: str = ""
    distance: Optional[float] = None


class VerificationResult(BaseModel):
    """Verification status and reasoning."""
    status: str = "not_checked"  # PASS, FAIL, SKIPPED, ERROR, not_checked
    reasoning: str = ""


class PipelineStatus(BaseModel):
    """Status of each pipeline node."""
    input: str = "pending"
    retrieval: str = "pending"
    classifier: str = "pending"
    extraction: str = "pending"
    eval: str = "pending"
    math: str = "pending"
    verification: str = "pending"
    output: str = "pending"


class ChatResponse(BaseModel):
    """Structured response from all chat endpoints.

    All endpoints return this consistent shape. Fields not applicable
    to a given mode are omitted (None) rather than missing.
    """
    type: str = "text"  # "text", "table", "error"
    answer: str = ""

    # The company the query actually resolved to (may differ from the requested
    # ticker when the question names a different company). The UI persists this
    # so follow-ups stay grounded on the same company.
    ticker: str = ""

    # Retrieval sources
    sources: List[SourceItem] = Field(default_factory=list)

    # Financial data
    xbrl_facts: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_xbrl: List[Dict[str, Any]] = Field(default_factory=list)
    xbrl_badge: str = ""
    xbrl_group: str = ""
    polygon_data: List[Dict[str, Any]] = Field(default_factory=list)

    # Standard Response Framework — educational layers (sections 3–5).
    # Additive, display-only; empty when not applicable (abstention) or disabled.
    what_it_means: str = ""
    how_to_interpret: str = ""
    follow_ups: List[str] = Field(default_factory=list)

    # Verification
    verification: VerificationResult = Field(default_factory=VerificationResult)

    # Math / calculation trace
    math_steps: List[str] = Field(default_factory=list)

    # Pipeline status
    pipeline_status: PipelineStatus = Field(default_factory=PipelineStatus)

    # Graph RAG specific. Triples carry source refs + node types (Phase C) so
    # the Evidence Graph is auditable, so values are mixed (str + float).
    entities: List[str] = Field(default_factory=list)
    triples: List[Dict[str, Any]] = Field(default_factory=list)

    # Optional chart spec (recharts). Built deterministically from XBRL facts
    # when the LLM calls the charting tool — never from model-generated numbers.
    # Shape: {type, title, metric, unit, data:[{period, value}]}.
    chart: Optional[Dict[str, Any]] = None

    # SQL mode specific
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None

    # Confidence / eval
    confidence: Optional[float] = None
    eval_route: Optional[str] = None  # AUTO, SAMPLED_REVIEW, ESCALATE

    # Lineage / audit
    lineage: Optional[Dict[str, Any]] = None
