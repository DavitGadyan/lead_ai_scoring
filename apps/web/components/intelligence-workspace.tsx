"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PlotParams } from "react-plotly.js";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  NodeResizer,
  ReactFlow,
  ReactFlowProvider,
  Position,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { SourceManager, type HubSpotWorkspaceData } from "./source-manager";

const Plot = dynamic<PlotParams>(() => import("react-plotly.js"), { ssr: false });

type SourceRecord = {
  id: string;
  name: string;
  source_type: string;
  is_active: boolean;
  created_at: string;
  last_synced_at: string | null;
  config: {
    connection_url?: string | null;
    file_path?: string | null;
  };
};

type ProviderDefinition = {
  key: string;
  label: string;
  category: string;
  description: string;
  recommended_order: number;
  fields: Array<{
    key: string;
    label: string;
    required: boolean;
    secret: boolean;
    kind: string;
    placeholder?: string | null;
    help_text?: string | null;
  }>;
};

type ConversationMessage = {
  role: "assistant" | "user";
  content: string;
};

type ConnectorDatasets = Record<string, unknown>;

type WorkspaceMemoryState = {
  session_id: string;
  active_tab: string;
  sources: SourceRecord[];
  hubspot_data: HubSpotWorkspaceData;
  connector_datasets?: ConnectorDatasets;
  knowledge_graph_summary: string | null;
  lead_intelligence?: {
    mode?: "qa" | "automation";
    title?: string | null;
    summary?: string | null;
    used_sources?: string[];
    query_plan?: QueryPlan | null;
    execution?: QueryExecutionTrace | null;
    records?: CanonicalRecord[];
    confidence?: number;
    agent_runs?: AgentRunSummary[];
    token_usage?: TokenUsageSummary | null;
    graph_reasoning_summary?: string | null;
    graph_nodes?: GraphNodePayload[];
    graph_edges?: GraphEdgePayload[];
    plotly_charts?: PlotlyChartSpec[];
    conversion_summary?: LeadRiskSummary | null;
    churn_summary?: LeadRiskSummary | null;
    conversion_signals?: LeadSignal[];
    churn_signals?: LeadSignal[];
    citations?: QueryCitation[];
  } | null;
  conversation: ConversationMessage[];
  updated_at: string | null;
};

type WorkspaceDataSourceSummary = {
  key: string;
  label: string;
  status: string;
  record_count: number;
  detail: string | null;
};

type WorkspaceWorkflowNode = {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
};

type WorkspaceWorkflowEdge = {
  source: string;
  target: string;
  label?: string | null;
};

type WorkspaceWorkflowPlan = {
  title: string;
  description: string;
  nodes: WorkspaceWorkflowNode[];
  edges: WorkspaceWorkflowEdge[];
};

type WorkflowNodeData = {
  label: string;
  kind: string;
  detail?: string | null;
  score?: number | null;
};

type WorkspaceScopeRecommendation = {
  scope: string;
  label: string;
  required: boolean;
  reason: string;
};

type QueryPlan = {
  intent: string;
  operation: string;
  entities: string[];
  sources: string[];
  filters: Record<string, unknown>;
  fields: string[];
  limit: number;
  needs_semantic_search: boolean;
  follow_up_required: boolean;
  reasoning?: string | null;
};

type QueryExecutionTrace = {
  cache_hit: boolean;
  executed_query: string;
  result_count: number;
  validated_operation: string;
  validated_sources: string[];
};

type AgentRunSummary = {
  agent: string;
  purpose: string;
  framework: string;
  status: string;
  latency_ms: number;
  model_name?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  trace_project?: string | null;
};

type TokenUsageSummary = {
  estimated_prompt_tokens: number;
  actual_prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  by_agent: Record<string, number>;
  source: string;
};

type LeadRiskSummary = {
  label: string;
  connector_breakdown: Record<string, number>;
  top_reasons: string[];
  total_records: number;
};

type LeadSignal = {
  record_id: string;
  connector: string;
  title: string;
  score: number;
  reasons: string[];
};

type GraphNodePayload = {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
  connector?: string | null;
  view: string;
  detail?: string | null;
  score?: number | null;
};

type GraphEdgePayload = {
  id: string;
  source: string;
  target: string;
  label?: string | null;
  view: string;
  strength?: number | null;
};

