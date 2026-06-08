import asyncio
import time
from fastapi import Request, HTTPException
from collections import defaultdict

# Thread-safe in-memory rate limiter
_rate_limits: dict[str, list[float]] = defaultdict(list)
_lock = asyncio.Lock()
_last_cleanup = time.time()

async def rate_limit_middleware(request: Request, call_next):
    global _last_cleanup
    
    # Get real client IP (handle reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host or "unknown"
    
    now = time.time()
    
    async with _lock:
        # 60 requests per minute
        _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < 60]
        
        # Periodic global cleanup (every 60 seconds)
        if now - _last_cleanup > 60:
            stale_ips = [ip for ip, times in _rate_limits.items() if not times or now - times[-1] > 300]
            for ip in stale_ips:
                del _rate_limits[ip]
            _last_cleanup = now
        
        if len(_rate_limits[client_ip]) >= 60:
            raise HTTPException(status_code=429, detail="Too Many Requests")
            
        _rate_limits[client_ip].append(now)
    
    response = await call_next(request)
    return response
