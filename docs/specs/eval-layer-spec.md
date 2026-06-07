# Autonomous EDGAR Reader — Evaluation Layer Spec

## 0. Assumptions (correct these before building)

- The reader **ingests SEC filings** (10-K, 10-Q, 8-K, etc.) and **extracts structured records** — financial values, entities, dates, material events — possibly via multiple agents (classify → extract → cross-check).
- Stack assumed **Python** (standard for EDGAR/XBRL work). Translate interfaces if you're on JS/TS.
- The output that matters is an **extracted record** with fields, not just free-text summary. If your reader is summarization/Q&A-first, the validator in §4.1 changes shape (validate claims against source spans instead of fields) — flag this.

## 1. Core principle

Autonomy is an **evaluation problem**, not an automation problem. The reader already works when a human checks every output. The job here is to make it trustworthy *without* a human in every loop: define "good," route by risk, hard-stop on danger, measure, and detect when "good" silently drifts.

The EDGAR-specific unlock: **SEC XBRL data is free structured ground truth.** Most financial figures the reader extracts already have a correct, machine-readable answer published by the SEC. Use it for the golden set, for live cross-validation, and for confidence — instead of hand-labeling everything or trusting LLM self-reported confidence.

## 2. Architecture

```
filing ──> reader/agents ──> ExtractionResult
                                   │
                          ┌────────▼─────────┐
                          │   EVAL LAYER     │
                          │  (this spec)     │
                          ├──────────────────┤
                          │ 1. validate      │ → schema + semantic, is_valid + reason_code
                          │ 2. score conf.   │ → derived from provenance + XBRL cross-check
                          │ 3. check triggers│ → deterministic always-escalate
                          │ 4. route         │ → AUTO / SAMPLED_REVIEW / ESCALATE
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                      ▼
        act + log          act + queue sample        hold for human
                                   │                      │
                                   └──────► reviews ◄──────┘
                                              │
                                   metrics + drift + recalibration (§4.4–4.5)
```

The eval layer is a wrapper around whatever the reader emits. Keep it decoupled so the reader and the trust logic evolve independently.

## 3. Core data structures

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class Provenance(str, Enum):
    XBRL = "xbrl"                # tagged fact, deterministic
    STRUCTURED_TABLE = "table"   # parsed HTML/financial table
    NARRATIVE_LLM = "narrative"  # LLM-extracted from prose (lowest trust)

class ReasonCode(str, Enum):
    OK = "ok"
    MISSING_FIELD = "missing_field"
    BAD_TYPE = "bad_type"
    OUT_OF_RANGE = "out_of_range"
    IDENTITY_VIOLATION = "identity_violation"   # e.g. balance sheet doesn't balance
    XBRL_MISMATCH = "xbrl_mismatch"             # text extraction ≠ tagged fact
    UNKNOWN_CONCEPT = "unknown_concept"         # us-gaap tag not recognized
    REFERENTIAL = "referential"                 # CIK/accession/exhibit inconsistency
    NOVEL_FORM = "novel_form"

class Route(str, Enum):
    AUTO = "auto"
    SAMPLED_REVIEW = "sampled_review"
    ESCALATE = "escalate"

@dataclass
class ExtractedField:
    name: str                      # e.g. "Revenues", "CIK", "filing_date"
    value: Any
    provenance: Provenance
    concept: Optional[str] = None  # us-gaap concept if applicable
    source_span: Optional[str] = None  # text/locator for audit

@dataclass
class ExtractionResult:
    cik: str
    accession: str
    form_type: str
    period: Optional[str]
    fields: list[ExtractedField]

@dataclass
class ValidationResult:
    is_valid: bool
    reason_codes: list[ReasonCode] = field(default_factory=list)
    details: dict = field(default_factory=dict)   # per-field diagnostics

@dataclass
class Decision:
    route: Route
    confidence: float
    validation: ValidationResult
    triggers_fired: list[str] = field(default_factory=list)
