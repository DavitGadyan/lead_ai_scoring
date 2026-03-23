from __future__ import annotations
# pylint: disable=broad-exception-caught

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import get_settings
from .memory import (
    count_connector_records,
    export_workspace_chat_context,
    get_connector_dataset,
    list_connectors_with_data,
)
from .schemas import (
    LeadCanonical,
    ScoreBreakdown,
    WorkspaceChatResponse,
    WorkspaceDataSourceSummary,
    WorkspaceMemoryState,
    WorkspaceWorkflowEdge,
    WorkspaceWorkflowNode,
    WorkspaceWorkflowPlan,
)


def build_fallback_explanation(
    lead: LeadCanonical,
    breakdown: ScoreBreakdown,
    action: str,
) -> str:
    reasons: list[str] = []
    if breakdown.fit_score >= 75:
        reasons.append("strong ICP alignment")
    if breakdown.intent_score >= 70:
        reasons.append("clear buying intent")
    if breakdown.urgency_score >= 70:
        reasons.append("near-term implementation urgency")
    if breakdown.budget_score >= 65:
        reasons.append("reasonable budget readiness")
    if breakdown.authority_score >= 65:
        reasons.append("senior decision-maker contact")

    if not reasons:
        reasons.append("limited qualification signals")

    company = lead.company or "This lead"
    return f"{company} was scored based on {', '.join(reasons)}. Recommended next action: {action}."


def generate_lead_explanation(
    lead: LeadCanonical,
    breakdown: ScoreBreakdown,
    overall_score: float,
    action: str,
) -> str:
    settings = get_settings()
    if not settings.llm_enabled or not settings.openai_api_key:
        return build_fallback_explanation(lead, breakdown, action)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a B2B lead scoring analyst. Write a concise 2-3 sentence explanation for a sales team. "
                "Be specific, factual, and avoid markdown.",
            ),
            (
                "human",
                "Lead data:\n"
                "company={company}\n"
                "job_title={job_title}\n"
                "industry={industry}\n"
                "country={country}\n"
                "employee_count={employee_count}\n"
                "budget_range={budget_range}\n"
                "notes={notes}\n\n"
                "Score breakdown:\n"
                "fit_score={fit_score}\n"
                "intent_score={intent_score}\n"
                "urgency_score={urgency_score}\n"
                "budget_score={budget_score}\n"
                "authority_score={authority_score}\n"
                "overall_score={overall_score}\n"
                "recommended_action={action}\n\n"
                "Explain why this lead got this score and what the sales team should do next.",
            ),
        ]
    )

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )

    try:
        chain = prompt | llm
        response = chain.invoke(
            {
                "company": lead.company or "Unknown",
                "job_title": lead.job_title or "Unknown",
                "industry": lead.industry or "Unknown",
                "country": lead.country or "Unknown",
                "employee_count": lead.employee_count or 0,
                "budget_range": lead.budget_range or "Unknown",
                "notes": lead.notes or "No notes provided",
                "fit_score": breakdown.fit_score,
                "intent_score": breakdown.intent_score,
                "urgency_score": breakdown.urgency_score,
                "budget_score": breakdown.budget_score,
                "authority_score": breakdown.authority_score,
                "overall_score": overall_score,
                "action": action,
            }
        )
        content = getattr(response, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except Exception:
        pass

    return build_fallback_explanation(lead, breakdown, action)


def _detect_workspace_mode(message: str) -> str:
    value = message.lower()
    automation_keywords = [
        "campaign",
        "automation",
        "workflow",
        "sequence",
        "nurture",
        "enroll",
        "journey",
        "follow-up",
        "follow up",
        "drip",
        "email blast",
        "marketing email",
        "build flow",
        "dag",
    ]
    return "automation" if any(keyword in value for keyword in automation_keywords) else "qa"


# Substrings that map the user message to a connector dataset key (Redis / workspace memory).
_CONNECTOR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("hubspot", ("hubspot",)),
    ("salesforce", ("salesforce", "sfdc", "sales cloud")),
    ("zoho", ("zoho",)),
    ("pipedrive", ("pipedrive",)),
    ("dynamics", ("dynamics", "d365", "microsoft dynamics")),
    ("netsuite", ("netsuite",)),
]


def _resolve_connector_keys_for_message(message: str, memory: WorkspaceMemoryState) -> list[str]:
    value = message.lower()
    available = list_connectors_with_data(memory)

    if any(
        token in value
        for token in ("all connectors", "all crm", "every connector", "from both", "both connectors")
    ):
        return available

    matched = [key for key, needles in _CONNECTOR_HINTS if any(n in value for n in needles)]
    if matched:
        return matched

    return available


def _connector_display_name(key: str) -> str:
    return key.replace("_", " ").title()


def _total_loaded_crm_records(memory: WorkspaceMemoryState) -> int:
    total = 0
    for key in list_connectors_with_data(memory):
        blob = get_connector_dataset(memory, key)
        if blob is not None:
            total += count_connector_records(blob)
    return total


