from __future__ import annotations

import asyncio
import json
import re
import shutil
from abc import ABC, abstractmethod
from typing import Any

import httpx
import pandas as pd
from pymongo import MongoClient
from sqlalchemy import create_engine, text

from .oauth import normalize_zoho_accounts_host, refresh_hubspot_token, refresh_zoho_token


def _zoho_client_credentials(config: SourceConfig) -> tuple[str, str, str]:
    """OAuth client id/secret and accounts host from source config, with API .env fallback."""
    from .config import get_settings

    s = get_settings()
    cid = (config.client_id or "").strip() or (s.zoho_client_id or "").strip()
    sec = (config.client_secret or "").strip() or (s.zoho_client_secret or "").strip()
    host = normalize_zoho_accounts_host(config.zoho_accounts_host or s.zoho_accounts_host)
    return cid, sec, host
from .schemas import SourceConfig


class SourceAdapter(ABC):
    @abstractmethod
    def load_records(self, config: SourceConfig) -> list[dict]:
        raise NotImplementedError


class SqlAdapter(SourceAdapter):
    def __init__(self, source_key: str = "sql") -> None:
        self.source_key = source_key

    def load_records(self, config: SourceConfig) -> list[dict]:
        from .config import get_settings

        settings = get_settings()
        url = (config.connection_url or "").strip()
        query = (config.query or "").strip()

        if not url:
            if self.source_key == "postgres":
                url = (settings.postgres_source_url or "").strip()
            elif self.source_key == "supabase":
                url = (settings.supabase_source_url or "").strip()
            elif self.source_key == "mysql":
                url = (settings.mysql_source_url or "").strip()

        if not query:
            if self.source_key == "postgres":
                query = (settings.postgres_source_query or "").strip()
            elif self.source_key == "supabase":
                query = (settings.supabase_source_query or "").strip()
            elif self.source_key == "mysql":
                query = (settings.mysql_source_query or "").strip()

        if not url or not query:
            raise ValueError("SQL sources require connection_url and query")

        engine = create_engine(url)
        with engine.connect() as connection:
            rows = connection.execute(text(query))
            return [dict(row._mapping) for row in rows]


class MongoAdapter(SourceAdapter):
    def __init__(self, source_key: str = "mongodb") -> None:
        self.source_key = source_key

    def load_records(self, config: SourceConfig) -> list[dict]:
        from .config import get_settings

        settings = get_settings()
        connection_url = (config.connection_url or "").strip() or (settings.mongodb_source_url or "").strip()
        database = (config.database or "").strip() or (settings.mongodb_source_database or "").strip()
        collection_name = (config.collection or "").strip() or (settings.mongodb_source_collection or "").strip()
        query_filter = config.filter
        if query_filter is None:
            raw_filter = (settings.mongodb_source_filter or "").strip() or "{}"
            try:
                parsed = json.loads(raw_filter)
                query_filter = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                query_filter = {}

        if not connection_url or not database or not collection_name:
            raise ValueError("MongoDB sources require connection_url, database, and collection")

        client = MongoClient(connection_url)
        collection = client[database][collection_name]
        cursor = collection.find(query_filter or {}, {"_id": 0})
        return list(cursor)


class ExcelAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.file_path:
            raise ValueError("Excel sources require file_path")

        frame = pd.read_excel(config.file_path, sheet_name=config.sheet_name or 0)
        if isinstance(frame, dict):
            first_sheet = next(iter(frame.values()))
            return first_sheet.to_dict(orient="records")
        return frame.to_dict(orient="records")


class CsvAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.file_path:
            raise ValueError("CSV sources require file_path")

        frame = pd.read_csv(config.file_path)
        return frame.to_dict(orient="records")


class HubSpotAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        access_token = config.access_token
        if not access_token and config.refresh_token and config.client_id and config.client_secret:
            refreshed = refresh_hubspot_token(
                client_id=config.client_id,
                client_secret=config.client_secret,
                refresh_token=config.refresh_token,
            )
            access_token = refreshed.access_token

        if not access_token:
            raise ValueError("HubSpot requires OAuth access token or refresh token with client credentials")

        object_name = config.object_name or "contacts"
        params = config.params or {"limit": 100}
        url = f"https://api.hubapi.com/crm/v3/objects/{object_name}"
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30.0,
        )
        if (
            response.status_code == 401
            and config.refresh_token
            and config.client_id
            and config.client_secret
        ):
            refreshed = refresh_hubspot_token(
                client_id=config.client_id,
                client_secret=config.client_secret,
                refresh_token=config.refresh_token,
            )
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {refreshed.access_token}"},
                params=params,
                timeout=30.0,
            )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [item.get("properties", {}) | {"external_id": item.get("id")} for item in results]


