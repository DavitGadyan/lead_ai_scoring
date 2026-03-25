from __future__ import annotations

from collections import Counter, defaultdict

from .schemas import (
    CanonicalRecord,
    GraphEdgePayload,
    GraphNodePayload,
    LeadChurnSignal,
    LeadConversionSignal,
    LeadRiskSummary,
    PlotlyChartSpec,
    PlotlyTraceSpec,
)

_POSITIVE_STATUS = (
    "qualified",
    "proposal",
    "demo",
    "trial",
    "won",
    "converted",
    "customer",
    "active",
)
_NEGATIVE_STATUS = (
    "churn",
    "cancel",
    "at risk",
    "risk",
    "lost",
    "closed lost",
    "inactive",
    "renewal",
)
_POSITIVE_TEXT = (
    "interested",
    "engaged",
    "replied",
    "meeting",
    "follow up",
    "expansion",
)
_NEGATIVE_TEXT = (
    "no owner",
    "unassigned",
    "stale",
    "no response",
    "complaint",
    "issue",
    "support",
    "delay",
    "refund",
)


def _record_text(record: CanonicalRecord) -> str:
    parts = [record.title, record.subtitle or "", record.summary or ""]
    parts.extend(str(value) for value in record.data.values() if value not in (None, ""))
    return " ".join(parts).lower()


def _score_matches(text: str, phrases: tuple[str, ...], weight: float, reasons: list[str]) -> float:
    score = 0.0
    for phrase in phrases:
        if phrase in text:
            score += weight
            reasons.append(phrase)
    return score


def _score_conversion(record: CanonicalRecord) -> LeadConversionSignal | None:
    text = _record_text(record)
    reasons: list[str] = []
    score = 0.0
    score += _score_matches(text, _POSITIVE_STATUS, 0.28, reasons)
    score += _score_matches(text, _POSITIVE_TEXT, 0.18, reasons)
    if record.data.get("email"):
        score += 0.08
        reasons.append("email_present")
    if record.data.get("company_name"):
        score += 0.08
        reasons.append("company_present")
    if any(keyword in text for keyword in ("vp", "director", "head of", "manager", "founder")):
        score += 0.14
        reasons.append("senior_contact")
    if score < 0.22:
        return None
    return LeadConversionSignal(
        record_id=record.id,
        connector=record.source.connector,
        title=record.title,
        score=min(score, 1.0),
        reasons=sorted(set(reasons)),
    )


def _score_churn(record: CanonicalRecord) -> LeadChurnSignal | None:
    text = _record_text(record)
    reasons: list[str] = []
    score = 0.0
    score += _score_matches(text, _NEGATIVE_STATUS, 0.26, reasons)
    score += _score_matches(text, _NEGATIVE_TEXT, 0.18, reasons)
    if not record.data.get("email"):
        score += 0.08
        reasons.append("missing_email")
    if "renewal" in text or "contract" in text:
        score += 0.12
        reasons.append("renewal_signal")
    if score < 0.22:
        return None
    return LeadChurnSignal(
        record_id=record.id,
        connector=record.source.connector,
        title=record.title,
        score=min(score, 1.0),
        reasons=sorted(set(reasons)),
    )


def _build_summary(
    *,
    label: str,
    connector_names: list[str],
    reasons: list[str],
) -> LeadRiskSummary:
    breakdown = Counter(connector_names)
    top_reasons = [reason for reason, _count in Counter(reasons).most_common(6)]
    return LeadRiskSummary(
        label=label,
        connector_breakdown=dict(sorted(breakdown.items())),
        top_reasons=top_reasons,
        total_records=len(connector_names),
    )


