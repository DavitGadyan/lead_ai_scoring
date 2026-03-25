from __future__ import annotations

import re
from io import BytesIO

import pandas as pd

from .adapters import browse_hubspot_object, get_adapter
from .db import get_conn
from .providers import PROVIDERS
from .schemas import (
    ImportResult,
    LeadCanonical,
    LeadScoreOut,
    LeadScoreRecord,
    PostgresSyncRequest,
    SourceConfig,
    SourceIn,
    ProviderDefinition,
    SourceRecord,
    SourceSyncResult,
    SourceTestResult,
    HubSpotPreviewResponse,
    HubSpotBrowseRequest,
    HubSpotBrowseResponse,
)
from .scoring import score_lead

FIELD_ALIASES = {
    "external_id": {"externalid", "external_id", "id", "leadid", "lead_id", "crm_id"},
    "full_name": {"name", "full_name", "fullname", "contactname", "contact_name", "displayname"},
    "email": {"email", "workemail", "work_email", "emailaddress", "email_address", "primaryemail"},
    "company": {"company", "companyname", "company_name", "account", "organization", "accountname"},
    "job_title": {"jobtitle", "job_title", "title", "role", "position"},
    "industry": {"industry", "vertical", "sector", "industryname"},
    "country": {"country", "region_country", "locationcountry", "countryregion"},
    "employee_count": {"employee_count", "employeecount", "employees", "team_size", "companysize", "numberofemployees"},
    "annual_revenue": {"annual_revenue", "annualrevenue", "revenue", "arr", "company_revenue", "annualincome"},
    "budget_range": {"budget_range", "budgetrange", "budget", "estimatedbudget", "spend_range"},
    "notes": {"notes", "description", "summary", "painpoints", "pain_points", "usecase", "use_case", "leadsource"},
    "lifecycle_stage": {"lifecyclestage", "lifecycle_stage", "customerstage", "journeystage"},
    "lead_status": {"leadstatus", "lead_status", "status", "dealstage", "pipeline_stage"},
    "owner_name": {"owner", "owner_name", "leadowner", "accountowner", "salesrep"},
    "last_activity_at": {"lastactivityat", "last_activity_at", "lasttouch", "lastengagementdate", "last_contacted_at"},
    "days_since_last_activity": {"days_since_last_activity", "dayssincelastactivity", "inactivedays"},
    "engagement_score": {"engagementscore", "engagement_score", "engagement"},
    "health_score": {"healthscore", "health_score", "accounthealth"},
    "product_usage_score": {"productusagescore", "product_usage_score", "usage_score"},
    "support_ticket_count": {"supportticketcount", "support_ticket_count", "ticketcount", "open_tickets"},
    "nps_score": {"nps", "npsscore", "nps_score"},
    "contract_value": {"contractvalue", "contract_value", "mrr", "arrvalue", "dealvalue"},
    "renewal_date": {"renewaldate", "renewal_date", "contractrenewaldate"},
    "conversion_likelihood": {"conversionlikelihood", "conversion_likelihood", "win_probability"},
    "churn_risk": {"churnrisk", "churn_risk", "attritionrisk"},
}

CANONICAL_FIELDS = [
    "external_id",
    "full_name",
    "email",
    "company",
    "job_title",
    "industry",
    "country",
    "employee_count",
    "annual_revenue",
    "budget_range",
    "notes",
    "lifecycle_stage",
    "lead_status",
    "owner_name",
    "last_activity_at",
    "days_since_last_activity",
    "engagement_score",
    "health_score",
    "product_usage_score",
    "support_ticket_count",
    "nps_score",
    "contract_value",
    "renewal_date",
    "conversion_likelihood",
    "churn_risk",
]


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def sanitize_source_record(source: SourceRecord) -> SourceRecord:
    sanitized_config = source.config.model_copy(
        update={
            "connection_url": _mask_secret(source.config.connection_url),
            "access_token": _mask_secret(source.config.access_token),
            "refresh_token": _mask_secret(source.config.refresh_token),
            "api_key": _mask_secret(source.config.api_key),
            "client_secret": _mask_secret(source.config.client_secret),
            "mcp_env": {key: _mask_secret(value) for key, value in (source.config.mcp_env or {}).items()} or None,
        }
    )
    return source.model_copy(update={"config": sanitized_config})


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _guess_target_field(source_field: str) -> str | None:
    normalized_source = _normalize_field_name(source_field)
    for target, aliases in FIELD_ALIASES.items():
        if normalized_source == _normalize_field_name(target):
            return target
        if normalized_source in {_normalize_field_name(alias) for alias in aliases}:
            return target
    return None


