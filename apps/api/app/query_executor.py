from __future__ import annotations
# pylint: disable=broad-exception-caught

from datetime import datetime
from math import ceil
from typing import Any

from .adapters import get_adapter
from .graphql_schema import build_graphql_query
from .memory import get_connector_dataset, list_connectors_with_data
from .query_validator import validate_query_plan
from .schemas import (
    CanonicalRecord,
    CanonicalSourceRef,
    QueryExecutionTrace,
    QueryPlan,
    SourceRecord,
    WorkspaceMemoryState,
)
from .services import _normalize_field_name, get_source
from .session_cache import build_query_cache_key, get_session_cache, set_session_cache


def _safe_scalar_dict(row: dict[str, Any], limit: int = 18) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if len(out) >= limit:
            break
        if value is None or isinstance(value, (str, int, float, bool)):
            out[str(key)] = value
    return out


def _value_lookup(row: dict[str, Any], *aliases: str) -> Any:
    normalized = {_normalize_field_name(str(k)): v for k, v in row.items()}
    for alias in aliases:
        value = normalized.get(_normalize_field_name(alias))
        if value not in (None, ""):
            return value
    return None


def _build_source_ref(source: SourceRecord, row: dict[str, Any]) -> CanonicalSourceRef:
    source_id = str(
        _value_lookup(row, "source_id", "external_id", "id", "record_id", "crm_id")
        or row.get("id")
        or row.get("external_id")
        or "unknown"
    )
    return CanonicalSourceRef(
        connector=source.source_type,
        source_id=source_id,
        source_name=source.name,
        last_synced_at=source.last_synced_at,
    )


def _updated_at(row: dict[str, Any]) -> datetime | None:
    raw = _value_lookup(row, "updated_at", "lastmodified", "lastmodifieddate", "modifiedtime", "createdate")
    if isinstance(raw, datetime):
        return raw
    return None


def _record_from_row(row: dict[str, Any], source: SourceRecord, operation: str) -> CanonicalRecord:
    source_ref = _build_source_ref(source, row)
    full_name = _value_lookup(row, "full_name", "name", "firstname", "lastname", "displayname", "question", "project_name")
    email = _value_lookup(row, "email", "workemail", "primaryemail")
    company_name = _value_lookup(
        row,
        "company",
        "companyname",
        "accountname",
        "organization",
        "board_name",
        "community",
        "category",
    )
    title = _value_lookup(row, "job_title", "title", "role", "position", "project", "market", "question")
    industry = _value_lookup(row, "industry", "vertical", "sector", "property_type")
    status = _value_lookup(row, "status", "leadstatus", "stage")
    domain = _value_lookup(row, "domain", "website")
    score = _value_lookup(row, "score", "leadscore")
    custom_subtitle = _value_lookup(row, "subtitle")
    custom_summary = _value_lookup(row, "summary", "description", "details", "notes", "analysis")

    if operation == "contacts":
        heading = str(full_name or email or company_name or source_ref.source_id)
        subtitle = " | ".join(str(part) for part in [email, title, company_name] if part)
        summary = custom_summary or " | ".join(str(part) for part in [industry, status] if part) or None
        entity_type = "Contact"
    elif operation == "companies":
        heading = str(company_name or domain or full_name or source_ref.source_id)
        subtitle = " | ".join(str(part) for part in [domain, industry, title] if part)
        summary = custom_summary or " | ".join(str(part) for part in [email, status] if part) or None
        entity_type = "Company"
    elif operation == "leads":
        heading = str(full_name or company_name or email or source_ref.source_id)
        subtitle = " | ".join(str(part) for part in [email, company_name, status] if part)
        summary = custom_summary or " | ".join(str(part) for part in [title, industry, score] if part) or None
        entity_type = "Lead"
    else:
        heading = str(title or full_name or company_name or row.get("name") or source_ref.source_id)
        subtitle = custom_subtitle or " | ".join(str(part) for part in [email, company_name, status] if part)
        summary = custom_summary or " | ".join(str(part) for part in [title, industry] if part) or None
        entity_type = "Record"

    data = _safe_scalar_dict(row)
    data.setdefault("full_name", full_name)
    data.setdefault("email", email)
    data.setdefault("company_name", company_name)
    data.setdefault("title", title)
    data.setdefault("industry", industry)
    data.setdefault("domain", domain)
    data.setdefault("status", status)
    data.setdefault("score", score)

    return CanonicalRecord(
        id=f"{source.source_type}:{source_ref.source_id}",
        entity_type=entity_type,
        title=heading,
        subtitle=subtitle or None,
        summary=summary,
        source=source_ref,
        data=data,
    )