def _plotly_charts(
    *,
    records: list[CanonicalRecord],
    conversion_signals: list[LeadConversionSignal],
    churn_signals: list[LeadChurnSignal],
    connector_totals: dict[str, int] | None = None,
) -> list[PlotlyChartSpec]:
    connector_counts = Counter(connector_totals or Counter(record.source.connector for record in records))
    top_companies = Counter(
        str(record.data.get("company_name") or "").strip()
        for record in records
        if str(record.data.get("company_name") or "").strip()
    )
    conversion_counts = Counter(signal.connector for signal in conversion_signals)
    churn_counts = Counter(signal.connector for signal in churn_signals)

    charts: list[PlotlyChartSpec] = [
        PlotlyChartSpec(
            id="contacts-by-connector",
            title="Contacts By Connector",
            chart_type="bar",
            description="Interactive bar chart showing current-session contact totals by connector.",
            data=[
                PlotlyTraceSpec(
                    type="bar",
                    x=list(connector_counts.keys()),
                    y=list(connector_counts.values()),
                    marker={"color": ["#0ea5e9", "#8b5cf6", "#22c55e", "#f59e0b"][: len(connector_counts)]},
                )
            ],
            layout={
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "margin": {"l": 40, "r": 20, "t": 56, "b": 40},
                "xaxis": {"title": "Connector"},
                "yaxis": {"title": "Contacts"},
            },
            config={"displayModeBar": True, "responsive": True},
        ),
        PlotlyChartSpec(
            id="signals-by-connector",
            title="Conversion vs Churn Signals",
            chart_type="grouped-bar",
            description="Grouped bar chart comparing detected conversion and churn signals by connector.",
            data=[
                PlotlyTraceSpec(
                    type="bar",
                    name="Conversion",
                    x=sorted(connector_counts.keys()),
                    y=[conversion_counts.get(key, 0) for key in sorted(connector_counts.keys())],
                    marker={"color": "#22c55e"},
                ),
                PlotlyTraceSpec(
                    type="bar",
                    name="Churn",
                    x=sorted(connector_counts.keys()),
                    y=[churn_counts.get(key, 0) for key in sorted(connector_counts.keys())],
                    marker={"color": "#ef4444"},
                ),
            ],
            layout={
                "barmode": "group",
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "margin": {"l": 40, "r": 20, "t": 56, "b": 40},
                "xaxis": {"title": "Connector"},
                "yaxis": {"title": "Signals"},
            },
            config={"displayModeBar": True, "responsive": True},
        ),
    ]
    if top_companies:
        companies = top_companies.most_common(8)
        charts.append(
            PlotlyChartSpec(
                id="top-companies",
                title="Top Companies In Current Result Set",
                chart_type="horizontal-bar",
                description="Horizontal bar chart of companies represented in the retrieved contacts.",
                data=[
                    PlotlyTraceSpec(
                        type="bar",
                        x=[count for _company, count in companies],
                        y=[company for company, _count in companies],
                        marker={"color": "#6366f1"},
                    )
                ],
                layout={
                    "paper_bgcolor": "rgba(0,0,0,0)",
                    "plot_bgcolor": "rgba(0,0,0,0)",
                    "margin": {"l": 120, "r": 20, "t": 56, "b": 40},
                    "xaxis": {"title": "Contacts"},
                    "yaxis": {"title": "Company", "automargin": True},
                },
                config={"displayModeBar": True, "responsive": True},
            )
        )
    return charts