_STRING_CANONICAL_FIELDS = {
    "external_id",
    "full_name",
    "email",
    "company",
    "job_title",
    "industry",
    "country",
    "budget_range",
    "notes",
    "lifecycle_stage",
    "lead_status",
    "owner_name",
    "last_activity_at",
    "renewal_date",
}


def _stringify_mapping(value: dict[object, object]) -> str | None:
    preferred_keys = ("name", "full_name", "display_name", "email", "value")
    for key in preferred_keys:
        candidate = value.get(key)
        if candidate not in (None, ""):
            return str(candidate)
    parts = [str(candidate) for candidate in value.values() if candidate not in (None, "", [], {})]
    return ", ".join(parts) if parts else None


def _coerce_canonical_value(target: str, value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict):
        if target in _STRING_CANONICAL_FIELDS:
            return _stringify_mapping(value)
        return None
    if isinstance(value, list):
        if target in _STRING_CANONICAL_FIELDS:
            parts = []
            for item in value:
                if isinstance(item, dict):
                    rendered = _stringify_mapping(item)
                elif item not in (None, ""):
                    rendered = str(item)
                else:
                    rendered = None
                if rendered:
                    parts.append(rendered)
            return ", ".join(parts) if parts else None
        return None
    return value


def normalize_records(records: list[dict], *, source_type: str, source_name: str) -> list[LeadCanonical]:
    leads: list[LeadCanonical] = []
    for record in records:
        lowered = {_normalize_field_name(str(key)): value for key, value in record.items()}
        normalized: dict[str, object | None] = {}
        for key, value in record.items():
            target = _guess_target_field(str(key))
            if target and normalized.get(target) in {None, ""}:
                normalized[target] = _coerce_canonical_value(target, value)
        if not normalized.get("full_name"):
            first_name = lowered.get("firstname")
            last_name = lowered.get("lastname")
            if first_name or last_name:
                normalized["full_name"] = " ".join(part for part in [first_name, last_name] if part)
        for field in CANONICAL_FIELDS:
            normalized.setdefault(field, None)
        normalized["source_type"] = source_type
        normalized["source_name"] = source_name
        leads.append(LeadCanonical.model_validate(normalized))
    return leads


def parse_excel(content: bytes, *, source_name: str) -> list[LeadCanonical]:
    frame = pd.read_excel(BytesIO(content))
    records = frame.to_dict(orient="records")
    return normalize_records(records, source_type="excel", source_name=source_name)


def parse_csv(content: bytes, *, source_name: str) -> list[LeadCanonical]:
    frame = pd.read_csv(BytesIO(content))
    records = frame.to_dict(orient="records")
    return normalize_records(records, source_type="csv", source_name=source_name)


def preview_uploaded_file(content: bytes, *, filename: str) -> SourceTestResult:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        source_type = "csv"
        sample = parse_csv(content, source_name=filename)[:25]
    elif lowered.endswith(".xlsx") or lowered.endswith(".xls"):
        source_type = "excel"
        sample = parse_excel(content, source_name=filename)[:25]
    else:
        raise ValueError("Only .xlsx, .xls, and .csv files are supported")

    preview_rows = [row.model_dump() for row in sample]
    sample_fields = sorted(
        {str(key) for row in sample for key, value in row.model_dump().items() if value not in (None, "")}
    )
    return SourceTestResult(
        source_type=source_type,
        connection_ok=True,
        sample_count=len(sample),
        sample_fields=sample_fields,
        normalized_fields=CANONICAL_FIELDS,
        preview_rows=preview_rows,
    )


def parse_postgres_sync(payload: PostgresSyncRequest) -> list[LeadCanonical]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(payload.query)
            rows = cur.fetchall()
    return normalize_records(rows, source_type="postgres", source_name=payload.source_name)


def ingest_from_source(source: SourceRecord) -> list[LeadCanonical]:
    adapter = get_adapter(source.source_type)
    records = adapter.load_records(source.config)
    return normalize_records(records, source_type=source.source_type, source_name=source.name)