type PlotlyTraceSpec = {
  type: string;
  name?: string | null;
  x?: unknown[];
  y?: unknown[];
  labels?: string[] | null;
  values?: number[] | null;
  text?: string[] | null;
  mode?: string | null;
  marker?: Record<string, unknown>;
};

type PlotlyChartSpec = {
  id: string;
  title: string;
  chart_type: string;
  description?: string | null;
  data: PlotlyTraceSpec[];
  layout: Record<string, unknown>;
  config: Record<string, unknown>;
};

type CanonicalRecord = {
  id: string;
  entity_type: string;
  title: string;
  subtitle: string | null;
  summary: string | null;
  source: {
    connector: string;
    source_id: string;
    source_name: string;
    last_synced_at: string | null;
  };
  data: Record<string, unknown>;
};

type QueryCitation = {
  source: string;
  source_name: string;
  source_id: string;
  entity_type: string;
  record_id: string;
  title: string;
};

type ChatQueryResponse = {
  session_id: string;
  answer: string;
  memory: WorkspaceMemoryState;
  mode: "qa" | "automation";
  title: string;
  summary: string | null;
  data_sources: WorkspaceDataSourceSummary[];
  workflow: WorkspaceWorkflowPlan | null;
  recommended_scopes: WorkspaceScopeRecommendation[];
  suggested_actions: string[];
  used_sources: string[];
  query_plan: QueryPlan | null;
  execution: QueryExecutionTrace | null;
  records: CanonicalRecord[];
  citations: QueryCitation[];
  confidence: number;
  agent_runs: AgentRunSummary[];
  token_usage: TokenUsageSummary | null;
  graph_reasoning_summary: string | null;
  graph_nodes: GraphNodePayload[];
  graph_edges: GraphEdgePayload[];
  plotly_charts: PlotlyChartSpec[];
  conversion_summary: LeadRiskSummary | null;
  churn_summary: LeadRiskSummary | null;
  conversion_signals: LeadSignal[];
  churn_signals: LeadSignal[];
};

type AssistantView = Omit<ChatQueryResponse, "session_id" | "answer" | "memory">;

const TAB_OPTIONS = [
  { id: "connect", label: "Connect Systems" },
  { id: "ai", label: "AI Assistant" },
  { id: "graph", label: "Knowledge Graph" }
] as const;

type TabId = (typeof TAB_OPTIONS)[number]["id"];
const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function buildDefaultMessages(): ConversationMessage[] {
  return [
    {
      role: "assistant",
      content:
        "Ask about your connected CRM data (by connector name if you want only one system) or describe a campaign or workflow to plan."
    }
  ];
}

function countRowsInDatasetBlob(blob: unknown): number {
  if (!blob || typeof blob !== "object" || Array.isArray(blob)) {
    return 0;
  }
  const o = blob as Record<string, unknown>;
  const contacts = Array.isArray(o.contacts) ? o.contacts.length : 0;
  const companies = Array.isArray(o.companies) ? o.companies.length : 0;
  const records = Array.isArray(o.records) ? o.records.length : 0;
  if (contacts || companies) {
    return contacts + companies;
  }
  return records;
}

function defaultTokenUsage(): TokenUsageSummary {
  return {
    estimated_prompt_tokens: 0,
    actual_prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    by_agent: {},
    source: "estimate"
  };
}