```

## 4. The five components

### 4.1 Validation — define a "valid record"

Two layers, both returning into one `ValidationResult` (boolean + reason codes so failures are diagnosable, not just rejected).

**Schema layer**

- Required fields present for the form type (a 10-K record needs different fields than an 8-K).
- Types correct (dates parse, monetary values numeric, CIK is 10 digits, accession matches `\d{10}-\d{2}-\d{6}`).
- Units sane (XBRL reports units/scale — don't confuse thousands vs. actuals).

**Semantic layer (the part that earns trust)**

- **Accounting identities** as hard checks within tolerance: `Assets ≈ Liabilities + StockholdersEquity`; `GrossProfit ≈ Revenues − CostOfRevenue`; cash-flow subtotals tie. Violations → `IDENTITY_VIOLATION`.
- **Referential integrity:** CIK ↔ company name match; period dates consistent with the form's fiscal period; referenced exhibits exist.
- **Plausibility vs. the company's own history:** pull prior values from the `companyfacts` API (§5) and flag values > N std devs (or > X% YoY) from that company's distribution → `OUT_OF_RANGE`. This is far better than a global "ranges sane" heuristic because scale varies wildly across filers.

### 4.2 Confidence + routing (the key design decision)

**Do not trust LLM self-reported confidence.** Derive confidence from **provenance + cross-validation**, which is calibratable and meaningful for EDGAR:

```
if field.provenance == XBRL:                  base = 0.98   # deterministic
elif field.provenance == STRUCTURED_TABLE:    base = 0.85
elif field.provenance == NARRATIVE_LLM:       base = 0.55

# strongest single signal: does it agree with the tagged fact?
if xbrl_fact_exists(field.concept):
    confidence = 1.0 if matches(field.value, xbrl_fact) else 0.0   # mismatch = escalate
else:
    confidence = base
