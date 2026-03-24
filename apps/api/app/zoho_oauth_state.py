"""Short-lived server-side storage for Zoho OAuth (authorization code flow)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

_lock = Lock()
_store: dict[str, tuple[datetime, "ZohoOAuthPending"]] = {}


@dataclass(frozen=True)
class ZohoOAuthPending:
    client_id: str
    client_secret: str
    redirect_uri: str
    accounts_host: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def put_zoho_oauth_pending(state: str, pending: ZohoOAuthPending, ttl_seconds: int = 600) -> None:
    expires = _utcnow() + timedelta(seconds=ttl_seconds)
    with _lock:
        _purge_locked()
        _store[state] = (expires, pending)


def pop_zoho_oauth_pending(state: str) -> ZohoOAuthPending | None:
    with _lock:
        _purge_locked()
        item = _store.pop(state, None)
        if not item:
            return None
        expires, pending = item
        if expires <= _utcnow():
            return None
        return pending


def _purge_locked() -> None:
    now = _utcnow()
    dead = [k for k, (exp, _) in _store.items() if exp <= now]
    for k in dead:
        _store.pop(k, None)
