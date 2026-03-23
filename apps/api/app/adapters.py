from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
import pandas as pd
from pymongo import MongoClient
from sqlalchemy import create_engine, text

from .oauth import refresh_hubspot_token
from .schemas import SourceConfig


class SourceAdapter(ABC):
    @abstractmethod
    def load_records(self, config: SourceConfig) -> list[dict]:
        raise NotImplementedError


class SqlAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.connection_url or not config.query:
            raise ValueError("SQL sources require connection_url and query")

        engine = create_engine(config.connection_url)
        with engine.connect() as connection:
            rows = connection.execute(text(config.query))
            return [dict(row._mapping) for row in rows]


class MongoAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.connection_url or not config.database or not config.collection:
            raise ValueError("MongoDB sources require connection_url, database, and collection")

        client = MongoClient(config.connection_url)
        collection = client[config.database][config.collection]
        cursor = collection.find(config.filter or {}, {"_id": 0})
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


class ZohoAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.access_token:
            raise ValueError("Zoho requires access_token")

        base_url = (config.base_url or "https://www.zohoapis.com").rstrip("/")
        module = config.object_name or "Leads"
        response = httpx.get(
            f"{base_url}/crm/v2/{module}",
            headers={"Authorization": f"Zoho-oauthtoken {config.access_token}"},
            params=config.params or {"per_page": 100},
            timeout=30.0,
        )
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


class MondayAdapter(SourceAdapter):
    def load_records(self, config: SourceConfig) -> list[dict]:
        if not config.access_token or not config.query:
            raise ValueError("monday CRM requires access_token and query")

        response = httpx.post(
            "https://api.monday.com/v2",
            headers={"Authorization": config.access_token},
            json={"query": config.query},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json().get("data", {})
        return [data] if data else []


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
    "sql": SqlAdapter(),
    "postgres": SqlAdapter(),
    "supabase": SqlAdapter(),
    "mysql": SqlAdapter(),
    "sqlite": SqlAdapter(),
    "mongodb": MongoAdapter(),
    "nosql": MongoAdapter(),
    "excel": ExcelAdapter(),
    "csv": CsvAdapter(),
}


def get_adapter(source_type: str) -> SourceAdapter:
    adapter = ADAPTERS.get(source_type.lower())
    if not adapter:
        raise ValueError(f"Unsupported source type: {source_type}")
    return adapter
