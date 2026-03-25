from __future__ import annotations

from .query_executor import execute_query_plan
from .schemas import QueryExecutionTrace, QueryPlan, WorkspaceMemoryState, CanonicalRecord


def resolve_graphql_query(
    *,
    session_id: str,
    memory: WorkspaceMemoryState,
    plan: QueryPlan,
) -> tuple[list[CanonicalRecord], QueryExecutionTrace]:
    return execute_query_plan(session_id=session_id, memory=memory, plan=plan)