def persist_lead_and_score(lead: LeadCanonical) -> LeadScoreOut:
    result = score_lead(lead)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into lead_raw_imports (source_type, source_name, external_id, payload_row, status)
                values (%s, %s, %s, %s::jsonb, %s)
                returning id
                """,
                (
                    lead.source_type,
                    lead.source_name,
                    lead.external_id,
                    lead.model_dump_json(),
                    "processed",
                ),
            )
            raw_import_id = cur.fetchone()["id"]

            cur.execute(
                """
                insert into leads_normalized (
                    raw_import_id, full_name, email, company, job_title, industry,
                    country, employee_count, annual_revenue, budget_range, notes, source_name
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    raw_import_id,
                    lead.full_name,
                    str(lead.email) if lead.email else None,
                    lead.company,
                    lead.job_title,
                    lead.industry,
                    lead.country,
                    lead.employee_count,
                    lead.annual_revenue,
                    lead.budget_range,
                    lead.notes,
                    lead.source_name,
                ),
            )
            lead_id = cur.fetchone()["id"]

            cur.execute(
                """
                insert into lead_scores (
                    lead_id, fit_score, intent_score, urgency_score, budget_score, authority_score,
                    overall_score, recommended_action, explanation
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lead_id,
                    result.breakdown.fit_score,
                    result.breakdown.intent_score,
                    result.breakdown.urgency_score,
                    result.breakdown.budget_score,
                    result.breakdown.authority_score,
                    result.overall_score,
                    result.recommended_action,
                    result.explanation,
                ),
            )
        conn.commit()

    return LeadScoreOut(
        lead_id=str(lead_id),
        overall_score=result.overall_score,
        directional_score=result.directional_score,
        recommended_action=result.recommended_action,
        explanation=result.explanation,
        breakdown=result.breakdown,
    )


def persist_batch(leads: list[LeadCanonical]) -> list[LeadScoreOut]:
    return [persist_lead_and_score(lead) for lead in leads]


def build_import_result(leads: list[LeadCanonical], *, source_type: str, source_name: str) -> ImportResult:
    return ImportResult(imported=len(leads), source_name=source_name, source_type=source_type)


def create_source(payload: SourceIn) -> SourceRecord:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into data_sources (name, source_type, config, is_active)
                values (%s, %s, %s::jsonb, %s)
                returning id, created_at
                """,
                (
                    payload.name,
                    payload.source_type,
                    payload.config.model_dump_json(),
                    payload.is_active,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    source = SourceRecord(
        id=str(row["id"]),
        name=payload.name,
        source_type=payload.source_type,
        config=payload.config,
        is_active=payload.is_active,
        created_at=row["created_at"],
        last_synced_at=None,
    )
    return sanitize_source_record(source)


def list_sources() -> list[SourceRecord]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, name, source_type, config, is_active, last_synced_at, created_at
                from data_sources
                order by created_at desc
                """
            )
            rows = cur.fetchall()

    return [
        sanitize_source_record(
            SourceRecord(
            id=str(row["id"]),
            name=row["name"],
            source_type=row["source_type"],
            config=row["config"],
            is_active=row["is_active"],
            last_synced_at=row["last_synced_at"],
            created_at=row["created_at"],
            )
        )
        for row in rows
    ]


def list_provider_definitions() -> list[ProviderDefinition]:
    return sorted(PROVIDERS, key=lambda provider: provider.recommended_order)


def get_source(source_id: str) -> SourceRecord:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, name, source_type, config, is_active, last_synced_at, created_at
                from data_sources
                where id = %s
                """,
                (source_id,),
            )
            row = cur.fetchone()

    if not row:
        raise ValueError(f"Source not found: {source_id}")

    return SourceRecord(
        id=str(row["id"]),
        name=row["name"],
        source_type=row["source_type"],
        config=row["config"],
        is_active=row["is_active"],
        last_synced_at=row["last_synced_at"],
        created_at=row["created_at"],
    )


def sync_source(source_id: str) -> SourceSyncResult:
    source = get_source(source_id)
    leads = ingest_from_source(source)
    persist_batch(leads)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update data_sources
                set last_synced_at = now()
                where id = %s
                """,
                (source_id,),
            )
        conn.commit()

    return SourceSyncResult(
        source_id=source_id,
        imported=len(leads),
        source_name=source.name,
        source_type=source.source_type,
    )


def test_source(payload: SourceIn) -> SourceTestResult:
    source = SourceRecord(
        id="preview",
        name=payload.name,
        source_type=payload.source_type,
        config=payload.config,
        is_active=payload.is_active,
        created_at=pd.Timestamp.utcnow().to_pydatetime(),
        last_synced_at=None,
    )
    if payload.source_type == "dubai_dld_mcp":
        raw_records = get_adapter(payload.source_type).load_records(payload.config)
        sample = raw_records[:25]
        preview_rows = [row for row in sample if isinstance(row, dict)]
        sample_fields = sorted({str(key) for row in preview_rows for key, value in row.items() if value not in (None, "")})
        normalized_fields = sorted({field for row in preview_rows for field in row.keys()})
    else:
        records = ingest_from_source(source)
        sample = records[:25]
        preview_rows = [row.model_dump() for row in sample]
        sample_fields = sorted(
            {str(key) for row in sample for key, value in row.model_dump().items() if value not in (None, "")}
        )
        normalized_fields = CANONICAL_FIELDS

    return SourceTestResult(
        source_type=payload.source_type,
        connection_ok=True,
        sample_count=len(sample),
        sample_fields=sample_fields,
        normalized_fields=normalized_fields,
        preview_rows=preview_rows,
    )


def preview_hubspot_source(payload: SourceIn) -> HubSpotPreviewResponse:
    if payload.source_type != "hubspot":
        raise ValueError("HubSpot preview only supports source_type='hubspot'")

    source = SourceRecord(
        id="hubspot-preview",
        name=payload.name,
        source_type=payload.source_type,
        config=payload.config,
        is_active=payload.is_active,
        created_at=pd.Timestamp.utcnow().to_pydatetime(),
        last_synced_at=None,
    )
    records = ingest_from_source(source)
    sample = records[:5]
    preview_rows = [row.model_dump() for row in sample]
    sample_fields = sorted({str(key) for row in sample for key, value in row.model_dump().items() if value not in (None, "")})

    return HubSpotPreviewResponse(
        source_type=payload.source_type,
        connection_ok=True,
        sample_count=len(sample),
        sample_fields=sample_fields,
        normalized_fields=CANONICAL_FIELDS,
        records=sample,
        preview_rows=preview_rows,
    )


def browse_hubspot(payload: HubSpotBrowseRequest) -> HubSpotBrowseResponse:
    config = SourceConfig(
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
    )
    body = browse_hubspot_object(config, payload.object_name, payload.after, payload.limit)
    raw_records = body.get("results", [])
    records = [item.get("properties", {}) | {"id": item.get("id")} for item in raw_records]
    next_after = body.get("paging", {}).get("next", {}).get("after")

    return HubSpotBrowseResponse(
        object_name=payload.object_name,
        records=records,
        current_after=payload.after,
        next_after=str(next_after) if next_after is not None else None,
        limit=payload.limit,
    )


def list_recent_scores(limit: int = 20) -> list[LeadScoreRecord]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    leads_normalized.id as lead_id,
                    leads_normalized.company,
                    leads_normalized.email,
                    leads_normalized.source_name,
                    lead_scores.overall_score,
                    lead_scores.recommended_action,
                    lead_scores.explanation,
                    lead_scores.fit_score,
                    lead_scores.intent_score,
                    lead_scores.urgency_score,
                    lead_scores.budget_score,
                    lead_scores.authority_score,
                    lead_scores.scored_at as created_at
                from lead_scores
                join leads_normalized on leads_normalized.id = lead_scores.lead_id
                order by lead_scores.scored_at desc
                limit %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [
        LeadScoreRecord(
            lead_id=str(row["lead_id"]),
            company=row["company"],
            email=row["email"],
            source_name=row["source_name"],
            overall_score=float(row["overall_score"]),
            recommended_action=row["recommended_action"],
            explanation=row["explanation"],
            created_at=row["created_at"],
            breakdown={
                "fit_score": row["fit_score"],
                "intent_score": row["intent_score"],
                "urgency_score": row["urgency_score"],
                "budget_score": row["budget_score"],
                "authority_score": row["authority_score"],
            },
        )
        for row in rows
    ]
