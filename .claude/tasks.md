# Orchestrator Task — 2026-06-07
Feature: Add GET /api/health/db route handler
Status: done

## Your Tasks
- [ ] Create api/routes/health.py with a GET /api/health/db endpoint that runs a lightweight DuckDB query and returns JSON {status: "ok", row_count: N}
- [ ] Register the health router in api/routes/__init__.py

## Files
- api/routes/health.py
- api/routes/__init__.py

## Acceptance Criteria
- GET /api/health/db returns JSON with status key equal to "ok" and an integer row_count field
