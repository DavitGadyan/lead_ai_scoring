"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
};

type WorkspaceScopeRecommendation = {
  scope: string;
  label: string;
  required: boolean;
  reason: string;
};

type WorkspaceChatResponse = {
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
};

type AssistantView = Omit<WorkspaceChatResponse, "session_id" | "answer" | "memory">;

const TAB_OPTIONS = [
  { id: "connect", label: "Connect Systems" },
  { id: "ai", label: "Talk to AI" },
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

function buildLocalAssistantView(
  sources: SourceRecord[],
  hubspotData: HubSpotWorkspaceData,
  connectorDatasets: ConnectorDatasets
): AssistantView {
  const dataSources: WorkspaceDataSourceSummary[] = [];

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

  sources.forEach((source, index) => {
    const previewCount = countRowsInDatasetBlob(merged[source.source_type]);
    dataSources.push({
      key: `${source.source_type}-${index}`,
      label: source.name,
      status: source.is_active ? "connected" : "inactive",
      record_count: previewCount,
      detail:
        previewCount > 0
          ? `${source.source_type}: ${previewCount} preview rows in workspace memory for this connector type.`
          : `${source.source_type} connector saved (run Test connection to load preview for AI).`
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
    title: "Connected data workspace",
    summary: "Summarizes saved connectors and per-connector preview datasets the assistant can use.",
    data_sources: dataSources,
    workflow: null,
    recommended_scopes: [],
    suggested_actions: []
  };
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
    report: { background: "rgba(249, 168, 212, 0.20)", border: "#db2777" }
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
        data: { label: node.label, kind: node.kind },
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

function OperationsCanvas({
  assistantView,
  hubspotData,
  connectorDatasets,
  sources
}: {
  assistantView: AssistantView;
  hubspotData: HubSpotWorkspaceData;
  connectorDatasets: ConnectorDatasets;
  sources: SourceRecord[];
}) {
  const merged: ConnectorDatasets = {
    ...(connectorDatasets || {}),
    hubspot: { contacts: hubspotData.contacts, companies: hubspotData.companies }
  };
  const previewRecords = Object.keys(merged).reduce(
    (sum, key) => sum + countRowsInDatasetBlob(merged[key]),
    0
  );
  const metricCards = [
    { label: "All CRM preview rows (memory)", value: previewRecords },
    { label: "Connector keys with data", value: Object.keys(merged).filter((k) => countRowsInDatasetBlob(merged[k]) > 0).length },
    { label: "Saved connectors", value: sources.length },
    { label: "Mode", value: assistantView.mode === "automation" ? "Automation" : "QA" }
  ];

  return (
    <section className="card ai-workspace-card">
      <div className="ai-workspace-header">
        <div>
          <div className="ai-mode-pill">{assistantView.mode === "automation" ? "Automation Planner" : "Data QA"}</div>
          <h2>{assistantView.title}</h2>
          {assistantView.summary && <p className="muted">{assistantView.summary}</p>}
        </div>
      </div>

      <div className="ai-metric-grid">
        {metricCards.map((metric) => (
          <div key={metric.label} className="ai-metric-card">
            <span className="muted">{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

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
  sources,
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
  sources: SourceRecord[];
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
      <OperationsCanvas
        assistantView={assistantView}
        hubspotData={hubspotData}
        connectorDatasets={connectorDatasets}
        sources={sources}
      />

      <section className="card chat-shell">
        <div className="chat-shell__header">
          <div>
            <div className="ai-mode-pill">AI Copilot</div>
            <h2>CRM data, QA, and automation</h2>
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
              <p>{message.content}</p>
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

function KnowledgeGraphTab({
  providers,
  connectedCount,
  summary
}: {
  providers: ProviderDefinition[];
  connectedCount: number;
  summary: string;
}) {
  const crmCount = providers.filter((provider) => provider.category === "crm").length;
  const enterpriseCount = providers.filter((provider) => provider.category === "enterprise").length;

  return (
    <div className="grid">
      <section className="card">
        <h2>Knowledge Graph View</h2>
        <p className="muted">
          This tab visualizes how systems, processes, and AI outputs connect. It is structured so you can later replace the static graph with backend-generated graph data.
        </p>
        <div className="graph-shell">
          <svg viewBox="0 0 760 320" className="graph-svg" role="img" aria-label="Knowledge graph of connected systems">
            <line x1="120" y1="80" x2="300" y2="160" className="graph-line" />
            <line x1="120" y1="240" x2="300" y2="160" className="graph-line" />
            <line x1="300" y1="160" x2="500" y2="90" className="graph-line" />
            <line x1="300" y1="160" x2="500" y2="230" className="graph-line" />
            <line x1="500" y1="90" x2="660" y2="90" className="graph-line" />
            <line x1="500" y1="230" x2="660" y2="230" className="graph-line" />
            <g>
              <circle cx="120" cy="80" r="44" className="graph-node primary" />
              <text x="120" y="76" textAnchor="middle" className="graph-text-title">CRM</text>
              <text x="120" y="96" textAnchor="middle" className="graph-text-sub">{crmCount} systems</text>
            </g>
            <g>
              <circle cx="120" cy="240" r="44" className="graph-node secondary" />
              <text x="120" y="236" textAnchor="middle" className="graph-text-title">ERP</text>
              <text x="120" y="256" textAnchor="middle" className="graph-text-sub">{enterpriseCount} suites</text>
            </g>
            <g>
              <circle cx="300" cy="160" r="52" className="graph-node center" />
              <text x="300" y="156" textAnchor="middle" className="graph-text-title">LeadScore</text>
              <text x="300" y="176" textAnchor="middle" className="graph-text-sub">AI core</text>
            </g>
            <g>
              <circle cx="500" cy="90" r="40" className="graph-node accent" />
              <text x="500" y="86" textAnchor="middle" className="graph-text-title">Chat</text>
              <text x="500" y="106" textAnchor="middle" className="graph-text-sub">insights</text>
            </g>
            <g>
              <circle cx="500" cy="230" r="40" className="graph-node accent" />
              <text x="500" y="226" textAnchor="middle" className="graph-text-title">Scores</text>
              <text x="500" y="246" textAnchor="middle" className="graph-text-sub">actions</text>
            </g>
            <g>
              <circle cx="660" cy="90" r="34" className="graph-node report" />
              <text x="660" y="86" textAnchor="middle" className="graph-text-title">PDF</text>
              <text x="660" y="104" textAnchor="middle" className="graph-text-sub">report</text>
            </g>
            <g>
              <circle cx="660" cy="230" r="34" className="graph-node report" />
              <text x="660" y="226" textAnchor="middle" className="graph-text-title">Ops</text>
              <text x="660" y="244" textAnchor="middle" className="graph-text-sub">handoff</text>
            </g>
          </svg>
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <h3>Conversation Summary</h3>
          <p className="muted">{summary}</p>
          <ul>
            <li>{connectedCount} connectors are currently saved in the workspace.</li>
            <li>CRM systems should usually be connected before ERP or warehouse data.</li>
            <li>AI chat can be used to explain why certain integrations should be prioritized.</li>
          </ul>
        </div>
        <div className="card">
          <h3>Key Points Report</h3>
          <button className="button" type="button" onClick={() => exportReportAsPdf(summary)}>
            Export PDF Report
          </button>
        </div>
      </section>
    </div>
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
    "The current frontend organizes lead operations across three layers: connected source systems, AI analysis, and reporting. CRM systems remain primary lead-entry points, enterprise suites enrich account context, and the scoring platform centralizes operational decisions.";

  useEffect(() => {
    setAssistantView((current) =>
      current.mode === "automation" && current.workflow
        ? current
        : buildLocalAssistantView(sources, hubspotData, connectorDatasets)
    );
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

    const existingSession = window.localStorage.getItem("leadscore-workspace-session-v2");
    const sessionId = existingSession || window.crypto.randomUUID();
    if (!existingSession) {
      window.localStorage.setItem("leadscore-workspace-session-v2", sessionId);
    }
    setMemorySessionId(sessionId);

    if (!backendAvailable) {
      setMemoryReady(true);
      return;
    }

    let cancelled = false;
    fetch(`${API_URL}/api/workspace-memory/${sessionId}`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Failed to load workspace memory");
        }
        return (await response.json()) as WorkspaceMemoryState;
      })
      .then((memory) => {
        if (cancelled) {
          return;
        }
        if (memory.active_tab && TAB_OPTIONS.some((tab) => tab.id === memory.active_tab)) {
          setActiveTab(memory.active_tab as TabId);
        }
        if (memory.sources.length > 0) {
          setSources(memory.sources);
        }
        const hubSlice = memory.connector_datasets?.hubspot;
        if (hubSlice && typeof hubSlice === "object" && !Array.isArray(hubSlice)) {
          const rec = hubSlice as { contacts?: HubSpotWorkspaceData["contacts"]; companies?: HubSpotWorkspaceData["companies"] };
          setHubspotData({
            contacts: Array.isArray(rec.contacts) ? rec.contacts : [],
            companies: Array.isArray(rec.companies) ? rec.companies : []
          });
        } else if (memory.hubspot_data) {
          setHubspotData(memory.hubspot_data);
        }
        if (memory.connector_datasets && typeof memory.connector_datasets === "object") {
          setConnectorDatasets(memory.connector_datasets as ConnectorDatasets);
        }
        const hasLegacyConversation = memory.conversation.some(
          (message) =>
            message.content.includes("Start with HubSpot or Salesforce") ||
            message.content.includes("Focus on three questions") ||
            message.content.includes("companyies")
        );
        if (memory.conversation.length > 0 && !hasLegacyConversation) {
          setMessages(memory.conversation);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) {
          setMemoryReady(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [backendAvailable]);

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
    const userMessage: ConversationMessage = { role: "user", content: draft.trim() };
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
      const response = await fetch(`${API_URL}/api/workspace-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: memorySessionId,
          message: userMessage.content
        })
      });
      const data = (await response.json()) as WorkspaceChatResponse | { detail?: string };
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
        suggested_actions: data.suggested_actions
      });
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
        <h1 className="title">LeadScore AI Workspace</h1>
        <p className="muted">
          Manage CRM/ERP connectors, question loaded preview data across connectors, and let the AI plan campaigns or automations from one workspace.
        </p>
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
          <section className="card">
            <h2>CRM / ERP Import Hub</h2>
            <p className="muted">
              Select from backend-accessible systems and connectors. The frontend uses the provider catalog exposed by the backend, which is the place to surface MCP-accessible or installed systems over time.
            </p>
          </section>
          <SourceManager
            initialSources={sources}
            providers={providers}
            onSourcesChanged={setSources}
            onHubSpotDataChanged={handleHubSpotWorkspaceData}
            workspaceSessionId={memoryReady ? memorySessionId : null}
            onWorkspaceMemoryUpdated={handleWorkspaceMemoryUpdated}
          />
        </div>
      )}

      {activeTab === "ai" && (
        <AnalyticsAndChatTab
          assistantView={assistantView}
          sources={sources}
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
        <KnowledgeGraphTab providers={providers} connectedCount={sources.length} summary={knowledgeGraphSummary} />
      )}
    </div>
  );
}
