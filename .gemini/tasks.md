# Orchestrator Task — 2026-06-07
Feature: Apply rate-limiting and auth to /api/health/db
Status: done

## Your Tasks
- [ ] Register rate-limit middleware for the /api/health/db endpoint in api/middleware/rate_limit.py
- [ ] Ensure the /api/health/db endpoint requires authentication in api/middleware/auth.py

## Files
- api/middleware/rate_limit.py
- api/middleware/auth.py

## Acceptance Criteria
- Unauthenticated request to GET /api/health/db returns 401
- Repeated rapid requests to /api/health/db are throttled by the rate limiter
