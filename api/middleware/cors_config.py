import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

_ORIGIN_RE = re.compile(r"^https?://[\w.-]+(:\d+)?$")


def _validate_origins(raw: str) -> list[str]:
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    valid = []
    for origin in origins:
        if origin == "*":
            logger.warning(
                "CORS_ORIGINS contains '*' — all origins allowed. "
                "allow_credentials will be disabled for safety."
            )
            return ["*"]
        if _ORIGIN_RE.match(origin):
            valid.append(origin)
        else:
            logger.warning("CORS_ORIGINS contains invalid origin, ignoring: {}", origin)
    if not valid:
        logger.warning("No valid CORS origins found, defaulting to http://localhost:3000")
        return ["http://localhost:3000"]
    return valid


def configure_cors(app: FastAPI) -> None:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    origins = _validate_origins(raw)
    allow_creds = origins != ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_creds,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Requested-With"],
    )