def _build_workspace_data_sources(memory: WorkspaceMemoryState) -> list[WorkspaceDataSourceSummary]:
    summaries: list[WorkspaceDataSourceSummary] = []

    for key in sorted(memory.connector_datasets.keys()) if memory.connector_datasets else []:
        blob = get_connector_dataset(memory, key)
        if blob is None:
            continue
        count = count_connector_records(blob)
        if count == 0:
            continue
        label = f"{_connector_display_name(key)} (preview)"
        detail = "Dataset stored under workspace connector key; full records are not sent to the model every turn."
        summaries.append(
            WorkspaceDataSourceSummary(
                key=f"{key}-preview",
                label=label,
                status="active",
                record_count=count,
                detail=detail,
            )
        )

    for index, source in enumerate(memory.sources):
        label = str(source.get("name") or source.get("source_type") or f"source-{index + 1}")
        source_type = str(source.get("source_type") or "source")
        summaries.append(
            WorkspaceDataSourceSummary(
                key=f"{source_type}-{index}",
                label=label,
                status="connected",
                record_count=0,
                detail=f"{source_type} connector saved in workspace memory",
            )
        )

    if not summaries:
        summaries.append(
            WorkspaceDataSourceSummary(
                key="no-data",
                label="No connected data",
                status="idle",
                record_count=0,
                detail="Connect a CRM or other system and load preview rows into workspace memory.",
            )
        )
    return summaries


def _build_workflow_plan(message: str, memory: WorkspaceMemoryState) -> WorkspaceWorkflowPlan:
    total = _total_loaded_crm_records(memory)
    title = "CRM automation plan"
    if "campaign" in message.lower():
        title = "Campaign automation plan"

    return WorkspaceWorkflowPlan(
        title=title,
        description="Suggested flow for segmentation, messaging, execution, and measurement.",
        nodes=[
            WorkspaceWorkflowNode(id="trigger", label="Trigger", kind="trigger", x=80, y=170),
            WorkspaceWorkflowNode(id="audience", label=f"Audience ({total} records)", kind="data", x=230, y=170),
            WorkspaceWorkflowNode(id="segment", label="AI Segment", kind="agent", x=390, y=90),
            WorkspaceWorkflowNode(id="copy", label="AI Copy", kind="agent", x=390, y=250),
            WorkspaceWorkflowNode(id="campaign", label="Campaign / send", kind="action", x=560, y=90),
            WorkspaceWorkflowNode(id="sequence", label="Follow-up / Sequence", kind="action", x=560, y=250),
            WorkspaceWorkflowNode(id="report", label="Measure + Report", kind="report", x=720, y=170),
        ],
        edges=[
            WorkspaceWorkflowEdge(source="trigger", target="audience", label="loaded CRM data"),
            WorkspaceWorkflowEdge(source="audience", target="segment", label="segment"),
            WorkspaceWorkflowEdge(source="audience", target="copy", label="personalize"),
            WorkspaceWorkflowEdge(source="segment", target="campaign", label="audience"),
            WorkspaceWorkflowEdge(source="copy", target="sequence", label="follow-up"),
            WorkspaceWorkflowEdge(source="campaign", target="report", label="performance"),
            WorkspaceWorkflowEdge(source="sequence", target="report", label="outcomes"),
        ],
    )


