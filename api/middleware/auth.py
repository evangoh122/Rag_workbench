import hmac
import logging
from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
import os

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = API_KEY_NAME

async def get_api_key(request: Request):
    api_key = request.headers.get(API_KEY_NAME)
    expected_key = os.getenv("API_KEY")
    
    if not expected_key:
        logger.warning("API_KEY not configured - allowing unauthenticated access. Set API_KEY env var for production.")
        return None
        
    if not api_key or not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key
