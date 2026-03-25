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
    lifecycle_stage: str | None = None
    lead_status: str | None = None
    owner_name: str | None = None
    last_activity_at: str | None = None
    days_since_last_activity: int | None = Field(default=None, ge=0)
    engagement_score: float | None = None
    health_score: float | None = None
    product_usage_score: float | None = None
    support_ticket_count: int | None = Field(default=None, ge=0)
    nps_score: float | None = None
    contract_value: float | None = None
    renewal_date: str | None = None
    conversion_likelihood: float | None = None
    churn_risk: float | None = None
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
    monday_board_ids: str | None = None
    """monday.com board IDs (comma-separated). Used when ``query`` is empty to fetch items for scoring / Talk to AI."""
    mcp_command: str | None = None
    mcp_args: list[str] | None = None
    mcp_env: dict[str, str] | None = None
    mcp_tool_name: str | None = None
    mcp_profile: str | None = None


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
    lead_intelligence: dict[str, Any] | None = None
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
    lead_intelligence: dict[str, Any] | None = None
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


class ChatQueryRequest(BaseModel):
    session_id: str
    message: str
    connector_scope: list[str] = Field(default_factory=list)


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


class CanonicalSourceRef(BaseModel):
    connector: str
    source_id: str
    source_name: str
    last_synced_at: datetime | None = None


class CanonicalContact(BaseModel):
    id: str
    full_name: str | None = None
    email: str | None = None
    title: str | None = None
    company_name: str | None = None
    source: CanonicalSourceRef
    last_updated_at: datetime | None = None


class CanonicalCompany(BaseModel):
    id: str
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    source: CanonicalSourceRef
    last_updated_at: datetime | None = None


class CanonicalLead(BaseModel):
    id: str
    status: str | None = None
    score: float | None = None
    full_name: str | None = None
    email: str | None = None
    company_name: str | None = None
    source: CanonicalSourceRef
    last_updated_at: datetime | None = None


class CanonicalRecord(BaseModel):
    id: str
    entity_type: str
    title: str
    subtitle: str | None = None
    summary: str | None = None
    source: CanonicalSourceRef
    data: dict[str, Any] = Field(default_factory=dict)


class QueryPlan(BaseModel):
    intent: str
    operation: str
    entities: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    fields: list[str] = Field(default_factory=list)
    limit: int = 10
    needs_semantic_search: bool = False
    follow_up_required: bool = False
    reasoning: str | None = None


class QueryCitation(BaseModel):
    source: str
    source_name: str
    source_id: str
    entity_type: str
    record_id: str
    title: str


class QueryExecutionTrace(BaseModel):
    cache_hit: bool = False
    executed_query: str
    result_count: int = 0
    validated_operation: str
    validated_sources: list[str] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    agent: str
    purpose: str
    framework: str = "langgraph"
    status: str = "completed"
    latency_ms: int = 0
    model_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    trace_project: str | None = None


class TokenUsageSummary(BaseModel):
    estimated_prompt_tokens: int = 0
    actual_prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    by_agent: dict[str, int] = Field(default_factory=dict)
    source: str = "estimate"


class LeadConversionSignal(BaseModel):
    record_id: str
    connector: str
    title: str
    score: float
    reasons: list[str] = Field(default_factory=list)


class LeadChurnSignal(BaseModel):
    record_id: str
    connector: str
    title: str
    score: float
    reasons: list[str] = Field(default_factory=list)


class LeadRiskSummary(BaseModel):
    label: str
    connector_breakdown: dict[str, int] = Field(default_factory=dict)
    top_reasons: list[str] = Field(default_factory=list)
    total_records: int = 0


class GraphNodePayload(BaseModel):
    id: str
    label: str
    kind: str
    x: int = 0
    y: int = 0
    connector: str | None = None
    view: str = "all"
    detail: str | None = None
    score: float | None = None


class GraphEdgePayload(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    view: str = "all"
    strength: float | None = None


class PlotlyTraceSpec(BaseModel):
    type: str = "bar"
    name: str | None = None
    x: list[Any] = Field(default_factory=list)
    y: list[Any] = Field(default_factory=list)
    labels: list[str] | None = None
    values: list[float] | None = None
    text: list[str] | None = None
    mode: str | None = None
    marker: dict[str, Any] = Field(default_factory=dict)


class PlotlyChartSpec(BaseModel):
    id: str
    title: str
    chart_type: str
    description: str | None = None
    data: list[PlotlyTraceSpec] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


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


class ChatQueryResponse(WorkspaceChatResponse):
    used_sources: list[str] = Field(default_factory=list)
    query_plan: QueryPlan | None = None
    execution: QueryExecutionTrace | None = None
    records: list[CanonicalRecord] = Field(default_factory=list)
    citations: list[QueryCitation] = Field(default_factory=list)
    confidence: float = 0.0
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)
    token_usage: TokenUsageSummary | None = None
    graph_reasoning_summary: str | None = None
    graph_nodes: list[GraphNodePayload] = Field(default_factory=list)
    graph_edges: list[GraphEdgePayload] = Field(default_factory=list)
    plotly_charts: list[PlotlyChartSpec] = Field(default_factory=list)
    conversion_summary: LeadRiskSummary | None = None
    churn_summary: LeadRiskSummary | None = None
    conversion_signals: list[LeadConversionSignal] = Field(default_factory=list)
    churn_signals: list[LeadChurnSignal] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    intent_score: int = Field(ge=0, le=100)
    urgency_score: int = Field(ge=0, le=100)
    budget_score: int = Field(ge=0, le=100)
    authority_score: int = Field(ge=0, le=100)


class LeadScoreOut(BaseModel):
    lead_id: str
    overall_score: float
    directional_score: float | None = Field(default=None, ge=-1, le=1)
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
