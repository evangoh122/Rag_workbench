import hmac
import os
from fastapi import Request, HTTPException, status
from loguru import logger

API_KEY_NAME = "X-API-Key"


async def get_api_key(request: Request):
    api_key = request.headers.get(API_KEY_NAME)
    expected_key = os.getenv("API_KEY")

    if not expected_key:
        logger.warning("API_KEY env var not set — rejecting all requests. Set API_KEY to enable access.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured",
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )

    if not hmac.compare_digest(api_key.encode(), expected_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key
