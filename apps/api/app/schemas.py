from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeadCanonical(BaseModel):
    external_id: str | None = None
    full_name: str | None = None
    email: str | None = None
    company: str | None = None
    job_title: str | None = None
    industry: str | None = None
    country: str | None = None
    employee_count: int | None = Field(default=None, ge=0)
    annual_revenue: float | None = Field(default=None, ge=0)
    budget_range: str | None = None
    notes: str | None = None
    source_type: str = "manual"
    source_name: str = "api"


class LeadBatchIn(BaseModel):
    leads: list[LeadCanonical]


class ImportResult(BaseModel):
    imported: int
    source_name: str
    source_type: str


class SourceConfig(BaseModel):
    base_url: str | None = None
    """Zoho: CRM API base, e.g. https://www.zohoapis.com (from OAuth api_domain)."""

    redirect_uri: str | None = None
    zoho_accounts_host: str | None = None
    """Hostname only, e.g. accounts.zoho.com or accounts.zoho.eu — used for Zoho token refresh."""
    connection_url: str | None = None
    query: str | None = None
    database: str | None = None
    collection: str | None = None
    filter: dict[str, Any] | None = None
    file_path: str | None = None
    sheet_name: str | int | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    api_key: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    tenant_id: str | None = None
    subdomain: str | None = None
    object_name: str | None = None
    params: dict[str, Any] | None = None


class SourceIn(BaseModel):
    name: str
    source_type: str
    config: SourceConfig
    is_active: bool = True


class SourceRecord(SourceIn):
    id: str
    last_synced_at: datetime | None = None
    created_at: datetime


class SourceSyncResult(ImportResult):
    source_id: str


class SourceTestResult(BaseModel):
    source_type: str
    connection_ok: bool
    sample_count: int
    sample_fields: list[str]
    normalized_fields: list[str]
    preview_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Normalized lead-shaped dicts for workspace / Talk to AI preview ingest.",
    )


class HubSpotPreviewResponse(SourceTestResult):
    records: list[LeadCanonical]


class ProviderField(BaseModel):
    key: str
    label: str
    required: bool = False
    secret: bool = False
    kind: str = "text"
    placeholder: str | None = None
    help_text: str | None = None


class ProviderDefinition(BaseModel):
    key: str
    label: str
    category: str
    description: str
    recommended_order: int
    fields: list[ProviderField]