```

Record-level confidence = min (or a weighted aggregate) over fields, so one shaky figure pulls the whole record down.

**Bands** (cut points calibrated from the shadow run in §6, not vibes):

- **AUTO** (high): act, log decision + full provenance.
- **SAMPLED_REVIEW** (medium): act, but route a sample to a human review queue.
- **ESCALATE** (low, or any trigger in §4.3): hold for human.

### 4.3 Always-escalate triggers (deterministic — fire regardless of confidence)

EDGAR-specific list:

- Balance sheet fails the accounting identity (after unit normalization).
- Amended filing (`/A` suffix) or any restatement signal.
- 8-K material items: **1.03** (bankruptcy), **4.02** (non-reliance / restatement), **4.01** (auditor change), and any going-concern language.
- XBRL fact ≠ text extraction for the same concept (`XBRL_MISMATCH`).
- Unrecognized `us-gaap` concept / new taxonomy version (`UNKNOWN_CONCEPT`, `NOVEL_FORM`).
- Value > historical range for that company.
- Any extraction that **feeds a user-facing financial figure, alert, or downstream action** (money/decision-affecting).

Implement as a list of pure predicate functions over `ExtractionResult`; `triggers_fired` collects names for the audit log.

### 4.4 Metrics

- **Validator precision/recall** against a labeled golden set (§5). Recall on the "invalid" class matters most — a missed bad record is the failure mode.
- **Escalation rate** and **false-escalation rate** (too high = you've rebuilt the human-in-the-loop bottleneck; too low = silent corruption).
- **Human-agreement rate:** on sampled AUTO decisions, how often does the human agree? This is the headline trust metric. Target **>95%** on the AUTO tier before trusting it; below that, tighten thresholds or fix the agent.
- **Drift signals:** rolling agreement rate, input distribution (form types, sections, sizes, sectors), and count of unrecognized concepts.

### 4.5 Feedback loop + drift detection

Sampled human reviews become **new labels** → periodically re-check validator precision/recall and re-fit confidence cut points → surface when "good" has drifted.

**Drift, EDGAR-aware:** the `us-gaap` taxonomy updates annually and filers change tagging, so drift here is real and partly *dated*. **Lead with the human-agreement rate** as the drift alarm (a drop means quality fell), and treat escalation-rate movement as a *secondary, ambiguous* signal — escalation rate dropping could mean "got better," "inputs got easier," or "detector broke," so never alert on it alone. Alert when agreement drops below a floor OR unrecognized-concept count spikes (new taxonomy season).

## 5. Ground truth strategy (the EDGAR advantage)

You mostly don't have to hand-label:

- **`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`** — every tagged fact, historically, per company. Use for live cross-validation (§4.2), plausibility ranges (§4.1), and as automatic labels.
- **SEC Financial Statement Data Sets** (quarterly bulk XBRL) — bulk ground truth for batch evaluation.
- Hand-label only the **hard cases**: narrative-extracted fields with no XBRL equivalent (risk factors, 8-K events, qualitative items). The doc's "50–100 edge-case records" target applies *here*, not to the financials.

Respect SEC fair-access rules (declared User-Agent, ≤10 req/s).

## 6. Build order

1. **Data structures + reader adapter** (§3) — wrap current output into `ExtractionResult`. Nothing else works without this.
2. **Schema validator** (§4.1 layer 1) — cheap, catches the dumb failures first.
3. **XBRL cross-validation + companyfacts client** (§5) — unlocks both semantic validation and confidence.
4. **Semantic validator** (§4.1 layer 2) — identities, plausibility, referential.
5. **Confidence + routing + triggers** (§4.2–4.3).
6. **Shadow deployment:** run the whole layer over several years of historical filings *without acting*, compare to companyfacts. See where the error mass actually sits, then set the AUTO/SAMPLED/ESCALATE cut points just above it.
7. **Metrics dashboard** (§4.4).
8. **Review queue + feedback loop + drift alerts** (§4.5).

Phases 1–6 give a trustworthy, calibrated read-only system. 7–8 keep it trustworthy over time.

## 7. Open questions to resolve

- Does the reader output **structured extractions**, **summaries/Q&A**, or **both**? (Changes §4.1.)
- What's the **downstream action** an extraction can trigger? (Defines the highest-stakes always-escalate cases.)
- Which **forms** are in scope first? (10-K/10-Q lean heavily on XBRL ground truth; 8-K is narrative-heavy and needs more hand-labeling.)
- Is there a **human reviewer** available for the sampled queue, or is that you for now?

## 8. Prior art & positioning

Every individual layer of this project already exists. That's a feature, not a bug: it means the instinct is sound, there are shoulders to stand on, and effort should concentrate on the one layer that's actually differentiated.

### 8.1 The EDGAR reader is a solved problem — build on it, don't rebuild it

Mature, free, open-source options already do retrieval + structured extraction:

- **EdgarTools** (`dgunning/edgartools`, MIT) — turns any filing into typed Python objects, parses XBRL financials to DataFrames, supports all major form types. **Recommended foundation.**
- **edgar-crawler** (`lefterisloukas/edgar-crawler`) — extracts 10-K/10-Q/8-K item sections into clean JSON; peer-reviewed (WWW 2025).
- **sec-edgar-agentkit / sec-edgar-toolkit** — agent-oriented wrappers (LangChain/MCP) over the same data.
- **sec-api** — hosted, paid JSON API alternative.

**Action:** Wrap EdgarTools as the reader/extraction layer (it already gives you XBRL facts, which is also your ground truth). Do **not** write a parser. The build effort goes into §4 (the eval layer).

### 8.2 The eval/HITL framework is an established pattern, not a novel architecture

What §1–§5 describe is essentially the standard "human-in-the-loop guardrails" pattern that the LLMOps field (Galileo, Weights & Biases, Patronus, and many practitioner writeups) has converged on through 2025–26: confidence-band routing, deterministic always-escalate policy rules, sampled post-hoc review (~5–10% of auto-decisions) to catch drift, and feedback into scorer calibration. The canonical failure story in that literature is *exactly* ours — a confident, well-formatted agent decision based on stale/misread data that nobody caught for days.

The most-cited pitfall is also the one we already designed against: **naive LLM self-reported confidence collapses to ~0.5 for everything**, making routing useless. Our provenance + XBRL/identity cross-validation approach is the concrete fix.

### 8.3 So what's actually the contribution

Not architectural novelty — **synthesis and judgment**:

1. **Domain-specific ground truth as the calibration substrate.** Generic guardrail demos calibrate against vibes or hand labels. This uses XBRL facts, accounting identities, and COT reconciliation as free, authoritative ground truth. That's the part most portfolio projects can't show.
2. **Honest confidence derivation** (provenance + cross-check, not self-report).
3. **Multi-source integrity model** spanning extraction-heavy data (EDGAR) and clean-but-revisable data (CFTC COT) under one risk-tiered layer.

### 8.4 Timely framing for the hiring narrative

The **EU AI Act's August 2026 human-oversight requirements** turn "demonstrable human oversight of automated decisions" from nice-to-have engineering into a compliance requirement enterprises must meet. Position the framework as that capability, not as a demo — it reframes the project from "I built an agent" to "I built the governance layer enterprises are now legally required to have."

## 9. Positioning & product case study (for AI PM / product owner / business-data roles)

### 9.1 The business problem *you* solve (lead with this)

> **AI capability is now cheap and commoditized; trustworthy AI *deployment* is the bottleneck. Most AI projects die in the gap between a demo that works and a system the business can actually run unsupervised. I own that gap — I define what "good" means, set the policy for what gets automated versus escalated, and own the metrics that earn the organization's trust to let it run.**

The EDGAR/COT system is not the product. It is the worked example that proves you think this way.

### 9.2 The project, framed as a product case study

Tell it in this order — decisions and tradeoffs first, plumbing only if asked:

- **Problem / context:** A multi-agent pipeline produced great output *only because a human checked every result*. Human-in-the-loop was the actual quality system, and it doesn't scale. The business risk: an agent silently misreads an edge case and downstream logic executes flawlessly on bad data.
- **Reframe (the product insight):** Autonomy is an evaluation problem, not an automation problem. Building the workflow was engineering; designing how to *trust* it was product.
- **Key decisions & tradeoffs:**
    - *Why sampled review at all* — pure auto-proceed hides drift; pure human review destroys the ROI. The sampled tier buys observability at a controlled cost.
    - *Why escalate irreversible/high-cost actions regardless of confidence* — confidence is a probability, not a guarantee; the cost asymmetry justifies a deterministic override.
    - *Why not trust LLM self-reported confidence* — it collapses to ~0.5 and makes routing useless; derive trust from verifiable ground truth instead.
- **Success definition (how I'd know it works):** human-agreement rate on the auto tier above a set bar, false-escalation rate inside a band, and a drift alarm that fires before quality silently degrades.
- **What it demonstrates:** problem framing, risk/ROI tradeoff ownership, ability to define "done" and the metrics, and enough technical depth to hold a credible conversation with engineers.

### 9.3 Resume bullets — product-framed

- **Defined what "good" means for an autonomous AI workflow** — translated a fuzzy "can we trust this output?" question into explicit, measurable acceptance criteria, with diagnosable failure codes instead of opaque pass/fail.
- **Established a risk-tiered autonomy policy** (auto-proceed / sampled review / escalate) that traded automation ROI against operational risk, calibrated to business impact rather than raw model confidence.
- **Owned the governance rules** for irreversible and high-cost actions — deciding what must remain human regardless of AI confidence, and why.
- **Set the trust metrics and acceptance bar** (human-agreement rate, false-escalation rate, drift signals) and the feedback loop that keeps the system trustworthy as the underlying data shifts.

### 9.4 The honest gap to close

It's a personal PoC with no real users or ROI numbers, and PM/owner interviews press hard on business impact. Two fixes, in order of strength:

1. **Run one slice of the shadow deployment** so you can cite a real result — "at threshold X, false-escalation was Y%, agreement was Z%." One number beats a page of architecture.
2. If that's not feasible yet, frame the deliverable explicitly as a **reusable governance methodology** and let the judgment carry it.

## 10. Regulatory alignment (the bank-AI-team angle)

### 10.1 US — SR 11-7 (model risk management)

The Federal Reserve / OCC *Supervisory Guidance on Model Risk Management* (SR 11-7, 2011) is the cornerstone US model-governance standard. Its three pillars and how this project maps:

- **Sound model validation** → the §4.1 validation layer (schema + semantic checks, accounting identities) and the §4.4 metrics (precision/recall vs. a golden set) — effectively a validation report.
- **Ongoing monitoring** → §4.5 drift detection (agreement-rate-led, plus unrecognized-concept spikes).
- **Governance, policies, controls + "effective challenge"** → §4.2 risk-tiered routing and §4.3 always-escalate triggers — an explicit, documented policy for what the model may decide alone vs. what a human must challenge.

### 10.2 Singapore — MAS

MAS's approach has built up in layers:

- **FEAT Principles (2018)** — Fairness, Ethics, Accountability, Transparency for AI/data analytics in financial services.
- **Veritas Initiative (2020–2023)** — operationalised FEAT into an assessment Methodology and Toolkit.
- **Project MindForge (2023– )** — GenAI-focused governance work; AI Risk Management Operationalisation Handbook published March 2026.
- **Proposed Guidelines on AI Risk Management** — issued for consultation 13 Nov 2025, closed 31 Jan 2026, expected to be finalised in 2026 with a 12-month transition. Apply to **all FIs**, explicitly cover **Generative AI and AI agents**, and are **risk-based / proportionate**.

> **Status:** As of mid-2026 these Guidelines are *proposed*, not yet in force — framing as "built to a standard that is about to land" reads as ahead-of-the-curve.

MAS proposed Guidelines map to this framework:

- **Risk materiality assessment** → §4.2 risk-tiering (proportionate controls scaled to decision impact)
- **AI life-cycle controls** → validation (§4.1), diagnosable reason codes (§3), human-review tiers (§4.2–4.3)
- **Meaningful human oversight** → always-escalate triggers (§4.3) and sampled review (§4.4)
- **Independent pre-deployment review + post-deployment monitoring** → shadow-deployment calibration (§6) and drift monitoring (§4.5)
- **Documentation for reproducibility and auditability** → provenance on every extracted field + logged decision record per output