function buildLocalAssistantView(
  sources: SourceRecord[],
  hubspotData: HubSpotWorkspaceData,
  connectorDatasets: ConnectorDatasets
): AssistantView {
  const dataSources: WorkspaceDataSourceSummary[] = [];
  const mcpKeys = new Set(["dubai_dld_mcp"]);

  const merged: ConnectorDatasets = {
    ...(connectorDatasets || {}),
    hubspot: {
      contacts: hubspotData.contacts,
      companies: hubspotData.companies
    }
  };

  const previewKeys = Object.keys(merged).filter((k) => countRowsInDatasetBlob(merged[k]) > 0);
  previewKeys.forEach((key) => {
    const n = countRowsInDatasetBlob(merged[key]);
    dataSources.push({
      key: `${key}-preview`,
      label: `${key} (preview in memory)`,
      status: "active",
      record_count: n,
      detail: `${n} rows under workspace connector key "${key}" — sent to Talk to AI when you ask about contacts/companies.`
    });
  });

  sources
    .filter((source) => source.is_active && mcpKeys.has(source.source_type))
    .forEach((source) => {
      if (dataSources.some((item) => item.key === `${source.source_type}-preview` || item.key === source.id)) {
        return;
      }
      dataSources.push({
        key: source.id,
        label: `${source.source_type} (direct MCP)`,
        status: "active",
        record_count: 1,
        detail: "Direct MCP/API connector available for live query execution in AI Assistant."
      });
    });

  if (dataSources.length === 0) {
    dataSources.push({
      key: "empty",
      label: "No connected data yet",
      status: "idle",
      record_count: 0,
      detail:
        "Connect a CRM, then click **Test connection** to load preview rows into workspace memory (Redis) for Talk to AI."
    });
  }

  return {
    mode: "qa",
    title: "Connected connectors",
    summary: null,
    data_sources: dataSources,
    workflow: null,
    recommended_scopes: [],
    suggested_actions: [],
    used_sources: [],
    query_plan: null,
    execution: null,
    records: [],
    citations: [],
    confidence: 0,
    agent_runs: [],
    token_usage: defaultTokenUsage(),
    graph_reasoning_summary: null,
    graph_nodes: [],
    graph_edges: [],
    plotly_charts: [],
    conversion_summary: null,
    churn_summary: null,
    conversion_signals: [],
    churn_signals: []
  };
}

function hydrateAssistantViewFromMemory(
  memory: WorkspaceMemoryState,
  sources: SourceRecord[],
  hubspotData: HubSpotWorkspaceData,
  connectorDatasets: ConnectorDatasets
): AssistantView {
  const base = buildLocalAssistantView(sources, hubspotData, connectorDatasets);
  const intelligence = memory.lead_intelligence;
  return {
    ...base,
    mode: intelligence?.mode ?? base.mode,
    title: intelligence?.title ?? base.title,
    summary: intelligence?.summary ?? base.summary,
    used_sources: intelligence?.used_sources ?? base.used_sources,
    query_plan: intelligence?.query_plan ?? base.query_plan,
    execution: intelligence?.execution ?? base.execution,
    records: intelligence?.records ?? base.records,
    confidence: intelligence?.confidence ?? base.confidence,
    citations: intelligence?.citations ?? base.citations,
    agent_runs: intelligence?.agent_runs ?? base.agent_runs,
    token_usage: intelligence?.token_usage ?? base.token_usage,
    graph_reasoning_summary: intelligence?.graph_reasoning_summary ?? memory.knowledge_graph_summary ?? base.graph_reasoning_summary,
    graph_nodes: intelligence?.graph_nodes ?? base.graph_nodes,
    graph_edges: intelligence?.graph_edges ?? base.graph_edges,
    plotly_charts: intelligence?.plotly_charts ?? base.plotly_charts,
    conversion_summary: intelligence?.conversion_summary ?? base.conversion_summary,
    churn_summary: intelligence?.churn_summary ?? base.churn_summary,
    conversion_signals: intelligence?.conversion_signals ?? base.conversion_signals,
    churn_signals: intelligence?.churn_signals ?? base.churn_signals
  };
}