class HubSpotAuthorizeRequest(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str = "crm.objects.contacts.read crm.objects.companies.read crm.objects.owners.read"
    optional_scope: str | None = None


class HubSpotAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class HubSpotExchangeRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str
    code: str


class HubSpotTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None


class ZohoAuthorizeRequest(BaseModel):
    """All fields optional if ``ZOHO_*`` defaults are set in the API ``.env``."""

    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    zoho_accounts_host: str | None = None
    scope: str = (
        "ZohoCRM.modules.leads.READ ZohoCRM.modules.contacts.READ"
    )


class ZohoAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class ZohoTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None
    api_domain: str | None = None
    """e.g. https://www.zohoapis.com — use as CRM API base_url."""


class HubSpotBrowseRequest(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    object_name: str
    after: str | None = None
    limit: int = 5


class HubSpotBrowseResponse(BaseModel):
    object_name: str
    records: list[dict[str, Any]]
    current_after: str | None = None
    next_after: str | None = None
    limit: int


class WorkspaceConversationMessage(BaseModel):
    role: str
    content: str


class WorkspaceHubSpotData(BaseModel):
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    companies: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceMemoryState(BaseModel):
    session_id: str
    active_tab: str = "connect"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    hubspot_data: WorkspaceHubSpotData = Field(default_factory=WorkspaceHubSpotData)
    """Legacy shape; kept in sync with connector_datasets['hubspot'] when present."""

    connector_datasets: dict[str, Any] = Field(default_factory=dict)
    """Per-connector payloads (native shapes), e.g. hubspot: {contacts, companies}, salesforce: {...}."""

    knowledge_graph_summary: str | None = None
    conversation: list[WorkspaceConversationMessage] = Field(default_factory=list)
    updated_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def sync_hubspot_connector_slice(cls, data: Any) -> Any:
        """Keep hubspot_data and connector_datasets['hubspot'] aligned (before init — avoids Pydantic v2 warning)."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        cd = dict(out.get("connector_datasets") or {})

        hs = out.get("hubspot_data")
        if isinstance(hs, dict):
            contacts = list(hs.get("contacts") or [])
            companies = list(hs.get("companies") or [])
        elif hasattr(hs, "contacts"):
            contacts = list(hs.contacts or [])
            companies = list(hs.companies or [])
        else:
            contacts, companies = [], []

        hub_cd = cd.get("hubspot")
        if isinstance(hub_cd, dict):
            contacts = list(hub_cd.get("contacts") or contacts)
            companies = list(hub_cd.get("companies") or companies)
            cd["hubspot"] = {"contacts": contacts, "companies": companies}
        elif contacts or companies:
            cd["hubspot"] = {"contacts": contacts, "companies": companies}

        out["connector_datasets"] = cd
        out["hubspot_data"] = {"contacts": contacts, "companies": companies}
        return out


class WorkspaceMemoryUpsertRequest(BaseModel):
    session_id: str
    active_tab: str | None = None
    sources: list[dict[str, Any]] | None = None
    hubspot_data: WorkspaceHubSpotData | None = None
    connector_datasets: dict[str, Any] | None = None
    knowledge_graph_summary: str | None = None
    conversation: list[WorkspaceConversationMessage] | None = None


class WorkspaceConnectorPreviewIngestRequest(BaseModel):
    """Merge CRM preview rows into ``connector_datasets[connector_key]`` for Talk to AI context."""

    session_id: str
    connector_key: str = Field(
        ...,
        description="Stable key, usually the source_type (hubspot, zoho, salesforce, ...).",
    )
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    companies: list[dict[str, Any]] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="If contacts is empty, these are stored as contacts for LLM context.",
    )


class WorkspaceChatRequest(BaseModel):
    session_id: str
    message: str


class WorkspaceDataSourceSummary(BaseModel):
    key: str
    label: str
    status: str
    record_count: int = 0
    detail: str | None = None


class WorkspaceWorkflowNode(BaseModel):
    id: str
    label: str
    kind: str
    x: int
    y: int


class WorkspaceWorkflowEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class WorkspaceWorkflowPlan(BaseModel):
    title: str
    description: str
    nodes: list[WorkspaceWorkflowNode] = Field(default_factory=list)
    edges: list[WorkspaceWorkflowEdge] = Field(default_factory=list)


class WorkspaceScopeRecommendation(BaseModel):
    scope: str
    label: str
    required: bool = False
    reason: str


class WorkspaceChatResponse(BaseModel):
    session_id: str
    answer: str
    memory: WorkspaceMemoryState
    mode: str = "qa"
    title: str = "Workspace answer"
    summary: str | None = None
    data_sources: list[WorkspaceDataSourceSummary] = Field(default_factory=list)
    workflow: WorkspaceWorkflowPlan | None = None
    recommended_scopes: list[WorkspaceScopeRecommendation] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    intent_score: int = Field(ge=0, le=100)
    urgency_score: int = Field(ge=0, le=100)
    budget_score: int = Field(ge=0, le=100)
    authority_score: int = Field(ge=0, le=100)


class LeadScoreOut(BaseModel):
    lead_id: str
    overall_score: float
    recommended_action: str
    explanation: str
    breakdown: ScoreBreakdown


class LeadScoreRecord(LeadScoreOut):
    created_at: datetime
    company: str | None = None
    email: str | None = None
    source_name: str


class PostgresSyncRequest(BaseModel):
    query: str
    source_name: str = "postgres_sync"


class NotificationPayload(BaseModel):
    recipient: str
    subject: str
    body: str


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str


class LeadRow(BaseModel):
    id: str
    source_name: str
    payload: dict[str, Any]
