from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectorCapability(BaseModel):
    connector_key: str
    supported_entities: list[str] = Field(default_factory=list)
    default_operation: str = "records"
    searchable_fields: list[str] = Field(default_factory=list)
    sortable_fields: list[str] = Field(default_factory=list)
    max_limit: int = 25
    supports_live_query: bool = True


CONNECTOR_CAPABILITIES: dict[str, ConnectorCapability] = {
    "hubspot": ConnectorCapability(
        connector_key="hubspot",
        supported_entities=["Contact", "Company", "Lead"],
        default_operation="contacts",
        searchable_fields=["full_name", "email", "company_name", "industry", "notes"],
        sortable_fields=["full_name", "email", "company_name"],
        max_limit=50,
    ),
    "zoho": ConnectorCapability(
        connector_key="zoho",
        supported_entities=["Contact", "Company", "Lead"],
        default_operation="leads",
        searchable_fields=["full_name", "email", "company_name", "industry", "notes"],
        sortable_fields=["full_name", "email", "company_name"],
        max_limit=50,
    ),
    "mondaycrm": ConnectorCapability(
        connector_key="mondaycrm",
        supported_entities=["Lead", "Task", "Record"],
        default_operation="records",
        searchable_fields=["title", "summary", "company_name", "full_name", "email", "notes"],
        sortable_fields=["title", "company_name", "full_name"],
        max_limit=50,
    ),
    "salesforce": ConnectorCapability(
        connector_key="salesforce",
        supported_entities=["Contact", "Company", "Lead"],
        default_operation="leads",
        searchable_fields=["full_name", "email", "company_name", "industry", "notes"],
        sortable_fields=["full_name", "email", "company_name"],
        max_limit=50,
    ),
    "dynamics365": ConnectorCapability(
        connector_key="dynamics365",
        supported_entities=["Lead", "Contact", "Company"],
        default_operation="leads",
        searchable_fields=["full_name", "email", "company_name", "industry", "notes"],
        sortable_fields=["full_name", "email", "company_name"],
        max_limit=50,
    ),
    "pipedrive": ConnectorCapability(
        connector_key="pipedrive",
        supported_entities=["Lead", "Contact", "Record"],
        default_operation="leads",
        searchable_fields=["full_name", "email", "company_name", "notes"],
        sortable_fields=["full_name", "company_name"],
        max_limit=50,
    ),
    "freshsales": ConnectorCapability(
        connector_key="freshsales",
        supported_entities=["Lead", "Contact", "Record"],
        default_operation="leads",
        searchable_fields=["full_name", "email", "company_name", "notes"],
        sortable_fields=["full_name", "company_name"],
        max_limit=50,
    ),
    "dubai_dld_mcp": ConnectorCapability(
        connector_key="dubai_dld_mcp",
        supported_entities=["Property", "Project", "Record"],
        default_operation="records",
        searchable_fields=["title", "summary", "subtitle", "community", "building", "project_name"],
        sortable_fields=["title", "community", "price"],
        max_limit=25,
    ),
}


def get_connector_capability(connector_key: str) -> ConnectorCapability:
    key = (connector_key or "").strip().lower()
    if key in CONNECTOR_CAPABILITIES:
        return CONNECTOR_CAPABILITIES[key]
    return ConnectorCapability(
        connector_key=key or "unknown",
        supported_entities=["Record"],
        default_operation="records",
        searchable_fields=["title", "summary", "notes"],
        sortable_fields=["title"],
        max_limit=25,
        supports_live_query=True,
    )