def analyze_records(records: list[CanonicalRecord], *, connector_totals: dict[str, int] | None = None) -> dict[str, object]:
    conversion_signals = [signal for record in records if (signal := _score_conversion(record)) is not None]
    churn_signals = [signal for record in records if (signal := _score_churn(record)) is not None]

    nodes: list[GraphNodePayload] = []
    edges: list[GraphEdgePayload] = []
    added_nodes: set[str] = set()
    connector_positions: dict[str, int] = {}
    per_connector_row = defaultdict(int)

    def add_node(node: GraphNodePayload) -> None:
        if node.id in added_nodes:
            return
        nodes.append(node)
        added_nodes.add(node.id)

    for index, connector in enumerate(sorted({record.source.connector for record in records})):
        connector_positions[connector] = index
        add_node(
            GraphNodePayload(
                id=f"connector:{connector}",
                label=connector,
                kind="connector",
                x=60,
                y=90 + (index * 180),
                connector=connector,
                view="grouped",
                detail="Current-session connector included in the LangGraph retrieval plan.",
            )
        )

    grouped_company_nodes: set[str] = set()

    for record_index, record in enumerate(records[:24]):
        connector_index = connector_positions.get(record.source.connector, 0)
        row = record_index % 8
        record_node_id = f"record:grouped:{record.id}"
        add_node(
            GraphNodePayload(
                id=record_node_id,
                label=record.title,
                kind=record.entity_type.lower(),
                x=320,
                y=70 + (connector_index * 210) + (row * 64),
                connector=record.source.connector,
                view="grouped",
                detail=record.subtitle or record.summary,
            )
        )
        edges.append(
            GraphEdgePayload(
                id=f"edge:grouped:{record.source.connector}:{record.id}",
                source=f"connector:{record.source.connector}",
                target=record_node_id,
                label="contact",
                view="grouped",
            )
        )
        company_name = str(record.data.get("company_name") or "").strip()
        if company_name:
            company_node_id = f"company:grouped:{company_name.lower()}"
            if company_node_id not in grouped_company_nodes:
                grouped_company_nodes.add(company_node_id)
                add_node(
                    GraphNodePayload(
                        id=company_node_id,
                        label=company_name,
                        kind="company",
                        x=620,
                        y=70 + (connector_index * 210) + (row * 64),
                        connector=record.source.connector,
                        view="grouped",
                        detail="Company cluster",
                    )
                )
            edges.append(
                GraphEdgePayload(
                    id=f"edge:grouped:{record.id}:company",
                    source=record_node_id,
                    target=company_node_id,
                    label="company",
                    view="grouped",
                )
            )

    def attach_signal(record: CanonicalRecord, score: float, reasons: list[str], signal_kind: str, view: str) -> None:
        connector_index = connector_positions.get(record.source.connector, 0)
        row = per_connector_row[(record.source.connector, view)]
        per_connector_row[(record.source.connector, view)] += 1
        record_node_id = f"record:{view}:{record.id}"
        outcome_node_id = f"outcome:{view}:{record.id}"
        add_node(
            GraphNodePayload(
                id=record_node_id,
                label=record.title,
                kind=record.entity_type.lower(),
                x=300,
                y=90 + (connector_index * 180) + (row * 78),
                connector=record.source.connector,
                view=view,
                detail=record.subtitle or record.summary,
            )
        )
        add_node(
            GraphNodePayload(
                id=outcome_node_id,
                label="Likely Convert" if signal_kind == "conversion" else "Churn Risk",
                kind="outcome",
                x=560,
                y=90 + (connector_index * 180) + (row * 78),
                connector=record.source.connector,
                view=view,
                score=round(score, 2),
                detail=f"{signal_kind} score {score:.2f}",
            )
        )
        edges.append(
            GraphEdgePayload(
                id=f"edge:{record.source.connector}:{record.id}:{view}",
                source=f"connector:{record.source.connector}",
                target=record_node_id,
                label="source",
                view=view,
            )
        )
        edges.append(
            GraphEdgePayload(
                id=f"edge:{view}:{record.id}:outcome",
                source=record_node_id,
                target=outcome_node_id,
                label="supports",
                view=view,
                strength=round(score, 2),
            )
        )
        for reason_index, reason in enumerate(reasons[:4]):
            reason_node_id = f"reason:{view}:{record.id}:{reason}"
            add_node(
                GraphNodePayload(
                    id=reason_node_id,
                    label=reason.replace("_", " "),
                    kind="reason",
                    x=820,
                    y=90 + (connector_index * 180) + (row * 78) + (reason_index * 34),
                    connector=record.source.connector,
                    view=view,
                )
            )
            edges.append(
                GraphEdgePayload(
                    id=f"edge:{view}:{record.id}:{reason}",
                    source=reason_node_id,
                    target=record_node_id,
                    label="reason",
                    view=view,
                )
            )

    record_lookup = {record.id: record for record in records}
    for signal in conversion_signals[:18]:
        record = record_lookup.get(signal.record_id)
        if record is not None:
            attach_signal(record, signal.score, signal.reasons, "conversion", "conversion")
    for signal in churn_signals[:18]:
        record = record_lookup.get(signal.record_id)
        if record is not None:
            attach_signal(record, signal.score, signal.reasons, "churn", "churn")

    conversion_summary = _build_summary(
        label="Likely conversion signals",
        connector_names=[signal.connector for signal in conversion_signals],
        reasons=[reason for signal in conversion_signals for reason in signal.reasons],
    )
    churn_summary = _build_summary(
        label="Likely churn signals",
        connector_names=[signal.connector for signal in churn_signals],
        reasons=[reason for signal in churn_signals for reason in signal.reasons],
    )
    reasoning = (
        f"Analyzed {len(records)} retrieved records across "
        f"{len(connector_positions)} connector(s) for positive conversion and churn-risk evidence."
    )
    charts = _plotly_charts(
        records=records,
        conversion_signals=conversion_signals,
        churn_signals=churn_signals,
        connector_totals=connector_totals,
    )
    effective_connector_totals = dict(connector_totals or Counter(record.source.connector for record in records))
    return {
        "conversion_signals": conversion_signals,
        "churn_signals": churn_signals,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "plotly_charts": charts,
        "connector_totals": effective_connector_totals,
        "conversion_summary": conversion_summary,
        "churn_summary": churn_summary,
        "graph_reasoning_summary": reasoning,
    }
