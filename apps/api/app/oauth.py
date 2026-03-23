from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from .schemas import HubSpotTokenResponse

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
