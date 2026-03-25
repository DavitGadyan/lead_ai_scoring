from __future__ import annotations

import json

from .db import get_conn
from .schemas import CanonicalRecord, QueryPlan


def persist_query_run(
    *,
    session_key: str,
    user_question: str,
    plan: QueryPlan,
    executed_query: str,
    used_sources: list[str],
    confidence: float,
    records: list[CanonicalRecord],
) -> None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into chat_sessions (session_key)
                    values (%s)
                    on conflict (session_key)
                    do update set updated_at = now()
                    """,
                    (session_key,),
                )
                cur.execute(
                    """
                    insert into query_runs (session_key, user_question, plan_json, executed_query, used_sources, confidence)
                    values (%s, %s, %s::jsonb, %s, %s::jsonb, %s)
                    returning id
                    """,
                    (
                        session_key,
                        user_question,
                        plan.model_dump_json(),
                        executed_query,
                        json.dumps(used_sources),
                        confidence,
                    ),
                )
                row = cur.fetchone()
                query_run_id = row["id"]
                for record in records[:25]:
                    cur.execute(
                        """
                        insert into query_run_results (query_run_id, entity_type, source, source_record_id, title, payload)
                        values (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            query_run_id,
                            record.entity_type,
                            record.source.connector,
                            record.source.source_id,
                            record.title,
                            record.model_dump_json(),
                        ),
                    )
            conn.commit()
    except Exception:
        # Audit writes should never block chat responses.
        return