def _matches_search(record: CanonicalRecord, search: str | None) -> bool:
    if not search:
        return True
    haystacks = [record.title, record.subtitle or "", record.summary or ""]
    haystacks.extend(str(v) for v in record.data.values() if v is not None)
    value = " ".join(haystacks).lower()
    return search.lower() in value


def _matches_filters(record: CanonicalRecord, plan: QueryPlan) -> bool:
    filters = plan.filters or {}
    if not _matches_search(record, filters.get("search")):
        return False
    status = filters.get("status")
    if status:
        record_status = str(record.data.get("status") or "").lower()
        if status.lower() not in record_status:
            return False
    return True


def _config_for_operation(source: SourceRecord, operation: str, limit: int) -> SourceRecord:
    config = source.config.model_copy(deep=True)
    params = dict(config.params or {})

    if source.source_type == "hubspot":
        config.object_name = {
            "contacts": "contacts",
            "companies": "companies",
            "leads": "leads",
        }.get(operation, config.object_name or "contacts")
        params["limit"] = limit
        config.params = params
    elif source.source_type == "zoho":
        config.object_name = {
            "contacts": "Contacts",
            "companies": "Accounts",
            "leads": "Leads",
        }.get(operation, config.object_name or "Leads")
        params["per_page"] = limit
        config.params = params
    elif source.source_type == "mondaycrm":
        params["limit"] = limit
        config.params = params
    elif source.source_type == "dynamics365":
        config.object_name = {
            "contacts": "contacts",
            "companies": "accounts",
            "leads": "leads",
        }.get(operation, config.object_name or "leads")
        params["$top"] = limit
        config.params = params
    elif source.source_type == "pipedrive":
        config.object_name = {
            "contacts": "persons",
            "companies": "organizations",
            "leads": "leads",
        }.get(operation, config.object_name or "leads")
    elif source.source_type == "freshsales":
        config.object_name = {
            "contacts": "contacts",
            "companies": "accounts",
            "leads": "leads",
        }.get(operation, config.object_name or "leads")
    elif source.source_type == "dubai_dld_mcp":
        params["limit"] = limit
        config.params = params
    return source.model_copy(update={"config": config})


def _resolve_live_sources(memory: WorkspaceMemoryState) -> list[SourceRecord]:
    live: list[SourceRecord] = []
    for item in memory.sources:
        source_id = str(item.get("id") or "").strip()
        if not source_id:
            try:
                live.append(SourceRecord.model_validate(item))
            except Exception:
                continue
            continue
        try:
            live.append(get_source(source_id))
        except Exception:
            try:
                live.append(SourceRecord.model_validate(item))
            except Exception:
                continue
    deduped: dict[str, SourceRecord] = {}
    for source in live:
        deduped[source.id] = source
    return list(deduped.values())


def _records_from_preview(memory: WorkspaceMemoryState, connector_key: str, plan: QueryPlan) -> list[CanonicalRecord]:
    blob = get_connector_dataset(memory, connector_key)
    if blob is None:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(blob, dict):
        for key in ("contacts", "companies", "records"):
            value = blob.get(key)
            if isinstance(value, list):
                rows.extend([row for row in value if isinstance(row, dict)])
    elif isinstance(blob, list):
        rows = [row for row in blob if isinstance(row, dict)]

    preview_source = SourceRecord(
        id=f"preview-{connector_key}",
        name=f"{connector_key}-preview",
        source_type=connector_key,
        config={},
        is_active=True,
        created_at=datetime.utcnow(),
        last_synced_at=None,
    )
    out = [_record_from_row(row, preview_source, plan.operation) for row in rows]
    return [record for record in out if _matches_filters(record, plan)][: plan.limit]


