from __future__ import annotations
# pylint: disable=broad-exception-caught

import json
import time
from functools import lru_cache
from typing import Any, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from .adapters import get_adapter
from .config import get_settings
from .connector_capabilities import get_connector_capability
from .graphql_resolvers import resolve_graphql_query
from .graphql_schema import get_schema_summary
from .lead_intelligence import analyze_records
from .llm import _build_workflow_plan, _build_workspace_data_sources, _detect_workspace_mode
from .memory import get_connector_dataset, list_connectors_with_data
from .query_executor import _record_from_row, _resolve_live_sources
from .relevance import build_citations, dedupe_records, estimate_confidence
from .schemas import (
    AgentRunSummary,
    CanonicalRecord,
    ChatQueryResponse,
    QueryExecutionTrace,
    QueryPlan,
    TokenUsageSummary,
    WorkspaceMemoryState,
)


class LeadGraphState(TypedDict, total=False):
    session_id: str
    message: str
    memory: WorkspaceMemoryState
    connector_scope: list[str]
    mode: str
    plan: QueryPlan
    schema_summary: dict[str, Any]
    records: list[CanonicalRecord]
    execution: QueryExecutionTrace
    citations: list[Any]
    confidence: float
    answer: str
    graph_analysis: dict[str, Any]
    agent_runs: list[AgentRunSummary]
    token_usage: TokenUsageSummary
    mcp_direct: bool


MCP_SOURCE_KEYS = {"dubai_dld_mcp"}


def _wants_graph_output(message: str) -> bool:
    value = _normalize_query_text(message)
    return any(
        phrase in value
        for phrase in (
            "knowledge graph",
            "create a graph",
            "generate a graph",
            "visualize",
            "grouped by each connector",
            "grouped by connector",
            "illustrate churn",
        )
    )


def _previous_session_records(memory: WorkspaceMemoryState) -> list[CanonicalRecord]:
    payload = memory.lead_intelligence or {}
    raw_records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(raw_records, list):
        return []
    records: list[CanonicalRecord] = []
    for item in raw_records:
        try:
            records.append(CanonicalRecord.model_validate(item))
        except Exception:
            continue
    return records


