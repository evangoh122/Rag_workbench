# Compliance and Governance Review Document: RAG Workbench

## Document Purpose

This document is prepared for the internal Model Risk Management (MRM) committee, IT Security, and Compliance oversight groups. It details how the RAG Workbench aligns with modernized banking regulations (specifically SR 26-2) and outlines the technical controls implemented to mitigate model, operational, and security risks.

## 1. Regulatory Alignment (SR 26-2)

The Federal Reserve's SR 26-2 guidelines emphasize a risk-based, tailored approach to model risk management, focusing on materiality, independent challenge, and ongoing monitoring. The RAG Workbench is designed natively to satisfy these requirements.

### 1.1 Model Definition and Materiality Tiering
The system explicitly separates the non-deterministic components (LLM extraction) from deterministic components (Python math execution). By doing so, we isolate model risk to the extraction phase.

To manage this risk, the system employs a deterministic Confidence Scorer that routes outputs based on materiality and confidence:
- **AUTO Tier:** High-confidence extractions verified against XBRL ground truth. Approved for direct downstream use.
- **SAMPLED_REVIEW Tier:** Medium-confidence extractions. Approved for use but queued for asynchronous human review to monitor drift.
- **ESCALATE Tier:** Low-confidence extractions or instances where specific risk triggers are fired. Requires mandatory human override before downstream execution.

### 1.2 Independent Validation and Cross-Checking
The system does not rely on LLM self-evaluation. Instead, it utilizes an independent `xbrl_cross_validator.py` service. This service fetches authoritative XBRL data directly from the SEC EDGAR database and programmatically compares the LLM's extracted figures against the regulatory ground truth. If a mismatch occurs, the confidence score is automatically reduced to zero, and the record is escalated.

### 1.3 Ongoing Monitoring and Drift Detection
In compliance with SR 26-2's requirement for continuous monitoring, the system includes a built-in drift detection module (`drift_detection.py`). This module monitors the rolling agreement rate between the automated system and the XBRL ground truth. If the agreement rate falls below the defined compliance floor (e.g., 95%), an alert is triggered, signaling the need for model recalibration.

## 2. Guardrails and Security Controls

To mitigate operational and security risks associated with generative AI, the RAG Workbench implements a comprehensive 5-rail NeMo Guardrails architecture.

| Rail Type | Purpose | Implementation Mechanism |
|---|---|---|
| **Input Rails** | Prevent prompt injection and jailbreaking | Regex and heuristic checks intercept malicious inputs before they reach the LLM. |
| **Dialog Rails** | Maintain conversational boundaries | Detects off-topic queries (e.g., non-financial requests) and gracefully refuses to process them. |
| **Retrieval Rails** | Ensure data relevance and minimize context poisoning | Evaluates retrieved chunks from the vector database and discards irrelevant context prior to generation. |
| **Execution Rails** | Enforce safe operational boundaries | Restricts SQL generation to read-only queries against specific tables, blocking access to system schema. |
| **Output Rails** | Prevent hallucination and data leakage | Masks Personally Identifiable Information (PII) and detects system prompt leakage in the final output. |

## 3. Data Integrity and Auditability

For a system to be used in credit risk and financial advisory, the audit trail must be immutable and transparent.

### 3.1 Provenance Tracking
Every data point extracted by the system is tagged with a provenance marker (`XBRL`, `STRUCTURED_TABLE`, or `NARRATIVE_LLM`). This allows analysts and auditors to trace any generated figure back to its exact source within the SEC filing.

### 3.2 Deterministic Execution
The system strictly prohibits the LLM from performing mathematical calculations. All extracted figures are passed to a deterministic Python Math Node. This ensures that financial ratios (e.g., Free Cash Flow, EBITDA) are calculated consistently and accurately every time, eliminating the risk of LLM mathematical hallucinations.

## 4. Shadow Deployment and Calibration

Prior to full production rollout, the system supports a "Shadow Deployment" mode. In this mode, the system processes historical filings without executing any downstream actions. The results are used to generate a calibration report, allowing the MRM committee to empirically determine the appropriate threshold cut-points for the AUTO, SAMPLED_REVIEW, and ESCALATE tiers based on actual performance data rather than theoretical assumptions.

## Conclusion

The RAG Workbench provides a robust, auditable, and compliant framework for integrating generative AI into the bank's financial analysis workflows. By enforcing strict provenance tracking, deterministic math execution, and a multi-tiered routing system aligned with SR 26-2, the system mitigates the inherent risks of LLMs while unlocking significant operational efficiencies.
