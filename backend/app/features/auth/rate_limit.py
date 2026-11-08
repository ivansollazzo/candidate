"""Per-IP limit on failed sign-ins and recovery keys (Settings › Security), whatever the account.

Kept in memory: the backend runs a single process, and a restart clearing the counts is acceptable.
"""

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.i18n import t
from app.features.settings.models import AppSettings

# Above this many tracked addresses, the ones without recent failures are dropped
_MAX_TRACKED = 10_000

_failures: dict[str, deque[float]] = {}
_lock = Lock()


def _client(request: Request) -> str:
    # The real address: uvicorn reads X-Forwarded-For, set by Caddy (backend Dockerfile)
    return request.client.host if request.client else "unknown"


def _recent(ip: str, window: float, now: float) -> deque[float]:
    times = _failures.get(ip, deque())
    while times and times[0] <= now - window:
        times.popleft()
    return times


def ensure_allowed(request: Request, settings: AppSettings) -> None:
    """429 while the address has reached the failed attempts allowed in the window."""
    if not settings.ip_limit_enabled:
        return
    window, now = settings.ip_block_minutes * 60, time.monotonic()
    with _lock:
        times = _recent(_client(request), window, now)
        if len(times) < settings.ip_max_attempts:
            return
        wait = times[len(times) - settings.ip_max_attempts] + window - now
    minutes = max(1, round(wait / 60))
    raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, t("ip_limited", minutes=minutes),
                        headers={"Retry-After": str(max(1, round(wait)))})


def register_failure(request: Request, settings: AppSettings) -> None:
    if not settings.ip_limit_enabled:
        return
    window, now = settings.ip_block_minutes * 60, time.monotonic()
    with _lock:
        if len(_failures) > _MAX_TRACKED:
            for ip in [ip for ip, times in _failures.items() if not _recent(ip, window, now)]:
                del _failures[ip]
        ip = _client(request)
        times = _recent(ip, window, now)
        times.append(now)
        _failures[ip] = times


def reset() -> None:
    """Forget every count (tests)."""
    with _lock:
        _failures.clear()
