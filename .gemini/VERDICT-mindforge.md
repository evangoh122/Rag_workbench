# VERDICT — mindforge — Gemini — round 1
Status: APPROVED
Reviewed: api/services/guardrails/consensus_rails.py

## Findings
- [SEVERITY: minor] `api/services/guardrails/consensus_rails.py:152` — `timeout: float = float(os.getenv("CONSENSUS_TIMEOUT", "8.0"))` as a default argument means the timeout is evaluated and bound exactly once at module import time. If the environment variable changes during runtime, the timeout won't update. Also, if the env var is misconfigured as a non-float, the application will crash on startup (import time) rather than failing gracefully during the request. Consider moving the `getenv` call inside the function body.

## Notes
- `_normalise_numbers` and `_divergence` rely purely on standard string replacements and regex (`_NUMERIC`), effectively removing any risk of injection (no `eval()` or unsanitized code execution).
- The prompt is constructed using safe f-string interpolation and passed strictly as the `content` field in a messages array. This is robust against arbitrary code execution, and we rely on upstream `input_rails.py` to prevent prompt injection.

# VERDICT — mindforge — Gemini — round 7
Status: APPROVED
Reviewed: api/services/guardrails/input_rails.py, api/services/guardrails/dialog_rails.py, api/models/schemas.py, api/db/database.py

## Findings
- None

## Notes
- `needs_llm_check` gate in `input_rails.py` appropriately balances latency and security. Bypassing the MiMo analyzer for `len(message) <= 200` and single-line messages is a sound trade-off because known short-form attacks (like "ignore all previous instructions") are already robustly caught by the preceding regex and keyword layers. Novel, complex prompt injections almost exclusively rely on longer or multi-line structures to bypass those initial heuristic defenses.
- `_FINANCIAL_KEYWORD_RE` correctly uses `re.escape` and word boundaries (`\b`), mitigating regex injection risks and accurately solving the substring false positives.
- Input validation at the schema boundary (`max_length=1500` in `schemas.py`) properly matches the runtime limits in `input_rails.py`.
- Thread-safe DuckDB connection handling in `database.py` via `parent.cursor()` is a standard parallel processing pattern that isolates connections per thread without hitting file-lock limits.