def _merge_records_by_source(
    records_by_source: dict[str, list[CanonicalRecord]],
    source_order: list[str],
    limit: int,
) -> list[CanonicalRecord]:
    merged: list[CanonicalRecord] = []
    index = 0
    while len(merged) < limit:
        appended = False
        for source_key in source_order:
            bucket = records_by_source.get(source_key) or []
            if index < len(bucket):
                merged.append(bucket[index])
                appended = True
                if len(merged) >= limit:
                    break
        if not appended:
            break
        index += 1
    return merged


def execute_query_plan(
    *,
    session_id: str,
    memory: WorkspaceMemoryState,
    plan: QueryPlan,
) -> tuple[list[CanonicalRecord], QueryExecutionTrace]:
    live_sources = _resolve_live_sources(memory)
    session_source_types = sorted(
        {
            *(source.source_type for source in live_sources),
            *list_connectors_with_data(memory),
            *(key.strip().lower() for key in plan.sources or [] if key.strip()),
        }
    )
    selected_sources = [source for source in live_sources if source.source_type in set(plan.sources or [])]
    validated = validate_query_plan(plan, session_source_types or [source.source_type for source in live_sources])
    query_text = build_graphql_query(validated.operation, validated.fields, validated.filters)

    cache_key = build_query_cache_key(
        session_id,
        {
            "operation": validated.operation,
            "fields": validated.fields,
            "filters": validated.filters,
            "sources": validated.sources,
        },
    )
    cached = get_session_cache(cache_key)
    if cached:
        records = [CanonicalRecord.model_validate(item) for item in cached.get("records", [])]
        return records, QueryExecutionTrace(
            cache_hit=True,
            executed_query=query_text,
            result_count=len(records),
            validated_operation=validated.operation,
            validated_sources=validated.sources,
        )

    fetched_sources = selected_sources or [source for source in live_sources if source.source_type in validated.sources]
    source_order = list(dict.fromkeys(validated.sources))
    per_source_limit = validated.limit
    if len(source_order) > 1:
        per_source_limit = max(2, ceil(validated.limit / max(1, len(source_order))))

    records_by_source: dict[str, list[CanonicalRecord]] = {source_key: [] for source_key in source_order}
    live_source_map = {source.source_type: source for source in fetched_sources}

    for source_key in source_order:
        source = live_source_map.get(source_key)
        live_records: list[CanonicalRecord] = []
        if source is None:
            records_by_source[source_key] = _records_from_preview(memory, source_key, validated)[:per_source_limit]
            continue
        try:
            configured = _config_for_operation(source, validated.operation, per_source_limit)
            raw_rows = get_adapter(source.source_type).load_records(configured.config)
        except Exception:
            raw_rows = []

        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            record = _record_from_row(row, source, validated.operation)
            if _matches_filters(record, validated):
                live_records.append(record)
                if len(live_records) >= per_source_limit:
                    break
        if len(live_records) < per_source_limit:
            preview_records = _records_from_preview(memory, source_key, validated)
            live_ids = {record.id for record in live_records}
            for preview_record in preview_records:
                if preview_record.id in live_ids:
                    continue
                live_records.append(preview_record)
                if len(live_records) >= per_source_limit:
                    break
        records_by_source[source_key] = live_records

    result_records = _merge_records_by_source(records_by_source, source_order, validated.limit)
    set_session_cache(
        cache_key,
        {"records": [record.model_dump(mode="json") for record in result_records]},
    )
    return result_records, QueryExecutionTrace(
        cache_hit=False,
        executed_query=query_text,
        result_count=len(result_records),
        validated_operation=validated.operation,
        validated_sources=validated.sources,
    )
