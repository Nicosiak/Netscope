"""Shared helpers for web backend route handlers."""

from __future__ import annotations

from fastapi import HTTPException


def sanitize_host(raw_host: str) -> str:
    """Normalize and validate a user-supplied hostname/IP.

    Raises HTTP 400 if the host is invalid so every endpoint fails
    consistently before touching any subprocess.
    """
    from core.sanitize import normalize_diagnostic_host
    host = normalize_diagnostic_host(raw_host)
    if not host:
        raise HTTPException(status_code=400, detail="Invalid hostname or IP address")
    return host
