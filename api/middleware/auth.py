import hmac
import os
from fastapi import Request, HTTPException, status
from loguru import logger

API_KEY_NAME = "X-API-Key"


def _verify_key(request: Request, key_env_vars: list[str], level_name: str):
    """Internal helper to verify API key against a list of allowed environment variables."""
    api_key = request.headers.get(API_KEY_NAME)
    
    # Get all possible valid keys for this level
    valid_keys = []
    for var in key_env_vars:
        val = os.getenv(var)
        if val:
            valid_keys.append(val)
            
    if not valid_keys:
        # Fallback to base API_KEY if no specific keys are set
        base_key = os.getenv("API_KEY")
        if base_key:
            valid_keys.append(base_key)
            
    if not valid_keys:
        logger.warning(f"No API keys configured for {level_name} access. Rejecting request.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured",
        )

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{API_KEY_NAME} header required",
        )

    for expected_key in valid_keys:
        if hmac.compare_digest(api_key.encode(), expected_key.encode()):
            return api_key

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Could not validate credentials for {level_name} access",
    )


async def get_read_api_key(request: Request):
    """Allow READ, WRITE, or ADMIN keys."""
    return _verify_key(request, ["READ_API_KEY", "WRITE_API_KEY", "ADMIN_API_KEY"], "Read")


async def get_write_api_key(request: Request):
    """Allow WRITE or ADMIN keys."""
    return _verify_key(request, ["WRITE_API_KEY", "ADMIN_API_KEY"], "Write")


async def get_admin_api_key(request: Request):
    """Allow only ADMIN key. Does NOT fall back to generic API_KEY — misconfiguration
    must hard-fail rather than silently grant admin access to a shared key."""
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key not configured",
        )
    api_key = request.headers.get(API_KEY_NAME)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{API_KEY_NAME} header required",
        )
    if hmac.compare_digest(api_key.encode(), admin_key.encode()):
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate admin credentials",
    )


# Legacy support
async def get_api_key(request: Request):
    """Standard API key check (defaults to READ level)."""
    return await get_read_api_key(request)
