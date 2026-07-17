# Jobs-to-Be-Done (JTBD) Framework: RAG Workbench

## Executive Summary

The RAG Workbench is designed to serve financial analysts, credit risk officers, and compliance teams within a banking environment. By applying the Jobs-to-Be-Done (JTBD) framework, we shift the focus from the technical features of the Retrieval-Augmented Generation system to the core objectives our users are trying to achieve. This framework identifies the functional, emotional, and social jobs that drive adoption, providing a foundation for product strategy and feature prioritization.

## Primary Functional Jobs

Functional jobs represent the practical, objective tasks users are attempting to complete. In the context of corporate banking and risk management, these jobs center around data extraction, verification, and analysis.

| Job Statement | Current Approach | RAG Workbench Solution | Outcome Metric |
|---|---|---|---|
| Extract verified financial figures from complex regulatory filings | Manual review of SEC EDGAR documents | Automated extraction with XBRL cross-validation | Reduce time spent gathering data by 80% |
| Calculate standard financial ratios for credit assessment | Manual data entry into Excel models | Deterministic math node applying formulas to extracted data | Eliminate calculation errors |
| Verify the provenance of AI-generated answers | Spot-checking outputs against source documents | End-to-end audit trails linking answers to specific filing chunks | Increase confidence in automated outputs |
| Identify material changes in company risk profiles | Comparing historical filings manually | Knowledge graph queries detecting entity relationship shifts | Accelerate risk identification |

## Secondary Functional Jobs

These jobs support the primary objectives and are often performed by management or compliance oversight teams rather than frontline analysts.

| Job Statement | Current Approach | RAG Workbench Solution | Outcome Metric |
|---|---|---|---|
| Monitor the reliability of automated analysis tools | Periodic manual audits of system outputs | Real-time metrics dashboard tracking agreement rates | Maintain >95% human agreement rate |
| Provide feedback to improve system accuracy | Ad-hoc reporting of errors | Integrated Human-in-the-Loop (HITL) review queue | Decrease unrecognized concept drift |
| Ensure compliance with model risk management standards | Manual documentation of model behavior | Deterministic routing and always-escalate triggers | Achieve 100% compliance with SR 26-2 guidelines |

## Emotional Jobs

Emotional jobs describe how users want to feel or avoid feeling while executing their functional jobs. In banking, emotional drivers are strongly tied to risk aversion and professional confidence.

**Feel confident in the accuracy of financial analysis**
Analysts experience significant anxiety when relying on automated tools for high-stakes credit decisions. The RAG Workbench addresses this by providing explicit provenance tags (e.g., `XBRL`, `STRUCTURED_TABLE`) and deterministic math execution, allowing analysts to feel secure that their recommendations are based on verified data rather than LLM hallucinations.

**Avoid the anxiety of regulatory non-compliance**
Compliance officers need assurance that automated systems operate within safe boundaries. The implementation of NeMo Guardrails (input, dialog, retrieval, execution, and output rails) ensures that the system will gracefully abstain or escalate when uncertain, reducing the stress associated with potential regulatory breaches.

## Social Jobs

Social jobs relate to how users want to be perceived by their peers, managers, or clients.

**Be perceived as a strategic advisor rather than a data gatherer**
By automating the tedious extraction and calculation phases of financial analysis, the RAG Workbench allows analysts to focus on interpreting the data and providing strategic insights. This elevates their role within the bank from tactical execution to strategic advisory.

**Demonstrate technological leadership within the institution**
For product owners and innovation leaders, successfully deploying a compliant, auditable AI system demonstrates forward-thinking leadership. The system's alignment with modernized model risk management standards (SR 26-2) showcases an ability to balance innovation with rigorous risk control.

## Desired Outcomes

Outcome-driven innovation requires defining the specific metrics users use to measure success when executing a job.

| Outcome Statement | Direction | Metric | Target |
|---|---|---|---|
| Minimize the time required to verify an AI-generated financial figure | Decrease | Verification time | < 30 seconds per figure |
| Maximize the percentage of automated extractions that match XBRL ground truth | Increase | Agreement rate | > 95% |
| Minimize the occurrence of unflagged LLM hallucinations in final reports | Decrease | Hallucination rate | 0% (Zero tolerance) |
| Maximize the speed of identifying out-of-range financial anomalies | Increase | Detection speed | Real-time during extraction |
