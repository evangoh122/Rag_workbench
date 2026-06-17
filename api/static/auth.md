# Agent Authentication

This site hosts a public portfolio and an interactive RAG Workbench.

## Read-only Discovery
All agent discovery endpoints (such as `/.well-known/api-catalog`, `/.well-known/mcp/server-card.json`, and `/.well-known/agent-card.json`) do not require authentication and are open to all AI crawlers and agents.

## API Usage
For query endpoints and RAG features, authentication details are configured via local session headers. No prior token registration is required.
