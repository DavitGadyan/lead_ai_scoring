from __future__ import annotations

from .schemas import CanonicalRecord, QueryCitation


def dedupe_records(records: list[CanonicalRecord]) -> list[CanonicalRecord]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[CanonicalRecord] = []
    for record in records:
        key = (record.entity_type, record.source.connector, record.source.source_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def build_citations(records: list[CanonicalRecord]) -> list[QueryCitation]:
    citations: list[QueryCitation] = []
    for record in records[:10]:
        citations.append(
            QueryCitation(
                source=record.source.connector,
                source_name=record.source.source_name,
                source_id=record.source.source_id,
                entity_type=record.entity_type,
                record_id=record.id,
                title=record.title,
            )
        )
    return citations


def estimate_confidence(records: list[CanonicalRecord], requested_limit: int) -> float:
    if requested_limit <= 0:
        return 0.0
    base = min(len(records) / requested_limit, 1.0)
    if len(records) >= 3:
        base += 0.1
    return round(min(base, 0.99), 2)
