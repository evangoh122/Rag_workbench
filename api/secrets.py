"""
api/secrets.py — centralized secret access.

All API keys and credentials must be retrieved through this module so that the
access pattern is consistent and the backend can be swapped (e.g., to a vault)
without touching callers.

Secrets are read from environment variables, which are populated from .env at
startup via python-dotenv in api/config.py.
"""
from __future__ import annotations

import os
from typing import Optional


class SecretNotFoundError(RuntimeError):
    """Raised when a required secret is absent from the environment."""


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return the named secret from the environment, or default if absent."""
    return os.getenv(name, default)


def require_secret(name: str) -> str:
    """Return the named secret or raise SecretNotFoundError with clear instructions."""
    value = os.getenv(name)
    if not value:
        raise SecretNotFoundError(
            f"Required secret '{name}' is not set. "
            "Copy .env.example to .env and fill in your value, "
            "or export it as an environment variable before starting the server."
        )
    return value
