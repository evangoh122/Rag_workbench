# Orchestrator Task — 2026-06-07
Feature: Optimize DuckDB health check query
Status: done

## Your Tasks
- [ ] Ensure the /api/health/db endpoint reuses an existing DuckDB connection from api/db/database.py rather than opening a new connection per request

## Files
- api/db/database.py

## Acceptance Criteria
- Health check query completes using a cached or pooled DuckDB connection (no new connection opened per request)
