from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from importlib import import_module
from threading import Lock
from typing import Any

from .config import get_settings

_cache_lock = Lock()
_cache_store: dict[str, tuple[datetime, str]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expiry(ttl_seconds: int) -> datetime:
    return _utcnow() + timedelta(seconds=ttl_seconds)


def _redis_client():
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        redis_module = import_module("redis")
        client = redis_module.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def build_query_cache_key(session_id: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"workspace-query:{session_id}:{digest}"


def get_session_cache(key: str) -> dict[str, Any] | None:
    client = _redis_client()
    if client is not None:
        raw = client.get(key)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    now = _utcnow()
    with _cache_lock:
        dead = [k for k, (exp, _) in _cache_store.items() if exp <= now]
        for k in dead:
            _cache_store.pop(k, None)
        item = _cache_store.get(key)
        if not item:
            return None
        _, raw = item
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None


def set_session_cache(key: str, payload: dict[str, Any], ttl_seconds: int = 600) -> None:
    raw = json.dumps(payload, default=str)
    client = _redis_client()
    if client is not None:
        client.setex(key, ttl_seconds, raw)
        return

    with _cache_lock:
        _cache_store[key] = (_expiry(ttl_seconds), raw)
