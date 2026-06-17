import os
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, FileResponse

router = APIRouter()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@router.get("/auth.md")
async def serve_auth_md():
    auth_md_path = os.path.join(STATIC_DIR, "auth.md")
    if os.path.exists(auth_md_path):
        return FileResponse(auth_md_path, media_type="text/markdown")
    return Response(
        content="# Agent Authentication\n\nNo registration or authorization is required for read-only agent discovery on this site.",
        media_type="text/markdown"
    )

@router.get("/.well-known/api-catalog", response_class=JSONResponse)
async def api_catalog(request: Request):
    base = str(request.base_url).rstrip("/")
    headers = {"Content-Type": "application/linkset+json"}
    content = {
        "linkset": [
            {
                "anchor": f"{base}/api",
                "service-desc": [
                    {
                        "href": f"{base}/openapi.json",
                        "type": "application/openapi+json"
                    }
                ],
                "service-doc": [
                    {
                        "href": f"{base}/docs",
                        "type": "text/html"
                    }
                ]
            }
        ]
    }
    return JSONResponse(content=content, headers=headers)

@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "resource": f"{base}/api",
        "authorization_servers": [f"{base}/api/auth"]
    }

@router.get("/.well-known/openid-configuration")
async def openid_configuration(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/api/auth/authorize",
        "token_endpoint": f"{base}/api/auth/token",
        "jwks_uri": f"{base}/api/auth/jwks",
        "response_types_supported": ["code", "token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    }

@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/api/auth/authorize",
        "token_endpoint": f"{base}/api/auth/token",
        "grant_types_supported": ["authorization_code", "client_credentials"]
    }

@router.get("/.well-known/mcp/server-card.json")
@router.get("/.well-known/mcp.json")
@router.get("/.well-known/mcp/server-cards.json")
async def mcp_server_card(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "serverInfo": {
            "name": "Evan Goh RAG Workbench Server",
            "version": "1.0.0",
            "description": "Financial SEC filings auditable RAG engine and entity-relation graph explorer"
        },
        "transports": [
            {
                "type": "sse",
                "endpoint": f"{base}/api/mcp/sse"
            }
        ],
        "capabilities": {
            "tools": True,
            "resources": True
        }
    }

@router.get("/.well-known/agent-card.json")
async def agent_card(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "name": "Evan Goh RAG Workbench Agent",
        "version": "1.0.0",
        "description": "An auditable AI agent for inspecting and analyzing SEC financial filings",
        "supportedInterfaces": [
            {
                "interface": "a2a",
                "url": f"{base}/api/agent/interact",
                "protocol": "https"
            }
        ],
        "capabilities": {
            "auditability": "verifiable_xbrl_facts",
            "explainability": "execution_trace_visualization"
        },
        "skills": [
            {
                "id": "financial_analysis",
                "name": "Financial Document Analysis",
                "description": "Analyzing 10-K and 10-Q statements and verifying financial calculations"
            }
        ]
    }

@router.get("/.well-known/agent-skills/index.json")
async def agent_skills_index(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "$schema": "https://agentskills.io/schemas/v0.2.0/index.json",
        "skills": [
            {
                "name": "Financial QA",
                "type": "skill-md",
                "description": "Answers complex regulatory and financial audit questions based on corporate disclosures",
                "url": f"{base}/api/agent-skills/financial-qa.md"
            }
        ]
    }

@router.get("/api/agent-skills/financial-qa.md")
async def serve_financial_qa_md():
    fq_path = os.path.join(STATIC_DIR, "financial-qa.md")
    if os.path.exists(fq_path):
        return FileResponse(fq_path, media_type="text/markdown")
    return Response(
        content="# Financial QA Skill\n\nAnswers queries against SEC financial filings using integrated LangGraph agent with auditable sources and XBRL verification.",
        media_type="text/markdown"
    )