def build_workspace_chat_fallback(message: str, memory: WorkspaceMemoryState) -> str:
    value = message.lower()
    selected = _resolve_connector_keys_for_message(message, memory)
    if not selected:
        selected = list_connectors_with_data(memory)

    counts_map = {
        k: count_connector_records(get_connector_dataset(memory, k) or {})
        for k in selected
    }

    source_names = [str(source.get("name")) for source in memory.sources if source.get("name")]
    asks_about_leads = "lead" in value and any(
        token in value for token in ["where", "created", "create", "come from", "coming from", "source", "origin"]
    )
    asks_about_contacts = "contact" in value and "connect" not in value
    asks_about_companies = "compan" in value
    asks_about_counts = "how many" in value or "count" in value
    asks_about_systems = any(token in value for token in ["system", "connector", "source", "connect first"])

    def _cite(keys: list[str], counts: dict[str, int]) -> str:
        if not keys:
            return "No connector previews are loaded in workspace memory yet."
        parts = [f"{_connector_display_name(k)}: {counts.get(k, 0)} records" for k in keys]
        return "Based on " + "; ".join(parts) + "."

    if _detect_workspace_mode(message) == "automation":
        return (
            "I can help plan a cross-connector automation from this chat. "
            "The graph shows a suggested DAG for triggers, audience, messaging, and reporting. "
            f"{_cite(selected, counts_map)}"
        )

    if asks_about_contacts:
        lines: list[str] = []
        for key in selected:
            blob = get_connector_dataset(memory, key)
            contacts: list = []
            if isinstance(blob, dict):
                contacts = list(blob.get("contacts") or [])
            if not contacts:
                lines.append(f"{_connector_display_name(key)}: no contact rows loaded in workspace memory.")
                continue
            preview = "; ".join(
                " | ".join(str(part) for part in [item.get("name"), item.get("email"), item.get("company")] if part)
                for item in contacts[:5]
            )
            lines.append(f"{_connector_display_name(key)}: {len(contacts)} contacts — {preview}")
        cite = _cite(selected, counts_map)
        return f"{cite} " + " ".join(lines)

    if asks_about_companies:
        lines = []
        for key in selected:
            blob = get_connector_dataset(memory, key)
            companies: list = []
            if isinstance(blob, dict):
                companies = list(blob.get("companies") or [])
            if not companies:
                lines.append(f"{_connector_display_name(key)}: no company rows loaded in workspace memory.")
                continue
            preview = "; ".join(
                " | ".join(
                    str(part) for part in [item.get("name"), item.get("domain"), item.get("industry"), item.get("country")] if part
                )
                for item in companies[:5]
            )
            lines.append(f"{_connector_display_name(key)}: {len(companies)} companies — {preview}")
        cite = _cite(selected, counts_map)
        return f"{cite} " + " ".join(lines)

    if asks_about_counts:
        parts = [f"{_connector_display_name(k)}: {counts_map.get(k, 0)} records" for k in selected]
        if not parts:
            return "No connector datasets with records are loaded yet. Use Connect Systems to load previews."
        return "Current loaded data summary — " + "; ".join(parts) + "."

    if asks_about_leads:
        any_contacts = False
        for key in selected:
            blob = get_connector_dataset(memory, key)
            if isinstance(blob, dict) and (blob.get("contacts") or []):
                any_contacts = True
                break
        if any_contacts:
            return (
                f"{_cite(selected, counts_map)} "
                "Visible lead rows are coming from the connector preview datasets listed above."
            )
        return f"{_cite(selected, counts_map)} No contact rows are loaded yet, so lead provenance is unclear."

    if asks_about_systems:
        if source_names:
            return f"Connected data sources currently saved in the workspace are: {', '.join(source_names[:10])}."
        return (
            "No saved connectors are in workspace memory yet. Connect your CRM (or other systems), "
            "then load preview records so the assistant can answer with the right connector context."
        )

    if memory.knowledge_graph_summary:
        return f"Latest workspace summary: {memory.knowledge_graph_summary}"

    return "Ask about loaded records by connector, connected sources, or request an automation / campaign workflow."


def build_workspace_chat_response(message: str, memory: WorkspaceMemoryState) -> WorkspaceChatResponse:
    mode = _detect_workspace_mode(message)
    answer = generate_workspace_chat_reply(message, memory)
    data_sources = _build_workspace_data_sources(memory)
    workflow = _build_workflow_plan(message, memory) if mode == "automation" else None
    title = "Connected data summary" if mode == "qa" else "Automation workflow"
    summary = (
        "Summarizes saved connectors and per-connector preview datasets available to the assistant."
        if mode == "qa"
        else "Workflow graph for the current automation-style request."
    )
    return WorkspaceChatResponse(
        session_id=memory.session_id,
        answer=answer,
        memory=memory,
        mode=mode,
        title=title,
        summary=summary,
        data_sources=data_sources,
        workflow=workflow,
        recommended_scopes=[],
        suggested_actions=[],
    )


def generate_workspace_chat_reply(message: str, memory: WorkspaceMemoryState) -> str:
    settings = get_settings()
    if not settings.llm_enabled or not settings.openai_api_key:
        return build_workspace_chat_fallback(message, memory)

    selected = _resolve_connector_keys_for_message(message, memory)
    if not selected:
        selected = list_connectors_with_data(memory)

    context_json, _counts = export_workspace_chat_context(memory, selected)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a revenue operations copilot. Multiple CRM and data connectors can be connected; each keeps "
                "its own dataset under a connector key (for example hubspot, salesforce, zoho) in workspace storage, "
                "often in that system's natural field shape. "
                "You only receive a capped JSON preview for this turn under datasets_preview — not the full warehouse. "
                "Do not invent rows or fields that are not in the preview or metadata. "
                "If the user names a specific connector, only that connector's slice should appear in datasets_preview "
                "(unless they ask for all connectors). If they name none, previews for every connector that currently "
                "has data are included. "
                "Always state clearly which connector key(s) you used for the answer and approximately how many "
                "records your reasoning is based on (use record_counts_by_connector). "
                "If a named connector has zero records in the preview, say that data is not loaded for that connector. "
                "Keep answers concise and factual. Avoid markdown unless the user asks for it.",
            ),
            (
                "human",
                "Workspace context (selective, capped preview):\n{context}\n\n"
                "User question:\n{message}\n\n"
                "Answer using only this context. Cite connector key(s) and record counts as required.",
            ),
        ]
    )

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
    )

    try:
        chain = prompt | llm
        response = chain.invoke({"context": context_json, "message": message})
        content = getattr(response, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except Exception:
        pass

    return build_workspace_chat_fallback(message, memory)
