import pytest
import time
from fastapi import Request, HTTPException
from unittest.mock import AsyncMock, MagicMock
from api.middleware.rate_limit import rate_limit_middleware

@pytest.mark.asyncio
async def test_rate_limit_under_limit():
    # Mock request
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    
    # Mock call_next
    call_next = AsyncMock(return_value="OK")
    
    # Run middleware
    response = await rate_limit_middleware(request, call_next)
    
    assert response == "OK"
    call_next.assert_called_once_with(request)

@pytest.mark.asyncio
async def test_rate_limit_exceeded():
    from api.middleware.rate_limit import MAX_REQUESTS, _rate_limits
    
    client_ip = "192.168.1.1"
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = client_ip
    
    call_next = AsyncMock(return_value="OK")
    
    # Pre-fill rate limits for this IP
    now = time.time()
    _rate_limits[client_ip] = [now] * MAX_REQUESTS
    
    with pytest.raises(HTTPException) as exc:
        await rate_limit_middleware(request, call_next)
    
    assert exc.value.status_code == 429
    assert exc.value.detail == "Too Many Requests"
    call_next.assert_not_called()

@pytest.mark.asyncio
async def test_rate_limit_window_expiry():
    from api.middleware.rate_limit import MAX_REQUESTS, WINDOW_SECONDS, _rate_limits
    
    client_ip = "10.0.0.1"
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = client_ip
    
    call_next = AsyncMock(return_value="OK")
    
    # Fill with expired timestamps
    old_time = time.time() - WINDOW_SECONDS - 1
    _rate_limits[client_ip] = [old_time] * MAX_REQUESTS
    
    # Should succeed because old timestamps are filtered out
    response = await rate_limit_middleware(request, call_next)
    
    assert response == "OK"
    assert len(_rate_limits[client_ip]) == 1 # Only the new request

@pytest.mark.asyncio
async def test_rate_limit_x_forwarded_for():
    request = MagicMock(spec=Request)
    request.headers = {"X-Forwarded-For": "203.0.113.1, 192.168.1.1"}
    request.client = None
    
    call_next = AsyncMock(return_value="OK")
    
    # Should use the first IP in X-Forwarded-For
    from api.middleware.rate_limit import _rate_limits
    
    await rate_limit_middleware(request, call_next)
    assert "203.0.113.1" in _rate_limits