function reasonLabel(reason: string): string {
  return reason
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function signalExplanation(signal: LeadSignal, type: "conversion" | "churn"): string {
  const reasons = signal.reasons.map(reasonLabel);
  if (reasons.length === 0) {
    return type === "conversion" ? "Positive conversion indicators detected." : "Possible churn indicators detected.";
  }
  return type === "conversion"
    ? `Likely to convert because of ${reasons.join(", ")}.`
    : `Possible churn risk because of ${reasons.join(", ")}.`;
}

function LeadSignalsSection({
  title,
  summary,
  signals,
  type
}: {
  title: string;
  summary: LeadRiskSummary | null;
  signals: LeadSignal[];
  type: "conversion" | "churn";
}) {
  if (!summary) {
    return null;
  }

  return (
    <details className="ai-list-card">
      <summary style={{ cursor: "pointer", listStyle: "none" }}>
        <div className="ai-list-card__top">
          <strong>{title}</strong>
          <span className="ai-status ai-status--active">{summary.total_records}</span>
        </div>
        <p className="muted">Top reasons: {summary.top_reasons.join(", ") || "none"}</p>
      </summary>
      <div style={{ marginTop: 12, overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Lead</th>
              <th>Source</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 ? (
              <tr>
                <td colSpan={3}>No detailed signals available.</td>
              </tr>
            ) : (
              signals.map((signal) => (
                <tr key={signal.record_id}>
                  <td>{signal.title}</td>
                  <td>{signal.connector}</td>
                  <td>{signalExplanation(signal, type)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function exportReportAsPdf(summary: string) {
  if (typeof window === "undefined") {
    return;
  }

  const reportWindow = window.open("", "_blank", "width=900,height=700");
  if (!reportWindow) {
    return;
  }

  reportWindow.document.write(`
    <html>
      <head>
        <title>LeadScore AI Report</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 32px; color: #111827; }
          h1, h2 { margin-bottom: 12px; }
          .muted { color: #4b5563; }
          .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        </style>
      </head>
      <body>
        <h1>LeadScore AI Knowledge Report</h1>
        <p class="muted">Exported from the frontend knowledge graph workspace.</p>
        <div class="card">
          <h2>Summary</h2>
          <p>${summary}</p>
        </div>
      </body>
    </html>
  `);
  reportWindow.document.close();
  reportWindow.focus();
  reportWindow.print();
}

function getWorkflowNodeStyle(kind: string) {
  const styles: Record<string, { background: string; border: string }> = {
    trigger: { background: "rgba(147, 197, 253, 0.22)", border: "#2563eb" },
    data: { background: "rgba(134, 239, 172, 0.18)", border: "#16a34a" },
    agent: { background: "rgba(196, 181, 253, 0.22)", border: "#7c3aed" },
    action: { background: "rgba(252, 211, 77, 0.22)", border: "#ca8a04" },
    report: { background: "rgba(249, 168, 212, 0.20)", border: "#db2777" },
    connector: { background: "rgba(125, 211, 252, 0.20)", border: "#0284c7" },
    contact: { background: "rgba(196, 181, 253, 0.22)", border: "#7c3aed" },
    company: { background: "rgba(134, 239, 172, 0.18)", border: "#16a34a" },
    lead: { background: "rgba(251, 191, 36, 0.20)", border: "#d97706" },
    outcome: { background: "rgba(244, 114, 182, 0.18)", border: "#db2777" },
    reason: { background: "rgba(203, 213, 225, 0.24)", border: "#64748b" }
  };
  return styles[kind] ?? { background: "rgba(148, 163, 184, 0.18)", border: "#64748b" };
}

function WorkflowNodeCard({ data, selected }: NodeProps<Node<WorkflowNodeData>>) {
  const palette = getWorkflowNodeStyle(data.kind);

  return (
    <>
      <NodeResizer minWidth={150} minHeight={72} isVisible={selected} color={palette.border} lineStyle={{ borderColor: palette.border }} />
      <Handle type="target" position={Position.Left} className="workflow-handle" />
      <div className="workflow-node-content">
        <div className="workflow-node-chip" style={{ background: palette.background, borderColor: palette.border }}>
          {data.kind}
        </div>
        <div className="workflow-node-title">{data.label}</div>
        {data.detail && <div className="muted" style={{ fontSize: 12 }}>{data.detail}</div>}
        {typeof data.score === "number" && <div className="muted" style={{ fontSize: 12 }}>score {data.score}</div>}
      </div>
      <Handle type="source" position={Position.Right} className="workflow-handle" />
    </>
  );
}

const workflowNodeTypes = {
  workflowNode: WorkflowNodeCard
};

function WorkflowCanvasInner({ workflow }: { workflow: WorkspaceWorkflowPlan }) {
  const initialNodes = useMemo<Node<WorkflowNodeData>[]>(() => {
    return workflow.nodes.map((node) => {
      return {
        id: node.id,
        position: { x: node.x, y: node.y },
        type: "workflowNode",
        draggable: true,
        data: { label: node.label, kind: node.kind, detail: null, score: null },
        style: {
          width: 180,
          borderRadius: 18,
          padding: 8,
          border: "1px solid var(--border)",
          background: "color-mix(in srgb, var(--surface) 95%, transparent)",
          boxShadow: "0 16px 28px rgba(15, 23, 42, 0.08)"
        }
      };
    });
  }, [workflow]);

  const initialEdges = useMemo<Edge[]>(() => {
    return workflow.edges.map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: "color-mix(in srgb, var(--primary) 34%, var(--muted))",
        strokeWidth: 2
      },
      labelStyle: {
        fill: "var(--muted)",
        fontWeight: 700
      },
      labelBgPadding: [6, 4],
      labelBgBorderRadius: 999,
      labelBgStyle: {
        fill: "var(--surface)",
        fillOpacity: 0.92
      }
    }));
  }, [workflow]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  return (
    <div className="workflow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={workflowNodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        attributionPosition="bottom-left"
        minZoom={0.4}
        maxZoom={1.6}
        panOnScroll
        selectionOnDrag
        nodesDraggable
        elementsSelectable
      >
        <Background gap={24} size={1} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}

function WorkflowCanvas({ workflow }: { workflow: WorkspaceWorkflowPlan }) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner workflow={workflow} />
    </ReactFlowProvider>
  );
}

function OperationsCanvas({ assistantView }: { assistantView: AssistantView }) {
  return (
    <section className="card ai-workspace-card">
      {(assistantView.conversion_summary || assistantView.churn_summary) && (
        <div className="ai-section">
          <h3>Lead Intelligence</h3>
          <div className="ai-list-grid">
            <LeadSignalsSection
              title="Likely conversion signals"
              summary={assistantView.conversion_summary}
              signals={assistantView.conversion_signals}
              type="conversion"
            />
            <LeadSignalsSection
              title="Likely churn signals"
              summary={assistantView.churn_summary}
              signals={assistantView.churn_signals}
              type="churn"
            />
          </div>
        </div>
      )}

      {assistantView.mode === "automation" && assistantView.workflow ? (
        <WorkflowCanvas workflow={assistantView.workflow} />
      ) : (
        <div className="ai-section">
          <h3>Connected Data Inputs</h3>
          <div className="ai-list-grid">
            {assistantView.data_sources.map((source) => (
              <div key={source.key} className="ai-list-card">
                <div className="ai-list-card__top">
                  <strong>{source.label}</strong>
                  <span className={`ai-status ai-status--${source.status}`}>{source.status}</span>
                </div>
                <div className="ai-list-card__value">{source.record_count}</div>
                {source.detail && <p className="muted">{source.detail}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function AnalyticsAndChatTab({
  assistantView,
  hubspotData,
  connectorDatasets,
  messages,
  draft,
  chatBusy,
  memoryReady,
  onDraftChange,
  onSend
}: {
  assistantView: AssistantView;
  hubspotData: HubSpotWorkspaceData;
  connectorDatasets: ConnectorDatasets;
  messages: ConversationMessage[];
  draft: string;
  chatBusy: boolean;
  memoryReady: boolean;
  onDraftChange: (value: string) => void;
  onSend: () => void;
}) {
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const promptSuggestions = [
    "What contacts do I have right now?",
    "How many companies are loaded?",
    "Plan a nurture campaign for new leads",
    "Build a follow-up workflow for leads without owners"
  ];

  useEffect(() => {
    if (!chatLogRef.current) {
      return;
    }
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [messages]);

  return (
    <div className="workspace-split ai-split">
      <OperationsCanvas assistantView={assistantView} />

      <section className="card chat-shell">
        <div className="chat-shell__header">
          <div>
            <div className="ai-mode-pill">AI Assistant</div>
            <h2>Lead scoring and churn analysis</h2>
          </div>
          {!memoryReady && <span className="muted">Loading session...</span>}
        </div>

        <div className="prompt-chip-list">
          {promptSuggestions.map((prompt) => (
            <button key={prompt} type="button" className="prompt-chip" onClick={() => onDraftChange(prompt)}>
              {prompt}
            </button>
          ))}
        </div>

        <div className="chat-log chat-log--pro" ref={chatLogRef}>
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role}`}>
              <strong>{message.role === "assistant" ? "AI" : "You"}</strong>
              {message.role === "assistant" ? (
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                </div>
              ) : (
                <p>{message.content}</p>
              )}
            </div>
          ))}
        </div>

        <div className="chat-composer">
          <textarea
            rows={3}
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            placeholder="Ask a question or describe a campaign / automation you want the AI to plan..."
          />
          <div className="chat-composer__footer">
            <button className="button" type="button" onClick={onSend} disabled={!memoryReady || chatBusy}>
              {chatBusy ? "Thinking..." : "Send"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function KnowledgeGraphCanvas({
  nodes,
  edges
}: {
  nodes: GraphNodePayload[];
  edges: GraphEdgePayload[];
}) {
  const flowNodes = useMemo<Node<WorkflowNodeData>[]>(() => {
    return nodes.map((node) => ({
      id: node.id,
      position: { x: node.x, y: node.y },
      type: "workflowNode",
      draggable: true,
      data: {
        label: node.label,
        kind: node.kind,
        detail: node.detail ?? null,
        score: node.score ?? null
      },
      style: {
        width: 200,
        borderRadius: 18,
        padding: 8,
        border: `1px solid ${getWorkflowNodeStyle(node.kind).border}`,
        background: getWorkflowNodeStyle(node.kind).background,
        boxShadow: "0 16px 28px rgba(15, 23, 42, 0.08)"
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left
    }));
  }, [nodes]);

  const flowEdges = useMemo<Edge[]>(() => {
    return edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: "color-mix(in srgb, var(--primary) 34%, var(--muted))",
        strokeWidth: Math.max(1.5, edge.strength ?? 1.5)
      }
    }));
  }, [edges]);
  const graphKey = useMemo(
    () => `${flowNodes.map((node) => node.id).join("|")}::${flowEdges.map((edge) => edge.id).join("|")}`,
    [flowNodes, flowEdges]
  );

  return (
    <div className="workflow-canvas">
      <ReactFlow
        key={graphKey}
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={workflowNodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15, duration: 500 }}
        attributionPosition="bottom-left"
        minZoom={0.35}
        maxZoom={1.8}
        panOnScroll
        nodesDraggable
        elementsSelectable
      >
        <Background gap={20} size={1} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}

function PlotlyChartsPanel({
  charts
}: {
  charts: PlotlyChartSpec[];
}) {
  const [selectedChartId, setSelectedChartId] = useState<string>(charts[0]?.id ?? "");

  useEffect(() => {
    if (!charts.some((chart) => chart.id === selectedChartId)) {
      setSelectedChartId(charts[0]?.id ?? "");
    }
  }, [charts, selectedChartId]);

  const selectedChart = charts.find((chart) => chart.id === selectedChartId) ?? charts[0] ?? null;

  if (!selectedChart) {
    return (
      <div className="ai-section">
        <p className="muted">No Plotly charts available for the current analysis.</p>
      </div>
    );
  }

  return (
    <div className="ai-section">
      {charts.length > 1 && (
        <div className="prompt-chip-list" style={{ marginBottom: 16 }}>
          {charts.map((chart) => (
            <button
              key={chart.id}
              type="button"
              className={`prompt-chip ${selectedChart.id === chart.id ? "active" : ""}`}
              onClick={() => setSelectedChartId(chart.id)}
            >
              {chart.title}
            </button>
          ))}
        </div>
      )}
      {selectedChart.description && (
        <p className="muted" style={{ marginBottom: 12 }}>
          {selectedChart.description}
        </p>
      )}
      <div className="workflow-canvas" style={{ padding: 12 }}>
        <Plot
          data={selectedChart.data as never}
          layout={
            {
              autosize: true,
              font: { color: "#cbd5e1" },
              ...selectedChart.layout
            } as never
          }
          config={
            {
              responsive: true,
              displaylogo: false,
              ...selectedChart.config
            } as never
          }
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
    </div>
  );
}

function KnowledgeGraphTab({
  assistantView,
  connectedCount
}: {
  assistantView: AssistantView;
  connectedCount: number;
}) {
  const activeConnectorCount = useMemo(() => {
    const fromGraph = new Set(
      assistantView.graph_nodes.map((node) => node.connector).filter((value): value is string => Boolean(value))
    ).size;
    return fromGraph || connectedCount;
  }, [assistantView.graph_nodes, connectedCount]);
  const hasCharts = assistantView.plotly_charts.length > 0;
  const hasNetwork = assistantView.graph_nodes.length > 0;

  return (
    <section className="card">
      {hasCharts ? (
        <PlotlyChartsPanel charts={assistantView.plotly_charts} />
      ) : hasNetwork ? (
        <ReactFlowProvider>
          <KnowledgeGraphCanvas nodes={assistantView.graph_nodes} edges={assistantView.graph_edges} />
        </ReactFlowProvider>
      ) : (
        <div className="ai-section">
          <p className="muted">Run a Talk to AI query first to generate the current-session knowledge graph.</p>
        </div>
      )}
    </section>
  );
}

function shouldAutoOpenKnowledgeGraph(message: string): boolean {
  const value = message.toLowerCase();
  return (
    value.includes("knowledge graph") ||
    value.includes("knowldge graph") ||
    value.includes("create a graph") ||
    value.includes("generate a graph") ||
    value.includes("bar chart") ||
    value.includes("chart") ||
    value.includes("plotly") ||
    value.includes("graph based on this") ||
    value.includes("illustrate churn") ||
    value.includes("show graph")
  );
}

export function IntelligenceWorkspace({
  initialSources,
  providers,
  backendAvailable
}: {
  initialSources: SourceRecord[];
  providers: ProviderDefinition[];
  backendAvailable: boolean;
}) {
  const [activeTab, setActiveTab] = useState<TabId>("connect");
  const [sources, setSources] = useState<SourceRecord[]>(initialSources);
  const [hubspotData, setHubspotData] = useState<HubSpotWorkspaceData>({
    contacts: [],
    companies: []
  });
  const [connectorDatasets, setConnectorDatasets] = useState<ConnectorDatasets>({});
  const [messages, setMessages] = useState<ConversationMessage[]>(buildDefaultMessages);
  const [draft, setDraft] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [memorySessionId, setMemorySessionId] = useState("");
  const [memoryReady, setMemoryReady] = useState(false);
  const [assistantView, setAssistantView] = useState<AssistantView>(() =>
    buildLocalAssistantView(initialSources, { contacts: [], companies: [] }, {})
  );
  const knowledgeGraphSummary =
    assistantView.graph_reasoning_summary ??
    "The current frontend organizes lead operations across three layers: connected source systems, AI analysis, and reporting. CRM systems remain primary lead-entry points, enterprise suites enrich account context, and the scoring platform centralizes operational decisions.";

  useEffect(() => {
    setAssistantView((current) => {
      if (current.mode === "automation" && current.workflow) {
        return current;
      }
      return {
        ...buildLocalAssistantView(sources, hubspotData, connectorDatasets),
        used_sources: current.used_sources,
        query_plan: current.query_plan,
        execution: current.execution,
        records: current.records,
        citations: current.citations,
        confidence: current.confidence,
        agent_runs: current.agent_runs,
        token_usage: current.token_usage,
        graph_reasoning_summary: current.graph_reasoning_summary,
        graph_nodes: current.graph_nodes,
        graph_edges: current.graph_edges,
        plotly_charts: current.plotly_charts,
        conversion_summary: current.conversion_summary,
        churn_summary: current.churn_summary,
        conversion_signals: current.conversion_signals,
        churn_signals: current.churn_signals
      };
    });
  }, [sources, hubspotData, connectorDatasets]);

  function handleHubSpotWorkspaceData(data: HubSpotWorkspaceData) {
    setHubspotData(data);
    setConnectorDatasets((prev) => ({
      ...prev,
      hubspot: { contacts: data.contacts, companies: data.companies }
    }));
  }

  function handleWorkspaceMemoryUpdated(mem: unknown) {
    const m = mem as WorkspaceMemoryState;
    if (m.connector_datasets && typeof m.connector_datasets === "object") {
      setConnectorDatasets(m.connector_datasets as ConnectorDatasets);
    }
    if (m.lead_intelligence) {
      setAssistantView((current) => ({
        ...current,
        ...hydrateAssistantViewFromMemory(
          m,
          m.sources?.length ? m.sources : sources,
          m.hubspot_data ?? hubspotData,
          (m.connector_datasets as ConnectorDatasets) ?? connectorDatasets
        )
      }));
    }
  }

  async function persistWorkspaceMemory(sessionId: string, conversation?: ConversationMessage[]) {
    const response = await fetch(`${API_URL}/api/workspace-memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
        session_id: sessionId,
        active_tab: activeTab,
        sources,
        hubspot_data: hubspotData,
        connector_datasets: {
          ...connectorDatasets,
          hubspot: {
            contacts: hubspotData.contacts,
            companies: hubspotData.companies
          }
        },
        knowledge_graph_summary: knowledgeGraphSummary,
        ...(conversation ? { conversation } : {})
      })
    });
    if (!response.ok) {
      throw new Error("Failed to persist workspace memory");
    }
    return (await response.json()) as WorkspaceMemoryState;
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const sessionId = window.crypto.randomUUID();
    setMemorySessionId(sessionId);
    setActiveTab("connect");
    setHubspotData({ contacts: [], companies: [] });
    setConnectorDatasets({});
    setMessages(buildDefaultMessages());
    setAssistantView(buildLocalAssistantView(initialSources, { contacts: [], companies: [] }, {}));

    if (!backendAvailable) {
      setMemoryReady(true);
      return;
    }

    setMemoryReady(true);
  }, [backendAvailable, initialSources]);

  useEffect(() => {
    if (!backendAvailable || !memorySessionId || !memoryReady) {
      return;
    }

    persistWorkspaceMemory(memorySessionId).catch(() => undefined);
  }, [
    activeTab,
    sources,
    hubspotData,
    connectorDatasets,
    knowledgeGraphSummary,
    memorySessionId,
    memoryReady,
    backendAvailable
  ]);

  async function handleChatSend() {
    if (!draft.trim() || !memorySessionId || chatBusy) {
      return;
    }

    setChatBusy(true);
    const prompt = draft.trim();
    const userMessage: ConversationMessage = { role: "user", content: prompt };
    const nextConversation = [...messages, userMessage];
    setMessages(nextConversation);
    setDraft("");

    if (!backendAvailable) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "The backend is offline, so shared workspace memory is unavailable right now."
        }
      ]);
      setChatBusy(false);
      return;
    }

    try {
      await persistWorkspaceMemory(memorySessionId);
      const response = await fetch(`${API_URL}/api/chat/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: memorySessionId,
          message: userMessage.content,
          connector_scope: []
        })
      });
      const data = (await response.json()) as ChatQueryResponse | { detail?: string };
      if (!response.ok || !("memory" in data)) {
        throw new Error(("detail" in data && data.detail) || "Workspace chat failed");
      }
      setMessages(data.memory.conversation);
      if (data.memory.connector_datasets && typeof data.memory.connector_datasets === "object") {
        setConnectorDatasets(data.memory.connector_datasets as ConnectorDatasets);
      }
      setAssistantView({
        mode: data.mode,
        title: data.title,
        summary: data.summary,
        data_sources: data.data_sources,
        workflow: data.workflow,
        recommended_scopes: data.recommended_scopes,
        suggested_actions: data.suggested_actions,
        used_sources: data.used_sources,
        query_plan: data.query_plan,
        execution: data.execution,
        records: data.records,
        citations: data.citations,
        confidence: data.confidence,
        agent_runs: data.agent_runs,
        token_usage: data.token_usage,
        graph_reasoning_summary: data.graph_reasoning_summary,
        graph_nodes: data.graph_nodes,
        graph_edges: data.graph_edges,
        plotly_charts: data.plotly_charts,
        conversion_summary: data.conversion_summary,
        churn_summary: data.churn_summary,
        conversion_signals: data.conversion_signals ?? [],
        churn_signals: data.churn_signals ?? []
      });
      if (shouldAutoOpenKnowledgeGraph(prompt) && data.graph_nodes.length > 0) {
        setActiveTab("graph");
      }
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: error instanceof Error ? error.message : "Workspace chat failed"
        }
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <h1 className="title">AI Lead Scoring Churn Analysis Platform</h1>
      </section>

      {!backendAvailable && (
        <section className="card warning">
          <strong>API offline mode</strong>
          <p className="muted">
            The frontend is running, but the backend provider catalog could not be reached. The workspace is still visible, but connector actions will stay disabled until the API is started.
          </p>
        </section>
      )}

      <section className="card">
        <div className="tab-list" role="tablist" aria-label="LeadScore workspace tabs">
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "connect" && (
        <div className="grid">
          <SourceManager
            initialSources={sources}
            providers={providers}
            onSourcesChanged={setSources}
            onHubSpotDataChanged={handleHubSpotWorkspaceData}
            hubspotData={hubspotData}
            connectorDatasets={connectorDatasets}
            workspaceSessionId={memoryReady ? memorySessionId : null}
            onWorkspaceMemoryUpdated={handleWorkspaceMemoryUpdated}
          />
        </div>
      )}

      {activeTab === "ai" && (
        <AnalyticsAndChatTab
          assistantView={assistantView}
          hubspotData={hubspotData}
          connectorDatasets={connectorDatasets}
          messages={messages}
          draft={draft}
          chatBusy={chatBusy}
          memoryReady={memoryReady}
          onDraftChange={setDraft}
          onSend={handleChatSend}
        />
      )}

      {activeTab === "graph" && (
        <KnowledgeGraphTab assistantView={assistantView} connectedCount={sources.length} />
      )}
    </div>
  );
}