def _session_connector_totals(memory: WorkspaceMemoryState, sources: list[str], operation: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for source in sources:
        blob = get_connector_dataset(memory, source)
        if blob is None:
            totals[source] = 0
            continue
        if isinstance(blob, dict):
            if operation == "contacts":
                totals[source] = len(blob.get("contacts") or []) if "contacts" in blob else 0
            elif operation == "companies":
                totals[source] = len(blob.get("companies") or []) if "companies" in blob else 0
            elif "records" in blob:
                totals[source] = len(blob.get("records") or [])
            elif "contacts" in blob or "companies" in blob:
                totals[source] = len(blob.get("contacts") or []) + len(blob.get("companies") or [])
            else:
                totals[source] = sum(len(value) for value in blob.values() if isinstance(value, list))
        elif isinstance(blob, list):
            totals[source] = len(blob)
        else:
            totals[source] = 1
    return totals


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _usage_values(response: Any) -> tuple[int | None, int | None, int | None]:
    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage") if isinstance(meta, dict) else None
    if not isinstance(usage, dict):
        usage = getattr(response, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    return prompt_tokens, completion_tokens, total_tokens


def _record_agent_run(
    state: LeadGraphState,
    *,
    agent: str,
    purpose: str,
    started_at: float,
    model_name: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    status: str = "completed",
) -> None:
    settings = get_settings()
    runs = list(state.get("agent_runs") or [])
    runs.append(
        AgentRunSummary(
            agent=agent,
            purpose=purpose,
            status=status,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            trace_project=settings.langsmith_project if settings.langsmith_tracing else None,
        )
    )
    state["agent_runs"] = runs


def _update_token_usage(
    state: LeadGraphState,
    *,
    agent: str,
    estimated_prompt_tokens: int = 0,
    actual_prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    source: str = "estimate",
) -> None:
    current = state.get("token_usage") or TokenUsageSummary()
    by_agent = dict(current.by_agent)
    by_agent[agent] = int(total_tokens or estimated_prompt_tokens or 0)
    state["token_usage"] = TokenUsageSummary(
        estimated_prompt_tokens=current.estimated_prompt_tokens + estimated_prompt_tokens,
        actual_prompt_tokens=(
            (current.actual_prompt_tokens or 0) + actual_prompt_tokens
            if actual_prompt_tokens is not None
            else current.actual_prompt_tokens
        ),
        completion_tokens=(
            (current.completion_tokens or 0) + completion_tokens
            if completion_tokens is not None
            else current.completion_tokens
        ),
        total_tokens=((current.total_tokens or 0) + total_tokens) if total_tokens is not None else current.total_tokens,
        by_agent=by_agent,
        source=source if total_tokens is not None else current.source,
    )


def _available_connector_keys(memory: WorkspaceMemoryState) -> list[str]:
    keys = {str(source.get("source_type") or "").strip().lower() for source in memory.sources if source.get("source_type")}
    keys.update(k.strip().lower() for k in memory.connector_datasets.keys())
    keys.update(list_connectors_with_data(memory))
    keys.discard("")
    return sorted(keys)


def _detect_entities(message: str) -> tuple[str, list[str]]:
    value = message.lower()
    if any(token in value for token in ("property", "real estate", "project", "building", "community", "market pulse")):
        return "records", ["Property", "Project", "Record"]
    if "compan" in value or "account" in value:
        return "companies", ["Company"]
    if "deal" in value or "opportunit" in value:
        return "records", ["Record"]
    if "task" in value or "activity" in value or "note" in value:
        return "records", ["Task", "Activity", "Record"]
    if "lead" in value:
        return "leads", ["Lead"]
    return "contacts", ["Contact"]


def _route_sources(
    message: str,
    available: list[str],
    connectors_with_data: list[str],
    connector_scope: list[str],
) -> list[str]:
    if connector_scope:
        scoped = [item.strip().lower() for item in connector_scope if item.strip().lower() in available]
        if scoped:
            return scoped
    value = message.lower()
    if any(token in value for token in ("dubai", "real estate", "property", "project", "building", "community")):
        if "dubai_dld_mcp" in available:
            return ["dubai_dld_mcp"]
    matched = [key for key in available if key in value or key.replace("crm", "") in value]
    if matched:
        return matched
    if connectors_with_data:
        return connectors_with_data
    preferred = [key for key in available if get_connector_capability(key).supports_live_query]
    return preferred or available


def _normalize_query_text(message: str) -> str:
    lowered = message.lower().strip()
    replacements = {
        "conatct": "contact",
        "conatcts": "contacts",
        "connetor": "connector",
        "connetors": "connectors",
        "chrun": "churn",
        "availble": "available",
        "retrive": "retrieve",
        "visulize": "visualize",
        "knowldge": "knowledge",
    }
    normalized = lowered
    for wrong, correct in replacements.items():
        normalized = normalized.replace(wrong, correct)
    return normalized


def _extract_search_hint(message: str) -> str | None:
    value = message.strip()
    if len(value) < 6:
        return None
    lowered = _normalize_query_text(value)
    broad_inventory_markers = [
        "what contact",
        "what contacts",
        "contacts i have",
        "contact do i have",
        "contacts are available",
        "contacts available",
        "what are my contacts",
        "what contacts are available",
        "summarize by connector",
        "summarize by connected",
        "summarize by connected data",
        "by connector",
        "each connector",
        "in each connector",
        "grouped by connector",
        "grouped by each connector",
        "by connected data",
        "connected data input",
        "connected inputs",
        "all erp.crm",
        "all crm",
    ]
    if any(marker in lowered for marker in broad_inventory_markers):
        return None
    for token in ("find", "show", "list", "what", "which", "give me", "get"):
        if lowered.startswith(token):
            candidate = lowered[len(token):].strip(" ?:")
            return candidate or None
    return lowered


def _build_plan(message: str, memory: WorkspaceMemoryState, connector_scope: list[str]) -> QueryPlan:
    available = _available_connector_keys(memory)
    connectors_with_data = list_connectors_with_data(memory)
    operation, entities = _detect_entities(message)
    sources = _route_sources(message, available, connectors_with_data, connector_scope)
    limit = 8 if operation in {"contacts", "companies", "leads"} else 6
    if "how many" in message.lower() or "count" in message.lower():
        limit = 12
    if len(sources) > 1 and _extract_search_hint(message) is None:
        limit = min(20, max(limit, len(sources) * 4))
    return QueryPlan(
        intent=f"retrieve_{operation}",
        operation=operation,
        entities=entities,
        sources=sources,
        filters={
            "search": _extract_search_hint(message),
            "status": "qualified" if "qualified" in message.lower() else None,
        },
        fields={
            "contacts": ["id", "fullName", "email", "title", "companyName", "source", "sourceId", "sourceName", "summary"],
            "companies": ["id", "name", "domain", "industry", "employeeCount", "source", "sourceId", "sourceName", "summary"],
            "leads": ["id", "status", "score", "fullName", "email", "companyName", "source", "sourceId", "sourceName", "summary"],
        }.get(operation, ["id", "entityType", "title", "subtitle", "summary", "source", "sourceId", "sourceName"]),
        limit=limit,
        needs_semantic_search=any(token in message.lower() for token in ["pain", "complain", "problem", "issue", "note"]),
        follow_up_required=False,
        reasoning=f"Route across {', '.join(sources) if sources else 'available connectors'} using {operation}.",
    )


def _real_estate_request(message: str, plan: QueryPlan) -> bool:
    value = message.lower()
    return "dubai_dld_mcp" in plan.sources or any(
        token in value for token in ("dubai", "real estate", "property", "project", "building", "community")
    )

def _should_use_direct_mcp(message: str, plan: QueryPlan, memory: WorkspaceMemoryState) -> bool:
    if not any(source in MCP_SOURCE_KEYS for source in plan.sources):
        return False
    active_mcp = {str(source.get("source_type") or "").strip().lower() for source in memory.sources if source.get("source_type")}
    active_mcp.update(key for key in memory.connector_datasets.keys() if key in MCP_SOURCE_KEYS)
    if not any(source in active_mcp for source in plan.sources):
        return False
    value = message.lower()
    return any(
        token in value
        for token in (
            "mcp",
            "dubai",
            "real estate",
            "property",
            "project",
            "building",
            "community",
        )
    ) or all(source in MCP_SOURCE_KEYS for source in plan.sources)


def _fallback_answer(records: list[CanonicalRecord], plan: QueryPlan) -> str:
    if not records:
        if plan.sources:
            return (
                f"I could not find matching {plan.operation} rows across {', '.join(plan.sources)}. "
                "Try narrowing the source, changing the search phrase, or testing/saving the connector first."
            )
        return "I could not find matching rows for that request."
    if len(plan.sources) > 1 and not plan.filters.get("search"):
        counts: dict[str, int] = {}
        for record in records:
            counts[record.source.connector] = counts.get(record.source.connector, 0) + 1
        parts = [f"{source}: {count}" for source, count in sorted(counts.items())]
        return (
            f"I found {len(records)} relevant result(s) across {', '.join(plan.sources)}. "
            f"By connector: {', '.join(parts)}."
        )
    lines = [f"I found {len(records)} relevant result(s) using {', '.join(plan.sources)}."]
    for record in records[:5]:
        parts = [record.title]
        if record.subtitle:
            parts.append(record.subtitle)
        if record.summary:
            parts.append(record.summary)
        lines.append("- " + " | ".join(parts))
    return " ".join(lines)


def _router_agent(state: LeadGraphState) -> LeadGraphState:
    started_at = time.perf_counter()
    state["mode"] = _detect_workspace_mode(state["message"])
    _record_agent_run(
        state,
        agent="router_agent",
        purpose="Route intent, entities, and current-session connectors.",
        started_at=started_at,
    )
    return state


def _planner_agent(state: LeadGraphState) -> LeadGraphState:
    started_at = time.perf_counter()
    plan = _build_plan(state["message"], state["memory"], state.get("connector_scope") or [])
    state["plan"] = plan
    state["schema_summary"] = get_schema_summary(plan.sources)
    estimated = _estimate_tokens(json.dumps(plan.model_dump(mode="json")))
    _update_token_usage(state, agent="planner_agent", estimated_prompt_tokens=estimated)
    _record_agent_run(
        state,
        agent="planner_agent",
        purpose="Build retrieval plan and schema slice for GraphQL-style execution.",
        started_at=started_at,
        total_tokens=estimated,
    )
    return state


def _real_estate_search_agent(state: LeadGraphState) -> LeadGraphState:
    plan = state["plan"]
    if not _real_estate_request(state["message"], plan):
        return state
    started_at = time.perf_counter()
    plan = plan.model_copy(
        update={
            "operation": "records",
            "entities": ["Property", "Project", "Record"],
            "fields": ["id", "entityType", "title", "subtitle", "summary", "source", "sourceId", "sourceName"],
            "reasoning": f"{plan.reasoning or ''} Real-estate routing activated for Dubai property MCP search.".strip(),
        }
    )
    if "dubai_dld_mcp" not in plan.sources and "dubai_dld_mcp" in _available_connector_keys(state["memory"]):
        plan.sources = ["dubai_dld_mcp"]
    state["plan"] = plan
    estimated = _estimate_tokens(json.dumps(plan.model_dump(mode="json")))
    _update_token_usage(state, agent="real_estate_search_agent", estimated_prompt_tokens=estimated)
    _record_agent_run(
        state,
        agent="real_estate_search_agent",
        purpose="Specialize retrieval for Dubai real estate MCP tools and property-market questions.",
        started_at=started_at,
        total_tokens=estimated,
    )
    return state
def _mcp_direct_agent(state: LeadGraphState) -> LeadGraphState:
    plan = state["plan"]
    if not _should_use_direct_mcp(state["message"], plan, state["memory"]):
        state["mcp_direct"] = False
        return state

    started_at = time.perf_counter()
    mcp_sources = [source for source in _resolve_live_sources(state["memory"]) if source.source_type in plan.sources and source.source_type in MCP_SOURCE_KEYS]
    if not mcp_sources:
        state["mcp_direct"] = False
        return state

    per_source_limit = max(1, plan.limit // max(1, len(mcp_sources)))
    records = []
    for source in mcp_sources:
        config = source.config.model_copy(deep=True)
        config.query = state["message"]
        params = dict(config.params or {})
        params.setdefault("limit", per_source_limit)
        config.params = params
        rows = get_adapter(source.source_type).load_records(config)[:per_source_limit]
        records.extend(_record_from_row(row, source, "records") for row in rows if isinstance(row, dict))

    records = dedupe_records(records)[: plan.limit]
    state["records"] = records
    state["execution"] = QueryExecutionTrace(
        cache_hit=False,
        executed_query=f"direct_mcp_call({', '.join(source.source_type for source in mcp_sources)})",
        result_count=len(records),
        validated_operation="records",
        validated_sources=[source.source_type for source in mcp_sources],
    )
    state["citations"] = build_citations(records)
    state["confidence"] = estimate_confidence(records, plan.limit)
    state["mcp_direct"] = True
    estimated = _estimate_tokens(json.dumps({"sources": [source.source_type for source in mcp_sources], "message": state["message"]}))
    _update_token_usage(state, agent="mcp_direct_agent", estimated_prompt_tokens=estimated)
    _record_agent_run(
        state,
        agent="mcp_direct_agent",
        purpose="Call MCP-backed APIs directly from the user query without GraphQL/context hydration.",
        started_at=started_at,
        total_tokens=estimated,
    )
    return state


def _executor_agent(state: LeadGraphState) -> LeadGraphState:
    started_at = time.perf_counter()
    if state.get("mcp_direct"):
        _record_agent_run(
            state,
            agent="executor_agent",
            purpose="Skip GraphQL execution because direct MCP execution already produced live results.",
            started_at=started_at,
            total_tokens=0,
        )
        return state
    plan = state["plan"]
    records, execution = resolve_graphql_query(
        session_id=state["session_id"],
        memory=state["memory"],
        plan=plan,
    )
    records = dedupe_records(records)[: plan.limit]
    state["records"] = records
    state["execution"] = QueryExecutionTrace.model_validate(execution.model_dump())
    state["citations"] = build_citations(records)
    state["confidence"] = estimate_confidence(records, plan.limit)
    estimated = _estimate_tokens(json.dumps(execution.model_dump(mode="json")))
    _update_token_usage(state, agent="executor_agent", estimated_prompt_tokens=estimated)
    _record_agent_run(
        state,
        agent="executor_agent",
        purpose="Validate, execute, and cache GraphQL-style retrieval against current-session connectors.",
        started_at=started_at,
        total_tokens=estimated,
    )
    return state


def _graph_agent(state: LeadGraphState) -> LeadGraphState:
    started_at = time.perf_counter()
    records = state.get("records") or []
    plan = state.get("plan")
    if not records and _wants_graph_output(state["message"]):
        records = _previous_session_records(state["memory"])
        if records:
            state["records"] = records
    connector_totals = _session_connector_totals(
        state["memory"],
        plan.sources if plan else sorted({record.source.connector for record in records}),
        plan.operation if plan else "contacts",
    )
    graph_analysis = analyze_records(records, connector_totals=connector_totals)
    state["graph_analysis"] = graph_analysis
    estimated = _estimate_tokens(json.dumps({"records": len(records), "graph": graph_analysis.get("graph_reasoning_summary")}))
    _update_token_usage(state, agent="graph_agent", estimated_prompt_tokens=estimated)
    _record_agent_run(
        state,
        agent="graph_agent",
        purpose="Transform retrieved contacts into graph-ready nodes and Plotly chart specs.",
        started_at=started_at,
        total_tokens=estimated,
    )
    return state


def _answer_agent(state: LeadGraphState) -> LeadGraphState:
    started_at = time.perf_counter()
    records = state.get("records") or []
    plan = state["plan"]
    graph_analysis = state.get("graph_analysis") or analyze_records(records)
    state["graph_analysis"] = graph_analysis

    settings = get_settings()
    answer = _fallback_answer(records, plan)
    estimated_prompt_tokens = _estimate_tokens(
        json.dumps(
            {
                "message": state["message"],
                "plan": plan.model_dump(mode="json"),
                "records": [record.model_dump(mode="json") for record in records[:10]],
                "graph_reasoning_summary": graph_analysis.get("graph_reasoning_summary"),
                "connector_totals": graph_analysis.get("connector_totals") or {},
            },
            default=str,
        )
    )
    actual_prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    model_name = None

    if settings.llm_enabled and settings.openai_api_key:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a secure revenue operations copilot running inside a LangGraph workflow. "
                    "Answer only from validated retrieval results. Mention which connectors were used. "
                    "Call out likely conversion or churn reasons only when the evidence exists in the retrieved rows. "
                    "Do not claim HIPAA compliance.",
                ),
                (
                    "human",
                    "User question:\n{message}\n\n"
                    "Query plan:\n{plan}\n\n"
                    "Retrieved records:\n{records}\n\n"
                    "Current-session connector totals:\n{connector_totals}\n\n"
                    "Graph reasoning summary:\n{graph_reasoning_summary}\n\n"
                    "Return a concise grounded answer with connector-backed findings. "
                    "When the user asks for counts or charts by connector, use the current-session connector totals instead of only the retrieved sample rows. "
                    "Mention likely conversion/churn patterns only when supported by the retrieved evidence.",
                ),
            ]
        )
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.1,
        ).with_config({"run_name": "answer_agent"})
        try:
            response = (prompt | llm).invoke(
                {
                    "message": state["message"],
                    "plan": plan.model_dump(mode="json"),
                    "records": [record.model_dump(mode="json") for record in records[:10]],
                    "connector_totals": graph_analysis.get("connector_totals") or {},
                    "graph_reasoning_summary": graph_analysis.get("graph_reasoning_summary"),
                }
            )
            content = getattr(response, "content", "")
            if isinstance(content, str) and content.strip():
                answer = content.strip()
            actual_prompt_tokens, completion_tokens, total_tokens = _usage_values(response)
            model_name = settings.openai_model
        except Exception:
            pass

    state["answer"] = answer
    _update_token_usage(
        state,
        agent="answer_agent",
        estimated_prompt_tokens=estimated_prompt_tokens,
        actual_prompt_tokens=actual_prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        source="provider" if total_tokens is not None else "estimate",
    )
    _record_agent_run(
        state,
        agent="answer_agent",
        purpose="Compose grounded answer and summarize conversion/churn evidence.",
        started_at=started_at,
        model_name=model_name,
        prompt_tokens=actual_prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens or estimated_prompt_tokens,
    )
    return state


