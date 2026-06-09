import asyncio
import time
from fastapi import Request, HTTPException
from cachetools import TTLCache

# Bounded in-memory rate limiter with automatic TTL eviction.
# 10,000 unique IPs max, entries expire after 120 seconds of inactivity.
_rate_limits: dict[str, list[float]] = TTLCache(maxsize=10_000, ttl=120)
_lock = asyncio.Lock()

MAX_REQUESTS = 60
WINDOW_SECONDS = 60


async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    now = time.time()

    async with _lock:
        timestamps = _rate_limits.get(client_ip, [])
        timestamps = [t for t in timestamps if now - t < WINDOW_SECONDS]

        if len(timestamps) >= MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Too Many Requests")

        timestamps.append(now)
        _rate_limits[client_ip] = timestamps

    response = await call_next(request)
    return response