def _resolve_hubspot_access_token(config: SourceConfig) -> str:
    access_token = config.access_token
    if not access_token and config.refresh_token and config.client_id and config.client_secret:
        refreshed = refresh_hubspot_token(
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token,
        )
        access_token = refreshed.access_token

    if not access_token:
        raise ValueError("HubSpot requires OAuth access token or refresh token with client credentials")
    return access_token


def browse_hubspot_object(config: SourceConfig, object_name: str, after: str | None = None, limit: int = 5) -> dict:
    access_token = _resolve_hubspot_access_token(config)
    property_map = {
        "contacts": ["firstname", "lastname", "email", "company", "jobtitle", "phone", "createdate"],
        "companies": ["name", "domain", "industry", "city", "country", "phone", "createdate"],
    }
    params: dict[str, object] = {
        "limit": limit,
        "properties": ",".join(property_map.get(object_name, [])),
    }
    if after:
        params["after"] = after

    url = f"https://api.hubapi.com/crm/v3/objects/{object_name}"
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=30.0,
    )
    if (
        response.status_code == 401
        and config.refresh_token
        and config.client_id
        and config.client_secret
    ):
        refreshed = refresh_hubspot_token(
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token,
        )
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {refreshed.access_token}"},
            params=params,
            timeout=30.0,
        )
    response.raise_for_status()
    return response.json()


class SalesforceAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.base_url or not config.access_token or not config.query:
            raise ValueError("Salesforce requires base_url, access_token, and query")

        response = httpx.get(
            f"{config.base_url.rstrip('/')}/services/data/v61.0/query",
            headers={"Authorization": f"Bearer {config.access_token}"},
            params={"q": config.query},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("records", [])


class DynamicsAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.base_url or not config.access_token:
            raise ValueError("Dynamics 365 requires base_url and access_token")

        object_name = config.object_name or "leads"
        response = httpx.get(
            f"{config.base_url.rstrip('/')}/api/data/v9.2/{object_name}",
            headers={
                "Authorization": f"Bearer {config.access_token}",
                "Accept": "application/json",
            },
            params=config.params or {"$top": 100},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("value", [])


def _resolve_zoho_access_token(config: SourceConfig) -> str:
    access_token = config.access_token
    accounts_host = normalize_zoho_accounts_host(config.zoho_accounts_host)
    if not access_token and config.refresh_token and config.client_id and config.client_secret:
        refreshed = refresh_zoho_token(
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token,
            accounts_host=accounts_host,
        )
        access_token = refreshed.access_token

    if not access_token:
        raise ValueError(
            "Zoho requires an OAuth access token (use Connect Zoho CRM) or refresh_token with client credentials"
        )
    return access_token


class ZohoAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        access_token = _resolve_zoho_access_token(config)
        base_url = (config.base_url or "https://www.zohoapis.com").rstrip("/")
        module = config.object_name or "Leads"
        params = config.params or {"per_page": 100}

        def _get(token: str) -> httpx.Response:
            return httpx.get(
                f"{base_url}/crm/v2/{module}",
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                params=params,
                timeout=30.0,
            )

        response = _get(access_token)
        z_cid, z_sec, z_host = _zoho_client_credentials(config)
        if response.status_code == 401 and config.refresh_token and z_cid and z_sec:
            refreshed = refresh_zoho_token(
                client_id=z_cid,
                client_secret=z_sec,
                refresh_token=config.refresh_token,
                accounts_host=z_host,
            )
            response = _get(refreshed.access_token)

        response.raise_for_status()
        return response.json().get("data", [])


class PipedriveAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.api_key:
            raise ValueError("Pipedrive requires api_key")

        base_url = (config.base_url or "https://api.pipedrive.com/api/v1").rstrip("/")
        resource = config.object_name or "leads"
        response = httpx.get(
            f"{base_url}/{resource}",
            params={"api_token": config.api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("data", []) or []


class FreshsalesAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.base_url or not config.api_key:
            raise ValueError("Freshsales requires base_url and api_key")

        resource = config.object_name or "leads"
        response = httpx.get(
            f"{config.base_url.rstrip('/')}/{resource}",
            headers={"Authorization": f"Token token={config.api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        return body.get(resource, body.get("items", []))


MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_VERSION = "2023-10"


def _monday_auth_token(raw: str | None) -> str:
    t = (raw or "").strip()
    if t.lower().startswith("bearer "):
        return t[7:].strip()
    return t


def _monday_parse_board_ids(raw: str | None) -> list[str]:
    """Resolve board IDs from comma-separated values or pasted monday board URLs."""
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in str(raw).replace("\n", ",").split(","):
        p = part.strip()
        if not p:
            continue
        url_m = re.search(r"/boards/(\d+)", p, re.I)
        if url_m:
            out.append(url_m.group(1))
            continue
        digits = re.sub(r"\D+", "", p)
        if digits:
            out.append(digits)
            continue
        raise ValueError(f"Invalid monday board id (use digits or a URL containing /boards/<id>/): {p!r}")
    return out


def _monday_item_limit(config: SourceConfig) -> int:
    params = config.params or {}
    raw = params.get("limit", 100)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 100
    return max(1, min(n, 500))


def _monday_default_graphql_query(board_ids: list[str], limit: int) -> str:
    # monday docs often use a scalar for one board: boards(ids: 1234567890). Multiple IDs use a list.
    if len(board_ids) == 1:
        ids_arg = board_ids[0]
    else:
        ids_arg = "[" + ", ".join(board_ids) + "]"
    return f"""query LeadscoreMondayBoardItems {{
  boards(ids: {ids_arg}) {{
    id
    name
    items_page(limit: {limit}) {{
      items {{
        id
        name
        column_values {{
          id
          text
          type
          value
        }}
      }}
    }}
  }}
}}"""


def _monday_cell_display(cv: dict) -> object | None:
    display_text = cv.get("text")
    if display_text is not None and str(display_text).strip() != "":
        return display_text
    raw = cv.get("value")
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "text" in parsed:
                return parsed.get("text")
            if isinstance(parsed, (str, int, float)):
                return parsed
        except json.JSONDecodeError:
            return raw
        return raw
    return raw


def _monday_flatten_graphql_response(body: dict, *, board_ids_hint: list[str] | None = None) -> list[dict]:
    if body.get("errors"):
        parts: list[str] = []
        for err in body["errors"]:
            if isinstance(err, dict):
                parts.append(str(err.get("message") or err))
            else:
                parts.append(str(err))
        raise ValueError("Monday API: " + "; ".join(parts))

    data = body.get("data")
    if not isinstance(data, dict):
        return []

    rows: list[dict] = []
    boards = data.get("boards")
    if not isinstance(boards, list):
        return rows

    if board_ids_hint and isinstance(boards, list):
        if not boards or all(b is None for b in boards):
            hint = ", ".join(board_ids_hint)
            raise ValueError(
                "Monday returned no boards for the given ID(s) "
                f"({hint}). Open your board in the browser and copy the ID from the URL "
                "(…/boards/<your_id>/…). Tutorial examples use sample IDs that are not in your account — "
                "Developer mode (Profile → monday.labs) can also show board IDs."
            )

    for board in boards:
        if not isinstance(board, dict):
            continue
        bid = board.get("id")
        bname = board.get("name")
        page = board.get("items_page")
        if not isinstance(page, dict):
            continue
        items = page.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            flat: dict = {
                "id": item.get("id"),
                "name": item.get("name"),
                "board_id": bid,
                "board_name": bname,
            }
            for cv in item.get("column_values") or []:
                if not isinstance(cv, dict):
                    continue
                col_id = cv.get("id")
                if not col_id:
                    continue
                key = str(col_id).replace(" ", "_")
                if key.lower() == "name":
                    key = "column_name"
                flat[key] = _monday_cell_display(cv)
            rows.append(flat)
    return rows


def _monday_resolve_from_env(config: SourceConfig) -> tuple[str, str, str]:
    """Token, board IDs string, and optional GraphQL query: form values win when non-empty; else API .env."""
    from .config import get_settings

    s = get_settings()
    token = _monday_auth_token(
        (config.access_token or "").strip() or (s.monday_api_token or "").strip()
    )
    boards = (config.monday_board_ids or "").strip() or (s.monday_board_ids or "").strip()
    query = (config.query or "").strip() or (s.monday_graphql_query or "").strip()
    return token, boards, query


class MondayAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        token, boards_raw, query_text = _monday_resolve_from_env(config)
        if not token:
            raise ValueError(
                "monday CRM requires access_token (Connect form) or MONDAY_API_TOKEN in API .env"
            )

        board_ids_for_hint: list[str] | None = None
        if not query_text:
            board_ids_for_hint = _monday_parse_board_ids(boards_raw)
            if not board_ids_for_hint:
                raise ValueError(
                    "monday CRM requires monday_board_ids (form) or MONDAY_BOARD_IDS in API .env, "
                    "or a custom GraphQL query (form query or MONDAY_GRAPHQL_QUERY in .env)"
                )
            query_text = _monday_default_graphql_query(board_ids_for_hint, _monday_item_limit(config))

        response = httpx.post(
            MONDAY_API_URL,
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
                "API-Version": MONDAY_API_VERSION,
            },
            json={"query": query_text},
            timeout=60.0,
        )
        response.raise_for_status()
        body = response.json()
        return _monday_flatten_graphql_response(
            body,
            board_ids_hint=board_ids_for_hint,
        )


_MCP_DEFAULTS: dict[str, dict[str, Any]] = {
    "dubai_dld_mcp": {
        "command": "uvx",
        "args": ["dld-mcp"],
        "default_tool": "search_properties",
    },
}


def _flatten_mcp_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "items", "data", "records", "markets", "projects", "sales", "buildings"):
            value = payload.get(key)
            if isinstance(value, list) and any(isinstance(item, dict) for item in value):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _normalize_tool_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _summary_text(parts: list[Any]) -> str | None:
    values = [str(part) for part in parts if part not in (None, "", [], {})]
    return " | ".join(values) if values else None


def _infer_dld_area(query: str) -> str:
    value = (query or "").lower()
    known_areas = {
        "palm jumeirah": "Palm Jumeirah",
        "business bay": "Business Bay",
        "downtown": "Downtown",
        "dubai marina": "Marina",
        "marina": "Marina",
        "jbr": "JBR",
        "jvc": "JVC",
        "jlt": "JLT",
        "dubai hills": "Dubai Hills",
        "bluewaters": "Bluewaters",
        "arabian ranches": "Arabian Ranches",
        "creek harbour": "Dubai Creek Harbour",
    }
    for token, label in known_areas.items():
        if token in value:
            return label
    return "Dubai"


def _normalize_dld_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        title = (
            row.get("project")
            or row.get("project_name")
            or row.get("building")
            or row.get("building_name")
            or row.get("community")
            or row.get("name")
            or row.get("title")
        )
        subtitle = _summary_text([row.get("community"), row.get("building"), row.get("property_type")])
        summary = _summary_text(
            [
                row.get("verdict"),
                f"median AED/sqm {row.get('median_price_sqm')}" if row.get("median_price_sqm") not in (None, "") else None,
                f"price AED {row.get('price')}" if row.get("price") not in (None, "") else None,
                f"transactions {row.get('transaction_count')}" if row.get("transaction_count") not in (None, "") else None,
                f"avg AED {row.get('avg_price')}" if row.get("avg_price") not in (None, "") else None,
                f"median AED {row.get('median_price')}" if row.get("median_price") not in (None, "") else None,
                f"count {row.get('count')}" if row.get("count") not in (None, "") else None,
                row.get("analysis"),
            ]
        )
        item = dict(row)
        item.update(
            {
                "title": str(title or row.get("area") or "Dubai DLD result"),
                "subtitle": subtitle,
                "summary": summary or _summary_text([f"{key}={value}" for key, value in row.items() if value not in (None, "", [], {})][:6]),
                "company": row.get("community"),
                "industry": "dubai_real_estate",
                "status": row.get("verdict") or row.get("property_type"),
                "source_id": str(row.get("project_id") or row.get("building_id") or row.get("id") or title or index + 1),
            }
        )
        normalized.append(item)
    return normalized

def _normalize_mcp_rows(profile: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _normalize_dld_rows(rows) if profile == "dubai_dld_mcp" else rows


def _extract_mcp_rows(result: Any) -> list[dict[str, Any]]:
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    rows = _flatten_mcp_payload(structured)
    if rows:
        return rows

    content = getattr(result, "content", None)
    if isinstance(content, list):
        extracted: list[dict[str, Any]] = []
        for item in content:
            text_value = getattr(item, "text", None)
            if isinstance(text_value, str) and text_value.strip():
                try:
                    extracted.extend(_flatten_mcp_payload(json.loads(text_value)))
                    continue
                except json.JSONDecodeError:
                    extracted.append(
                        {
                            "title": text_value.strip().splitlines()[0][:120],
                            "summary": text_value.strip(),
                        }
                    )
                    continue
            if hasattr(item, "model_dump"):
                extracted.extend(_flatten_mcp_payload(item.model_dump()))
        if extracted:
            return extracted

    if hasattr(result, "model_dump"):
        return _flatten_mcp_payload(result.model_dump())
    return []


def _extract_mcp_text(result: Any) -> str:
    content = getattr(result, "content", None)
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for item in content:
        text_value = getattr(item, "text", None)
        if isinstance(text_value, str) and text_value.strip():
            texts.append(text_value.strip())
    return "\n".join(texts).strip()


def _resolve_mcp_tool(profile: str, config: SourceConfig) -> str:
    if config.mcp_tool_name:
        return config.mcp_tool_name
    if config.object_name:
        return config.object_name
    query = (config.query or "").lower()
    if profile == "dubai_dld_mcp":
        if "market pulse" in query or "pulse" in query:
            return "get_market_pulse"
        if "trending" in query:
            return "get_trending_projects"
        if "price mover" in query or "mover" in query:
            return "get_price_movers"
        if "recent sale" in query or "recent sales" in query:
            return "get_recent_sales"
        if "deal" in query and {"project", "area_sqm", "price"}.issubset(set(config.params or {})):
            return "check_deal"
        if "listing" in query:
            return "analyze_listing"
    return str(_MCP_DEFAULTS.get(profile, {}).get("default_tool") or config.mcp_tool_name or "")


def _resolve_mcp_args(profile: str, config: SourceConfig) -> dict[str, Any]:
    args = dict(config.params or {})
    query = (config.query or "").strip()
    tool = _resolve_mcp_tool(profile, config)
    if query and tool in {"search_properties", "find_project", "analyze_listing"}:
        args.setdefault("query", query)
    return args


def _pick_available_tool(profile: str, requested_tool: str, available_tools: list[str], query: str) -> str:
    if not available_tools:
        raise ValueError("The MCP server did not report any callable tools.")
    if requested_tool in available_tools:
        return requested_tool

    requested_norm = _normalize_tool_name(requested_tool)
    normalized_map = {_normalize_tool_name(name): name for name in available_tools}
    if requested_norm in normalized_map:
        return normalized_map[requested_norm]

    value = (query or "").lower()
    preference_groups: list[list[str]] = []
    if profile == "dubai_dld_mcp":
        if "pulse" in value:
            preference_groups.append(["get_market_pulse", "market_pulse", "query_dld"])
        elif "trending" in value or "popular" in value:
            preference_groups.append(["get_trending_projects", "trending_projects", "query_dld"])
        elif "mover" in value:
            preference_groups.append(["get_price_movers", "price_movers", "query_dld"])
        elif "recent" in value:
            preference_groups.append(["get_recent_sales", "recent_sales", "query_dld"])
        else:
            preference_groups.append(["search_properties", "find_project", "query_dld", "search", "search_property"])
    for group in preference_groups:
        for wanted in group:
            wanted_norm = _normalize_tool_name(wanted)
            if wanted_norm in normalized_map:
                return normalized_map[wanted_norm]

    for name in available_tools:
        normalized = _normalize_tool_name(name)
        if "search" in normalized or "list" in normalized or "market" in normalized or "project" in normalized:
            return name
    return available_tools[0]


def _coerce_mcp_args(tool_name: str, tool_args: dict[str, Any], query: str) -> dict[str, Any]:
    args = dict(tool_args)
    if query:
        for field in ("query", "prompt", "text", "search", "request"):
            args.setdefault(field, query)
    normalized = _normalize_tool_name(tool_name)
    if normalized == "querydld":
        args.pop("query", None)
        args.pop("prompt", None)
        args.pop("text", None)
        args.pop("search", None)
        args.pop("request", None)
        args.setdefault("area", _infer_dld_area(query))
        value = query.lower()
        args.setdefault("type", "rentals" if any(token in value for token in ("rent", "rental", "lease")) else "sales")
        if "villa" in value:
            args.setdefault("property_type", "villa")
        elif "townhouse" in value:
            args.setdefault("property_type", "townhouse")
        elif "apartment" in value or "flat" in value:
            args.setdefault("property_type", "apartment")
        else:
            args.setdefault("property_type", "all")
        if "studio" in value:
            args.setdefault("bedrooms", "studio")
        else:
            for candidate in ("1", "2", "3", "4"):
                if f"{candidate}br" in value or f"{candidate} br" in value or f"{candidate}-bed" in value:
                    args.setdefault("bedrooms", candidate)
                    break
            else:
                args.setdefault("bedrooms", "all")
        if "how many" in value or "count" in value:
            args.setdefault("metric", "count")
        elif any(token in value for token in ("recent", "latest", "list", "show")):
            args.setdefault("metric", "list")
        else:
            args.setdefault("metric", "stats")
        args.setdefault("limit", 10)
        return args
    if "findproject" in normalized and query:
        args.setdefault("query", query)
    return args


async def _call_mcp_tool_async(
    *,
    connector_profile: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None,
    tool_name: str,
    tool_args: dict[str, Any],
    query_text: str,
) -> list[dict[str, Any]]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise ValueError("The Python MCP client is not installed. Add the `mcp` package to the API environment.") from exc

    server_params = StdioServerParameters(command=command, args=args, env=env or None)
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            tools = getattr(tools_response, "tools", None) or []
            available_tools = [str(getattr(tool, "name", "")).strip() for tool in tools if getattr(tool, "name", None)]
            resolved_tool = _pick_available_tool(connector_profile, tool_name, available_tools, query_text)
            coerced_args = _coerce_mcp_args(resolved_tool, tool_args, query_text)
            result = await session.call_tool(resolved_tool, coerced_args)
            text_payload = _extract_mcp_text(result)
            if text_payload.lower().startswith("unknown tool"):
                raise ValueError(
                    f"MCP server rejected tool '{resolved_tool}'. Available tools: {', '.join(available_tools) or 'none'}"
                )
            return _extract_mcp_rows(result)


class McpAdapter(SourceAdapter):
    def __init__(self, profile: str) -> None:
        self.profile = profile

    def load_records(self, config: SourceConfig) -> list[dict]:
        defaults = _MCP_DEFAULTS.get(self.profile, {})
        command = (config.mcp_command or defaults.get("command") or "").strip()
        args = list(config.mcp_args or defaults.get("args") or [])
        tool_name = _resolve_mcp_tool(self.profile, config)
        tool_args = _resolve_mcp_args(self.profile, config)

        if not command:
            raise ValueError("This MCP connector requires an mcp_command or a built-in default launcher.")
        if not args:
            raise ValueError("This MCP connector requires mcp_args or a built-in default launcher.")
        if not tool_name:
            raise ValueError("This MCP connector requires an MCP tool name.")
        if shutil.which(command) is None:
            raise ValueError(f"MCP command not found on PATH: {command}")

        try:
            rows = asyncio.run(
                _call_mcp_tool_async(
                    connector_profile=self.profile,
                    command=command,
                    args=args,
                    env=config.mcp_env,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    query_text=config.query or "",
                )
            )
        except RuntimeError as exc:
            raise ValueError(f"MCP execution failed: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"MCP tool call failed: {exc}") from exc

        if not rows:
            return []
        return _normalize_mcp_rows(self.profile, rows)


class GenericRestAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.base_url or not config.access_token:
            raise ValueError("This connector requires base_url and access_token")

        resource = config.object_name or "leads"
        response = httpx.get(
            f"{config.base_url.rstrip('/')}/{resource}",
            headers={"Authorization": f"Bearer {config.access_token}"},
            params=config.params or {},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        for key in ("items", "value", "data", "records"):
            if isinstance(body.get(key), list):
                return body[key]
        return [body]


ADAPTERS: dict[str, SourceAdapter] = {
    "hubspot": HubSpotAdapter(),
    "salesforce": SalesforceAdapter(),
    "dynamics365": DynamicsAdapter(),
    "zoho": ZohoAdapter(),
    "pipedrive": PipedriveAdapter(),
    "freshsales": FreshsalesAdapter(),
    "mondaycrm": MondayAdapter(),
    "odoo": GenericRestAdapter(),
    "netsuite": GenericRestAdapter(),
    "oracle_sales": GenericRestAdapter(),
    "sap_sales_cloud": GenericRestAdapter(),
    "dubai_dld_mcp": McpAdapter("dubai_dld_mcp"),
    "sql": SqlAdapter(),
    "postgres": SqlAdapter("postgres"),
    "supabase": SqlAdapter("supabase"),
    "mysql": SqlAdapter("mysql"),
    "sqlite": SqlAdapter(),
    "mongodb": MongoAdapter("mongodb"),
    "nosql": MongoAdapter(),
    "excel": ExcelAdapter(),
    "csv": CsvAdapter(),
}


def get_adapter(source_type: str) -> SourceAdapter:
    adapter = ADAPTERS.get(source_type.lower())
    if not adapter:
        raise ValueError(f"Unsupported source type: {source_type}")
    return adapter