@lru_cache
def _compiled_chat_query_graph():
    graph = StateGraph(LeadGraphState)
    graph.add_node("router_agent", _router_agent)
    graph.add_node("planner_agent", _planner_agent)
    graph.add_node("real_estate_search_agent", _real_estate_search_agent)
    graph.add_node("mcp_direct_agent", _mcp_direct_agent)
    graph.add_node("executor_agent", _executor_agent)
    graph.add_node("graph_agent", _graph_agent)
    graph.add_node("answer_agent", _answer_agent)
    graph.add_edge(START, "router_agent")
    graph.add_edge("router_agent", "planner_agent")
    graph.add_edge("planner_agent", "real_estate_search_agent")
    graph.add_edge("real_estate_search_agent", "mcp_direct_agent")
    graph.add_edge("mcp_direct_agent", "executor_agent")
    graph.add_edge("executor_agent", "graph_agent")
    graph.add_edge("graph_agent", "answer_agent")
    graph.add_edge("answer_agent", END)
    return graph.compile()


def run_langgraph_chat_query(
    *,
    session_id: str,
    message: str,
    memory: WorkspaceMemoryState,
    connector_scope: list[str],
) -> ChatQueryResponse:
    state = _compiled_chat_query_graph().invoke(
        {
            "session_id": session_id,
            "message": message,
            "memory": memory,
            "connector_scope": connector_scope,
            "agent_runs": [],
            "token_usage": TokenUsageSummary(),
        }
    )
    mode = state.get("mode") or _detect_workspace_mode(message)
    plan = state.get("plan")
    execution = state.get("execution")
    graph_analysis = state.get("graph_analysis") or {}
    return ChatQueryResponse(
        session_id=session_id,
        answer=state.get("answer") or "",
        memory=memory,
        mode=mode,
        title="Connected data query" if mode == "qa" else "Automation workflow",
        summary=(
            "LangGraph retrieval-first answer from validated GraphQL-style queries over the selected connectors."
            if mode == "qa"
            else "LangGraph workflow proposed after validated retrieval across current-session connectors."
        ),
        data_sources=_build_workspace_data_sources(memory),
        workflow=_build_workflow_plan(message, memory) if mode == "automation" else None,
        recommended_scopes=[],
        suggested_actions=[] if state.get("records") else ["Test or save the connector, then retry with a narrower search phrase."],
        used_sources=plan.sources if plan else [],
        query_plan=plan,
        execution=execution,
        records=state.get("records") or [],
        citations=state.get("citations") or [],
        confidence=float(state.get("confidence") or 0.0),
        agent_runs=state.get("agent_runs") or [],
        token_usage=state.get("token_usage"),
        graph_reasoning_summary=graph_analysis.get("graph_reasoning_summary"),
        graph_nodes=graph_analysis.get("graph_nodes") or [],
        graph_edges=graph_analysis.get("graph_edges") or [],
        plotly_charts=graph_analysis.get("plotly_charts") or [],
        conversion_summary=graph_analysis.get("conversion_summary"),
        churn_summary=graph_analysis.get("churn_summary"),
        conversion_signals=graph_analysis.get("conversion_signals") or [],
        churn_signals=graph_analysis.get("churn_signals") or [],
    )
