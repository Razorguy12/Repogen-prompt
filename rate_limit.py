"""Small in-process sliding-window rate limiter.

Per-process only: with several Uvicorn workers, the effective limit is
multiplied by the worker count. Pair with Nginx limit_req in production.
"""
import threading
from time import monotonic

from fastapi import HTTPException

_lock = threading.Lock()
_windows: dict[tuple[int, str], list[float]] = {}


def enforce_rate_limit(user_id: int, action: str, limit: int, window_seconds: int = 60) -> None:
    now = monotonic()
    key = (user_id, action)
    with _lock:
        hits = [t for t in _windows.get(key, []) if now - t < window_seconds]
        if len(hits) >= limit:
            _windows[key] = hits
            raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")
        hits.append(now)
        _windows[key] = hits


def reset() -> None:
    with _lock:
        _windows.clear()
