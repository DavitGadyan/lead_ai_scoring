from __future__ import annotations
# pylint: disable=broad-exception-caught

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING, Any

from .config import get_settings
from .schemas import (
    WorkspaceChatRequest,
    WorkspaceConversationMessage,
    WorkspaceMemoryState,
    WorkspaceMemoryUpsertRequest,
)

if TYPE_CHECKING:
    from .schemas import WorkspaceConnectorPreviewIngestRequest

_memory_lock = Lock()
_memory_store: dict[str, tuple[datetime, WorkspaceMemoryState]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expiry() -> datetime:
    settings = get_settings()
    return _utcnow() + timedelta(seconds=settings.workspace_memory_ttl_seconds)


@lru_cache
def _get_redis_client():
    settings = get_settings()
    if not settings.redis_url:
        return None

    try:
        redis_module = import_module("redis")
        client = redis_module.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _memory_key(session_id: str) -> str:
    return f"workspace-memory:{session_id}"


def _connector_slice_key(session_id: str, connector_key: str) -> str:
    return f"workspace:connector:{session_id}:{connector_key}"


def _mirror_connector_slices(client, session_id: str, ttl: int, connector_datasets: dict[str, Any]) -> None:
    for key, value in connector_datasets.items():
        try:
            client.setex(_connector_slice_key(session_id, key), ttl, json.dumps(value, default=str))
        except Exception:
            continue


def _default_state(session_id: str) -> WorkspaceMemoryState:
    return WorkspaceMemoryState(session_id=session_id, updated_at=_utcnow())


def get_workspace_memory(session_id: str) -> WorkspaceMemoryState:
    client = _get_redis_client()
    if client is not None:
        raw = client.get(_memory_key(session_id))
        if not raw:
            return _default_state(session_id)
        return WorkspaceMemoryState.model_validate_json(raw)

    now = _utcnow()
    with _memory_lock:
        expired_keys = [key for key, (expiry, _) in _memory_store.items() if expiry <= now]
        for key in expired_keys:
            _memory_store.pop(key, None)

        item = _memory_store.get(session_id)
        if not item:
            return _default_state(session_id)
        _, state = item
        return state


def save_workspace_memory(payload: WorkspaceMemoryUpsertRequest) -> WorkspaceMemoryState:
    current = get_workspace_memory(payload.session_id)
    next_cd = dict(current.connector_datasets)
    if payload.connector_datasets is not None:
        next_cd.update(payload.connector_datasets)
    next_hs = current.hubspot_data
    if payload.hubspot_data is not None:
        next_hs = payload.hubspot_data
        next_cd["hubspot"] = {"contacts": next_hs.contacts, "companies": next_hs.companies}

    draft = current.model_copy(
        update={
            "active_tab": payload.active_tab if payload.active_tab is not None else current.active_tab,
            "sources": payload.sources if payload.sources is not None else current.sources,
            "hubspot_data": next_hs,
            "connector_datasets": next_cd,
            "knowledge_graph_summary": payload.knowledge_graph_summary
            if payload.knowledge_graph_summary is not None
            else current.knowledge_graph_summary,
            "conversation": payload.conversation if payload.conversation is not None else current.conversation,
            "updated_at": _utcnow(),
        }
    )
    next_state = WorkspaceMemoryState.model_validate(draft.model_dump())

    client = _get_redis_client()
    if client is not None:
        settings = get_settings()
        ttl = settings.workspace_memory_ttl_seconds
        client.setex(
            _memory_key(payload.session_id),
            ttl,
            next_state.model_dump_json(),
        )
        _mirror_connector_slices(client, payload.session_id, ttl, dict(next_state.connector_datasets))
        return next_state

    with _memory_lock:
        _memory_store[payload.session_id] = (_expiry(), next_state)
    return next_state


def ingest_connector_preview(payload: WorkspaceConnectorPreviewIngestRequest) -> WorkspaceMemoryState:
    """Store CRM preview rows under ``connector_datasets[connector_key]`` (merged into Redis / memory)."""
    contacts = list(payload.contacts)
    if not contacts and payload.records:
        contacts = [dict(row) for row in payload.records]
    companies = list(payload.companies)
    blob: dict[str, Any] = {"contacts": contacts, "companies": companies}
    key = payload.connector_key.strip().lower()
    if not key:
        raise ValueError("connector_key is required")
    return save_workspace_memory(
        WorkspaceMemoryUpsertRequest(
            session_id=payload.session_id,
            connector_datasets={key: blob},
        )
    )


def append_workspace_conversation(payload: WorkspaceChatRequest, answer: str) -> WorkspaceMemoryState:
    current = get_workspace_memory(payload.session_id)
    next_conversation = list(current.conversation)
    if not (
        next_conversation
        and next_conversation[-1].role == "user"
        and next_conversation[-1].content == payload.message
    ):
        next_conversation.append(WorkspaceConversationMessage(role="user", content=payload.message))
    next_conversation.append(WorkspaceConversationMessage(role="assistant", content=answer))
    return save_workspace_memory(
        WorkspaceMemoryUpsertRequest(
            session_id=payload.session_id,
            conversation=next_conversation,
        )
    )


def export_workspace_memory_summary(memory: WorkspaceMemoryState) -> str:
    """Full summary for debugging; prefer export_workspace_chat_context for LLM calls."""
    preview: dict[str, Any] = {}
    for name, blob in memory.connector_datasets.items():
        if isinstance(blob, dict) and ("contacts" in blob or "companies" in blob):
            preview[name] = {
                "contacts": (blob.get("contacts") or [])[:5],
                "companies": (blob.get("companies") or [])[:5],
            }
        elif isinstance(blob, list):
            preview[name] = blob[:5]
        else:
            preview[name] = blob
    payload = {
        "active_tab": memory.active_tab,
        "source_names": [source.get("name") for source in memory.sources[:10]],
        "connector_preview": preview,
        "knowledge_graph_summary": memory.knowledge_graph_summary,
        "conversation_tail": [item.model_dump() for item in memory.conversation[-6:]],
    }
    return json.dumps(payload, indent=2, default=str)


def connector_dataset_has_records(blob: Any) -> bool:
    if blob is None:
        return False
    if isinstance(blob, dict):
        if "contacts" in blob or "companies" in blob:
            return bool((blob.get("contacts") or []) or (blob.get("companies") or []))
        return any(connector_dataset_has_records(v) for v in blob.values())
    if isinstance(blob, list):
        return len(blob) > 0
    return True


def list_connectors_with_data(memory: WorkspaceMemoryState) -> list[str]:
    keys = [k for k, v in memory.connector_datasets.items() if connector_dataset_has_records(v)]
    if "hubspot" not in keys and (memory.hubspot_data.contacts or memory.hubspot_data.companies):
        keys.append("hubspot")
    return sorted(set(keys))


def count_connector_records(blob: Any) -> int:
    if blob is None:
        return 0
    if isinstance(blob, dict) and ("contacts" in blob or "companies" in blob):
        return len(blob.get("contacts") or []) + len(blob.get("companies") or [])
    if isinstance(blob, list):
        return len(blob)
    if isinstance(blob, dict):
        return sum(len(v) if isinstance(v, list) else (1 if v is not None else 0) for v in blob.values())
    return 1


def trim_connector_dataset(blob: Any, limit: int) -> Any:
    if isinstance(blob, dict):
        trimmed: dict[str, Any] = {}
        for key, value in blob.items():
            if isinstance(value, list):
                trimmed[key] = value[:limit]
            elif isinstance(value, dict):
                trimmed[key] = trim_connector_dataset(value, limit)
            else:
                trimmed[key] = value
        return trimmed
    if isinstance(blob, list):
        return blob[:limit]
    return blob


def get_connector_dataset(memory: WorkspaceMemoryState, connector_key: str) -> Any | None:
    raw = memory.connector_datasets.get(connector_key)
    if raw is not None:
        return raw
    if connector_key == "hubspot" and (memory.hubspot_data.contacts or memory.hubspot_data.companies):
        return {"contacts": memory.hubspot_data.contacts, "companies": memory.hubspot_data.companies}
    return None


def export_workspace_chat_context(
    memory: WorkspaceMemoryState,
    selected_keys: list[str],
    preview_limit: int = 28,
) -> tuple[str, dict[str, int]]:
    """Build a JSON context string for the LLM and return record counts per selected connector."""
    counts: dict[str, int] = {}
    preview: dict[str, Any] = {}
    for key in selected_keys:
        blob = get_connector_dataset(memory, key)
        if blob is None:
            counts[key] = 0
            preview[key] = None
            continue
        counts[key] = count_connector_records(blob)
        preview[key] = trim_connector_dataset(blob, preview_limit)

    payload = {
        "instruction": (
            "Only the connectors listed under datasets_preview are included in this turn. "
            "Full datasets live in workspace storage per connector key; this is a capped preview."
        ),
        "connectors_included_this_turn": selected_keys,
        "record_counts_by_connector": counts,
        "datasets_preview": preview,
        "saved_connector_sources": [
            {"name": s.get("name"), "source_type": s.get("source_type")} for s in memory.sources[:12]
        ],
        "knowledge_graph_summary": memory.knowledge_graph_summary,
        "conversation_tail": [item.model_dump() for item in memory.conversation[-6:]],
    }
    return json.dumps(payload, indent=2, default=str), counts
