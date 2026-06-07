import time
from fastapi import Request, HTTPException
from collections import defaultdict

# Simple in-memory rate limiter (Gemini: "Optimize parallel retrieval and async performance")
_rate_limits = defaultdict(list)

async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    now = time.time()
    
    # 60 requests per minute
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < 60]
    
    if len(_rate_limits[client_ip]) >= 60:
        raise HTTPException(status_code=429, detail="Too Many Requests")
        
    _rate_limits[client_ip].append(now)
    response = await call_next(request)
    return response
