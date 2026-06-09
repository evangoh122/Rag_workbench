# Peer Review: Gemini (Security/UI) -> Claude (Routes) & DeepSeek (Services)

## Summary
The API wiring works but violates several security mandates. The frontend needs immediate hardening against potential XSS from untrusted LLM outputs.

## Findings

### 1. Missing Authentication/Rate Limiting
**File:** `api/routes/chat.py`
**Issue:** `/auditable-rag` and other chat endpoints are public and lack rate limiting.
**Recommendation:** Apply `@auth_required` and `@rate_limit` decorators (once implemented in middleware).

### 2. Input Validation
**File:** `api/routes/chat.py`
**Issue:** `ticker` is a string without validation.
**Recommendation:** Use a regex pattern or a set of allowed tickers to prevent injection or invalid requests.

### 3. XSS Risk (High Severity)
**File:** `frontend/src/App.tsx`
**Issue:** `ReactMarkdown` renders raw assistant responses.
**Recommendation:** Pass `disallowedElements={['script', 'iframe']}` and ensure `unwrapDisallowed` is set to true.
