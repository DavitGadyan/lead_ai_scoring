from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from .schemas import HubSpotTokenResponse, ZohoTokenResponse
from .zoho_oauth_state import ZohoOAuthPending, put_zoho_oauth_pending

HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"


def build_hubspot_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    optional_scope: str | None = None,
) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    query_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    if optional_scope:
        query_params["optional_scope"] = optional_scope
    query = urlencode(query_params)
    return f"{HUBSPOT_AUTHORIZE_URL}?{query}", state


def exchange_hubspot_code(*, client_id: str, client_secret: str, redirect_uri: str, code: str) -> HubSpotTokenResponse:
    response = httpx.post(
        HUBSPOT_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    response.raise_for_status()
    return HubSpotTokenResponse.model_validate(response.json())


def refresh_hubspot_token(*, client_id: str, client_secret: str, refresh_token: str) -> HubSpotTokenResponse:
    response = httpx.post(
        HUBSPOT_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    response.raise_for_status()
    return HubSpotTokenResponse.model_validate(response.json())


def resolve_zoho_authorize_credentials(
    *,
    client_id: str | None,
    client_secret: str | None,
    redirect_uri: str | None,
    accounts_host: str | None,
) -> tuple[str, str, str, str]:
    """Merge form values with ``Settings`` (``ZOHO_*`` env vars)."""
    from .config import get_settings

    s = get_settings()
    cid = (client_id or "").strip() or (s.zoho_client_id or "").strip()
    sec = (client_secret or "").strip() or (s.zoho_client_secret or "").strip()
    redir = (redirect_uri or "").strip() or (s.zoho_redirect_uri or "").strip()
    host_raw = (accounts_host or "").strip() or (s.zoho_accounts_host or "").strip() or "accounts.zoho.com"
    return cid, sec, normalize_zoho_accounts_host(host_raw), redir


def normalize_zoho_accounts_host(host: str | None) -> str:
    h = (host or "accounts.zoho.com").strip().rstrip("/")
    if h.startswith("https://"):
        h = h[8:]
    if h.startswith("http://"):
        h = h[7:]
    return h or "accounts.zoho.com"


def zoho_token_accounts_host(*, callback_accounts_server: str | None, pending_host: str) -> str:
    """Use Zoho's ``accounts-server`` redirect query param when present.

    EU/IN/etc. users get e.g. ``accounts-server=https%3A%2F%2Faccounts.zoho.eu``.
    The authorization code must be exchanged at that data center's token URL,
    not necessarily at ``pending_host`` from the authorize step.
    """
    from urllib.parse import unquote, urlparse

    if not callback_accounts_server or not str(callback_accounts_server).strip():
        return normalize_zoho_accounts_host(pending_host)
    raw = unquote(str(callback_accounts_server).strip())
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if parsed.hostname:
            return normalize_zoho_accounts_host(parsed.hostname)
    return normalize_zoho_accounts_host(raw)


def build_zoho_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    accounts_host: str,
    state: str,
) -> str:
    host = normalize_zoho_accounts_host(accounts_host)
    query_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = urlencode(query_params)
    return f"https://{host}/oauth/v2/auth?{query}"


def prepare_zoho_authorize(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scope: str,
    accounts_host: str,
    state: str,
) -> str:
    pending = ZohoOAuthPending(
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
        redirect_uri=redirect_uri.strip(),
        accounts_host=normalize_zoho_accounts_host(accounts_host),
    )
    put_zoho_oauth_pending(state, pending)
    return build_zoho_authorize_url(
        client_id=pending.client_id,
        redirect_uri=pending.redirect_uri,
        scope=scope,
        accounts_host=pending.accounts_host,
        state=state,
    )


def _parse_zoho_token_json(response: httpx.Response) -> ZohoTokenResponse:
    """Zoho often returns HTTP 200 with ``{\"error\": \"...\"}`` instead of tokens."""
    try:
        body = response.json()
    except Exception as exc:
        detail = (response.text or "")[:500]
        raise ValueError(f"Zoho token response was not JSON (HTTP {response.status_code}): {detail}") from exc

    if not isinstance(body, dict):
        raise ValueError(f"Unexpected Zoho token response: {body!r}")

    if body.get("error"):
        err = body.get("error")
        desc = body.get("error_description") or body.get("message") or ""
        msg = f"Zoho token error: {err}"
        if desc:
            msg = f"{msg} — {desc}"
        raise ValueError(msg)

    if not response.is_success:
        raise ValueError(f"Zoho token HTTP {response.status_code}: {body}")

    return ZohoTokenResponse.model_validate(body)


def exchange_zoho_code(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    accounts_host: str,
) -> ZohoTokenResponse:
    host = normalize_zoho_accounts_host(accounts_host)
    response = httpx.post(
        f"https://{host}/oauth/v2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    return _parse_zoho_token_json(response)


def refresh_zoho_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    accounts_host: str,
) -> ZohoTokenResponse:
    host = normalize_zoho_accounts_host(accounts_host)
    response = httpx.post(
        f"https://{host}/oauth/v2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    return _parse_zoho_token_json(response)
