from __future__ import annotations

from typing import Iterable

from .connector_capabilities import get_connector_capability
from .graphql_schema import GRAPHQL_OPERATIONS, allowed_fields_for_operation
from .schemas import QueryPlan, SourceRecord

MAX_QUERY_FIELDS = 10
MAX_QUERY_DEPTH = 2


def _validate_fields(operation: str, fields: list[str]) -> list[str]:
    allowed = allowed_fields_for_operation(operation)
    clean: list[str] = []
    for field in fields:
        if field in allowed and field not in clean:
            clean.append(field)
    if not clean:
        clean = sorted(list(allowed))[:6]
    return clean[:MAX_QUERY_FIELDS]


def _extract_source_types(sources: Iterable[SourceRecord | str]) -> set[str]:
    allowed: set[str] = set()
    for source in sources:
        if isinstance(source, str):
            value = source.strip().lower()
        else:
            value = source.source_type.strip().lower()
        if value:
            allowed.add(value)
    return allowed


def validate_query_plan(plan: QueryPlan, sources: list[SourceRecord] | list[str]) -> QueryPlan:
    if plan.operation not in GRAPHQL_OPERATIONS:
        raise ValueError(f"Unsupported query operation: {plan.operation}")
    if "mutation" in plan.reasoning.lower() if plan.reasoning else False:
        raise ValueError("Mutations are not allowed in retrieval plans")

    allowed_source_types = _extract_source_types(sources)
    if allowed_source_types:
        selected_sources = [source for source in plan.sources if source in allowed_source_types]
        if not selected_sources:
            selected_sources = sorted(allowed_source_types)
    else:
        selected_sources = list(dict.fromkeys(plan.sources))

    max_limit = 20
    for source_key in selected_sources:
        capability = get_connector_capability(source_key)
        max_limit = min(max_limit, capability.max_limit)
    limit = max(1, min(plan.limit or 10, max_limit))

    filters = dict(plan.filters)
    filters["limit"] = limit
    filters["source"] = selected_sources

    # Best-effort protection against deep selection strings.
    for field in plan.fields:
        if field.count("{") >= MAX_QUERY_DEPTH:
            raise ValueError("Query depth exceeded")

    return plan.model_copy(
        update={
            "fields": _validate_fields(plan.operation, plan.fields),
            "sources": selected_sources,
            "filters": filters,
            "limit": limit,
        }
    )
