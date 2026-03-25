from __future__ import annotations

from typing import Any

from .connector_capabilities import get_connector_capability

GRAPHQL_OPERATIONS: dict[str, dict[str, Any]] = {
    "contacts": {
        "entity": "Contact",
        "fields": {
            "id",
            "fullName",
            "email",
            "title",
            "companyName",
            "source",
            "sourceId",
            "sourceName",
            "lastUpdatedAt",
            "summary",
        },
    },
    "companies": {
        "entity": "Company",
        "fields": {
            "id",
            "name",
            "domain",
            "industry",
            "employeeCount",
            "source",
            "sourceId",
            "sourceName",
            "lastUpdatedAt",
            "summary",
        },
    },
    "leads": {
        "entity": "Lead",
        "fields": {
            "id",
            "status",
            "score",
            "fullName",
            "email",
            "companyName",
            "source",
            "sourceId",
            "sourceName",
            "lastUpdatedAt",
            "summary",
        },
    },
    "records": {
        "entity": "Record",
        "fields": {
            "id",
            "entityType",
            "title",
            "subtitle",
            "summary",
            "source",
            "sourceId",
            "sourceName",
            "lastUpdatedAt",
        },
    },
}


def get_schema_summary(connector_keys: list[str]) -> dict[str, Any]:
    connectors = []
    for key in connector_keys:
        cap = get_connector_capability(key)
        connectors.append(
            {
                "connector": cap.connector_key,
                "supported_entities": cap.supported_entities,
                "default_operation": cap.default_operation,
                "searchable_fields": cap.searchable_fields,
                "max_limit": cap.max_limit,
            }
        )
    return {
        "operations": {
            name: {"entity": spec["entity"], "fields": sorted(spec["fields"])}
            for name, spec in GRAPHQL_OPERATIONS.items()
        },
        "connectors": connectors,
    }


def allowed_fields_for_operation(operation: str) -> set[str]:
    spec = GRAPHQL_OPERATIONS.get(operation)
    if not spec:
        return set()
    return set(spec["fields"])


def build_graphql_query(operation: str, fields: list[str], filters: dict[str, Any]) -> str:
    if operation not in GRAPHQL_OPERATIONS:
        raise ValueError(f"Unsupported operation: {operation}")

    filter_parts: list[str] = []
    for key, value in filters.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            items = ", ".join(f'"{str(item)}"' for item in value)
            filter_parts.append(f'{key}: [{items}]')
        elif isinstance(value, str):
            filter_parts.append(f'{key}: "{value}"')
        else:
            filter_parts.append(f"{key}: {value}")
    filters_text = f"({', '.join(filter_parts)})" if filter_parts else ""
    fields_text = "\n    ".join(fields)
    return f"query LeadScoreQuery {{\n  {operation}{filters_text} {{\n    {fields_text}\n  }}\n}}"
