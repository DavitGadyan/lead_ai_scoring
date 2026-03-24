"use client";

import { useMemo, useState } from "react";

type SourceRecord = {
  id: string;
  name: string;
  source_type: string;
  is_active: boolean;
  created_at: string;
  last_synced_at: string | null;
  config: {
    redirect_uri?: string | null;
    connection_url?: string | null;
    query?: string | null;
    database?: string | null;
    collection?: string | null;
    file_path?: string | null;
    sheet_name?: string | number | null;
    client_id?: string | null;
    client_secret?: string | null;
    access_token?: string | null;
    refresh_token?: string | null;
    base_url?: string | null;
    zoho_accounts_host?: string | null;
    oauth_scope?: string | null;
  };
};

type ProviderField = {
  key: string;
  label: string;
  required: boolean;
  secret: boolean;
  kind: string;
  placeholder?: string | null;
  help_text?: string | null;
};

type ProviderDefinition = {
  key: string;
  label: string;
  category: string;
  description: string;
  recommended_order: number;
  fields: ProviderField[];
};

type SourceTestResult = {
  source_type: string;
  connection_ok: boolean;
  sample_count: number;
  sample_fields: string[];
  normalized_fields: string[];
  preview_rows?: Array<Record<string, unknown>>;
};

type HubSpotPreviewRecord = {
  external_id?: string | null;
  full_name?: string | null;
  email?: string | null;
  company?: string | null;
  job_title?: string | null;
  industry?: string | null;
  country?: string | null;
};

type HubSpotPreviewResponse = SourceTestResult & {
  records: HubSpotPreviewRecord[];
};

type HubSpotBrowseResponse = {
  object_name: string;
  records: Array<Record<string, string | number | null>>;
  current_after: string | null;
  next_after: string | null;
  limit: number;
};

export type HubSpotWorkspaceData = {
  contacts: Array<Record<string, string | number | null>>;
  companies: Array<Record<string, string | number | null>>;
};

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const HUBSPOT_OAUTH_MESSAGE = "leadscore:hubspot-oauth";
const ZOHO_OAUTH_MESSAGE = "leadscore:zoho-oauth";
const DEFAULT_ZOHO_SCOPE = "ZohoCRM.modules.leads.READ ZohoCRM.modules.contacts.READ";
const HUBSPOT_SCOPE =
  "crm.objects.contacts.read crm.objects.companies.read crm.objects.owners.read";
const HUBSPOT_OPTIONAL_SCOPE = [
  "crm.objects.contacts.write",
  "crm.objects.companies.write",
  "crm.lists.read",
  "crm.lists.write",
  "marketing.campaigns.read",
  "marketing.campaigns.write",
  "content",
  "automation",
  "automation.sequences.read",
  "automation.sequences.enrollments.write",
  "communication_preferences.read_write",
  "crm.objects.deals.read",
  "crm.objects.deals.write",
  "crm.objects.leads.read",
  "crm.objects.leads.write"
].join(" ");

function getDefaultState(provider: ProviderDefinition) {
  const config = Object.fromEntries(
    provider.fields.map((field) => [field.key, field.placeholder ?? ""])
  ) as Record<string, string>;

  return {
    name: `${provider.key}-connector`,
    source_type: provider.key,
    is_active: true,
    config
  };
}

function parseMaybeJson(value: string) {
  if (!value.trim()) {
    return {};
  }
  return JSON.parse(value);
}

function getPayload(
  formState: ReturnType<typeof getDefaultState>,
  provider: ProviderDefinition | undefined
) {
  if (!provider) {
    throw new Error("Provider not found");
  }

  const configEntries = provider.fields.map((field) => {
    const rawValue = formState.config[field.key] ?? "";
    if (!rawValue.trim()) {
      return [field.key, null];
    }
    if (field.kind === "json") {
      return [field.key, parseMaybeJson(rawValue)];
    }
    return [field.key, rawValue];
  });

  const config = Object.fromEntries(configEntries) as Record<string, unknown>;

  if (provider.key === "hubspot") {
    return {
      name: formState.name,
      source_type: formState.source_type,
      is_active: formState.is_active,
      config: {
        ...config,
        access_token: formState.config.access_token || null,
        refresh_token: formState.config.refresh_token || null
      }
    };
  }

  if (provider.key === "zoho") {
    const zohoRest = { ...config };
    delete zohoRest.oauth_scope;
    return {
      name: formState.name,
      source_type: formState.source_type,
      is_active: formState.is_active,
      config: {
        ...zohoRest,
        access_token: formState.config.access_token || null,
        refresh_token: formState.config.refresh_token || null,
        base_url: formState.config.base_url || null
      }
    };
  }

  return {
    name: formState.name,
    source_type: formState.source_type,
    is_active: formState.is_active,
    config
  };
}

export function SourceManager({
  initialSources,
  providers,
  onSourcesChanged,
  onHubSpotDataChanged,
  workspaceSessionId,
  onWorkspaceMemoryUpdated
}: {
  initialSources: SourceRecord[];
  providers: ProviderDefinition[];
  onSourcesChanged?: (sources: SourceRecord[]) => void;
  onHubSpotDataChanged?: (data: HubSpotWorkspaceData) => void;
  /** When set, successful CRM **Test connection** ingests ``preview_rows`` into workspace memory (Redis) for Talk to AI. */
  workspaceSessionId?: string | null;
  /** Called after connector preview is written to workspace memory (optional refresh). */
  onWorkspaceMemoryUpdated?: (memory: unknown) => void;
}) {
  const [sources, setSources] = useState<SourceRecord[]>(initialSources);
  const [sourceType, setSourceType] = useState<string>(providers[0]?.key ?? "hubspot");
  const [formState, setFormState] = useState(
    providers[0] ? getDefaultState(providers[0]) : { name: "", source_type: "", is_active: true, config: {} }
  );
  const [busy, setBusy] = useState<"idle" | "testing" | "saving">("idle");
  const [hubspotBusy, setHubspotBusy] = useState(false);
  const [zohoBusy, setZohoBusy] = useState(false);
  const [hubspotContacts, setHubspotContacts] = useState<HubSpotBrowseResponse | null>(null);
  const [hubspotCompanies, setHubspotCompanies] = useState<HubSpotBrowseResponse | null>(null);
  const [hubspotBrowseBusy, setHubspotBrowseBusy] = useState<"" | "contacts" | "companies">("");
  const [hubspotPrev, setHubspotPrev] = useState<{ contacts: string[]; companies: string[] }>({
    contacts: [],
    companies: []
  });
  const [message, setMessage] = useState("");
  const [testResult, setTestResult] = useState<SourceTestResult | null>(null);
  const hasProviders = providers.length > 0;

  const selectedSourceMeta = useMemo(
    () => providers.find((provider) => provider.key === sourceType),
    [providers, sourceType]
  );

  const groupedProviders = useMemo(() => {
    return providers.reduce<Record<string, ProviderDefinition[]>>((groups, provider) => {
      groups[provider.category] = [...(groups[provider.category] ?? []), provider];
      return groups;
    }, {});
  }, [providers]);

  function updateConfig(name: string, value: string) {
    setFormState((current) => ({
      ...current,
      config: {
        ...current.config,
        [name]: value
      }
    }));
  }

  function getHubSpotBrowsePayload(objectName: "contacts" | "companies", after: string | null = null) {
    return {
      client_id: formState.config.client_id || null,
      client_secret: formState.config.client_secret || null,
      access_token: formState.config.access_token || null,
      refresh_token: formState.config.refresh_token || null,
      object_name: objectName,
      after,
      limit: 5
    };
  }

  function getHubSpotSourcePayload(objectName: "contacts" | "companies", after: string | null = null) {
    return {
      name: formState.name || `hubspot-${objectName}`,
      source_type: "hubspot",
      is_active: true,
      config: {
        ...getHubSpotBrowsePayload(objectName, after),
        params: {
          limit: 5,
          ...(after ? { after } : {})
        }
      }
    };
  }

  function applyHubSpotPreview(objectName: "contacts" | "companies", data: HubSpotPreviewResponse) {
    const mappedRows = data.records.map((record) => {
      if (objectName === "contacts") {
        return {
          id: record.external_id ?? null,
          name: record.full_name ?? null,
          email: record.email ?? null,
          company: record.company ?? null,
          jobtitle: record.job_title ?? null
        };
      }

      return {
        id: record.external_id ?? null,
        name: record.company ?? record.full_name ?? null,
        domain: null,
        industry: record.industry ?? null,
        country: record.country ?? null
      };
    });

    const previewState: HubSpotBrowseResponse = {
      object_name: objectName,
      records: mappedRows,
      current_after: null,
      next_after: null,
      limit: 5
    };

    if (objectName === "contacts") {
      setHubspotContacts(previewState);
      onHubSpotDataChanged?.({
        contacts: mappedRows,
        companies: hubspotCompanies?.records ?? []
      });
    } else {
      setHubspotCompanies(previewState);
      onHubSpotDataChanged?.({
        contacts: hubspotContacts?.records ?? [],
        companies: mappedRows
      });
    }
  }

  function zohoApiOriginMatches(origin: string): boolean {
    try {
      return origin === new URL(API_URL).origin;
    } catch {
      return false;
    }
  }

  async function handleZohoOAuth() {
    if (!selectedSourceMeta || selectedSourceMeta.key !== "zoho") {
      return;
    }

    const clientId = formState.config.client_id?.trim();
    const clientSecret = formState.config.client_secret?.trim();
    const apiBase = API_URL.replace(/\/$/, "");
    const defaultRedirect = `${apiBase}/api/oauth/zoho/callback`;
    const redirectUri = formState.config.redirect_uri?.trim() || defaultRedirect;
    const accountsHost = formState.config.zoho_accounts_host?.trim() || "accounts.zoho.com";
    const scope =
      formState.config.oauth_scope?.trim() || DEFAULT_ZOHO_SCOPE;

    setZohoBusy(true);
    setMessage("");

    try {
      updateConfig("redirect_uri", redirectUri);
      const response = await fetch(`${API_URL}/api/oauth/zoho/authorize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          client_secret: clientSecret,
          redirect_uri: redirectUri,
          zoho_accounts_host: accountsHost,
          scope
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? "Failed to start Zoho OAuth");
      }

      const popup = window.open(data.authorize_url, "zoho-oauth", "width=900,height=860");
      if (!popup) {
        throw new Error("Popup blocked. Allow popups and try again.");
      }

      const handleMessage = (event: MessageEvent) => {
        if (!zohoApiOriginMatches(event.origin) && event.origin !== window.location.origin) {
          return;
        }
        if (!event.data || event.data.type !== ZOHO_OAUTH_MESSAGE) {
          return;
        }

        window.removeEventListener("message", handleMessage);

        if (event.data.error) {
          setMessage(`Zoho OAuth failed: ${event.data.error}`);
          setZohoBusy(false);
          return;
        }

        setFormState((current) => ({
          ...current,
          config: {
            ...current.config,
            access_token: event.data.access_token ?? "",
            refresh_token: event.data.refresh_token ?? "",
            base_url: event.data.api_domain ?? "",
            zoho_accounts_host: event.data.zoho_accounts_host ?? current.config.zoho_accounts_host
          }
        }));
        setMessage("Zoho connected. Tokens saved in the form — use Test connection, then Save source.");
        setZohoBusy(false);
      };

      window.addEventListener("message", handleMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Zoho OAuth failed");
      setZohoBusy(false);
    }
  }

  async function handleHubSpotOAuth() {
    if (!selectedSourceMeta || selectedSourceMeta.key !== "hubspot") {
      return;
    }

    const clientId = formState.config.client_id?.trim();
    const clientSecret = formState.config.client_secret?.trim();
    const redirectUri =
      formState.config.redirect_uri?.trim() ||
      `${window.location.origin}/integrations/hubspot/callback`;

    if (!clientId || !clientSecret) {
      setMessage("HubSpot OAuth requires both client ID and client secret.");
      return;
    }

    setHubspotBusy(true);
    setMessage("");

    try {
      updateConfig("redirect_uri", redirectUri);
      const response = await fetch(`${API_URL}/api/oauth/hubspot/authorize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          redirect_uri: redirectUri,
          scope: HUBSPOT_SCOPE,
          optional_scope: HUBSPOT_OPTIONAL_SCOPE
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? "Failed to start HubSpot OAuth");
      }

      const popup = window.open(data.authorize_url, "hubspot-oauth", "width=760,height=820");
      if (!popup) {
        throw new Error("Popup blocked. Allow popups and try again.");
      }

      const handleMessage = async (event: MessageEvent) => {
        if (event.origin !== window.location.origin) {
          return;
        }

        if (!event.data || event.data.type !== HUBSPOT_OAUTH_MESSAGE) {
          return;
        }

        window.removeEventListener("message", handleMessage);

        if (event.data.error) {
          setMessage(`HubSpot OAuth failed: ${event.data.error}`);
          setHubspotBusy(false);
          return;
        }

        try {
          const exchangeResponse = await fetch(`${API_URL}/api/oauth/hubspot/exchange`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              client_id: clientId,
              client_secret: clientSecret,
              redirect_uri: redirectUri,
              code: event.data.code
            })
          });
          const tokenData = await exchangeResponse.json();
          if (!exchangeResponse.ok) {
            throw new Error(tokenData.detail ?? "HubSpot token exchange failed");
          }

          setFormState((current) => ({
            ...current,
            config: {
              ...current.config,
              redirect_uri: redirectUri,
              access_token: tokenData.access_token,
              refresh_token: tokenData.refresh_token ?? ""
            }
          }));
          setMessage("HubSpot OAuth connected. You can now test and save the source.");
        } catch (error) {
          setMessage(error instanceof Error ? error.message : "HubSpot token exchange failed");
        } finally {
          setHubspotBusy(false);
        }
      };

      window.addEventListener("message", handleMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to start HubSpot OAuth");
      setHubspotBusy(false);
    }
  }

  async function handleTest() {
    try {
      setBusy("testing");
      setMessage("");
      const isHubSpot = selectedSourceMeta?.key === "hubspot";
      const endpoint = isHubSpot ? `${API_URL}/api/hubspot/preview` : `${API_URL}/api/sources/test`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getPayload(formState, selectedSourceMeta))
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? "Source test failed");
      }
      setTestResult(data);
      if (isHubSpot) {
        const objectName = (formState.config.object_name === "companies" ? "companies" : "contacts") as
          | "contacts"
          | "companies";
        applyHubSpotPreview(objectName, data as HubSpotPreviewResponse);
      }

      const testPayload = data as SourceTestResult;
      const isCrm = selectedSourceMeta?.category === "crm";
      const rows = testPayload.preview_rows ?? [];
      if (!isHubSpot && workspaceSessionId && isCrm && rows.length > 0 && selectedSourceMeta) {
        const ingestRes = await fetch(`${API_URL}/api/workspace-memory/connector-preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: workspaceSessionId,
            connector_key: selectedSourceMeta.key,
            contacts: rows,
            companies: [],
            records: []
          })
        });
        const mem = await ingestRes.json();
        if (!ingestRes.ok) {
          setMessage(
            `Connection test succeeded, but workspace preview ingest failed: ${(mem as { detail?: string }).detail ?? ingestRes.statusText}. Talk to AI may not see this connector until ingest works.`
          );
        } else {
          onWorkspaceMemoryUpdated?.(mem);
          setMessage("Connection test succeeded. Preview rows saved for Talk to AI (workspace memory).");
        }
      } else {
        setMessage("Connection test succeeded.");
      }
    } catch (error) {
      setTestResult(null);
      setMessage(error instanceof Error ? error.message : "Connection test failed");
    } finally {
      setBusy("idle");
    }
  }

  async function handleHubSpotBrowse(
    objectName: "contacts" | "companies",
    direction: "initial" | "next" | "previous" = "initial"
  ) {
    try {
      setHubspotBrowseBusy(objectName);
      setMessage("");

      if (direction === "initial") {
        const previewResponse = await fetch(`${API_URL}/api/hubspot/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(getHubSpotSourcePayload(objectName))
        });
        const previewData = await previewResponse.json();
        if (!previewResponse.ok) {
          throw new Error(previewData.detail ?? `Failed to load HubSpot ${objectName}`);
        }
        applyHubSpotPreview(objectName, previewData as HubSpotPreviewResponse);
        setHubspotPrev((prev) => ({
          ...prev,
          [objectName]: []
        }));
        setMessage(`Loaded ${objectName}.`);
        return;
      }

      const current = objectName === "contacts" ? hubspotContacts : hubspotCompanies;
      let after: string | null = null;

      if (direction === "next") {
        after = current?.next_after ?? null;
      } else if (direction === "previous") {
        const history = objectName === "contacts" ? hubspotPrev.contacts : hubspotPrev.companies;
        after = history.length > 0 ? history[history.length - 1] || null : null;
      }

      const response = await fetch(`${API_URL}/api/hubspot/browse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getHubSpotBrowsePayload(objectName, after))
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? `Failed to browse HubSpot ${objectName}`);
      }

      if (direction === "next" && current?.next_after) {
        setHubspotPrev((prev) => ({
          ...prev,
          [objectName]: [...prev[objectName], current.current_after ?? ""]
        }));
      }

      if (direction === "previous") {
        setHubspotPrev((prev) => ({
          ...prev,
          [objectName]: prev[objectName].slice(0, -1)
        }));
      }

      if (direction === "initial") {
        setHubspotPrev((prev) => ({
          ...prev,
          [objectName]: []
        }));
      }

      if (objectName === "contacts") {
        setHubspotContacts(data);
        onHubSpotDataChanged?.({
          contacts: data.records,
          companies: hubspotCompanies?.records ?? []
        });
      } else {
        setHubspotCompanies(data);
        onHubSpotDataChanged?.({
          contacts: hubspotContacts?.records ?? [],
          companies: data.records
        });
      }
      setMessage(`Loaded ${objectName}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Failed to browse HubSpot ${objectName}`);
    } finally {
      setHubspotBrowseBusy("");
    }
  }

  async function handleSave() {
    try {
      setBusy("saving");
      setMessage("");
      const response = await fetch(`${API_URL}/api/sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getPayload(formState, selectedSourceMeta))
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? "Saving source failed");
      }
      setSources((current) => {
        const next = [data, ...current];
        onSourcesChanged?.(next);
        return next;
      });
      setMessage("Source saved. You can sync it from the table below.");
      setTestResult(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Saving source failed");
    } finally {
      setBusy("idle");
    }
  }

  async function handleSync(sourceId: string) {
    setMessage("");
    const response = await fetch(`${API_URL}/api/sources/${sourceId}/sync`, {
      method: "POST"
    });
    const data = await response.json();
    if (!response.ok) {
      setMessage(data.detail ?? "Sync failed");
      return;
    }

    setSources((current) => {
      const next = current.map((source) =>
        source.id === sourceId
          ? {
              ...source,
              last_synced_at: new Date().toISOString()
            }
          : source
      );
      onSourcesChanged?.(next);
      return next;
    });
    setMessage(`Synced ${data.imported} records from ${data.source_name}.`);
  }

  return (
    <div className="grid">
      <section className="card">
        <h2>Connect Data Sources</h2>
        <p className="muted">
          Create connectors for mainstream CRMs, enterprise sales suites, databases, and files directly from the
          website. The backend stores the connection config and normalizes incoming records into one lead schema.
        </p>
      </section>

      {!hasProviders && (
        <section className="card warning">
          <strong>No provider catalog loaded</strong>
          <p className="muted">
            The backend provider list is unavailable right now, so connector setup is disabled. Start the API to test, save, and sync sources from the frontend.
          </p>
        </section>
      )}

      {hasProviders && (
      <section className="card">
        <h2>Backend / MCP Accessible Catalog</h2>
        <p className="muted">
          This catalog is rendered from the backend provider list, so any CRM/ERP systems exposed there can appear in
          the frontend dropdown and management workflow.
        </p>
        <div className="provider-groups">
          {Object.entries(groupedProviders).map(([category, items]) => (
            <div key={category} className="provider-group">
              <strong>{category.toUpperCase()}</strong>
              <div className="provider-chip-list">
                {items.map((item) => (
                  <span key={item.key} className="provider-chip">
                    {item.label}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
      )}

      <section className="card">
        <div className="form">
          <label>
            Source Type
            <select
              value={sourceType}
              disabled={!hasProviders}
              onChange={(event) => {
                const nextType = event.target.value;
                const provider = providers.find((item) => item.key === nextType);
                setSourceType(nextType);
                if (provider) {
                  setFormState(getDefaultState(provider));
                }
                setTestResult(null);
                setMessage("");
              }}
            >
              {providers.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <p className="muted">
            {selectedSourceMeta?.description} Category: <strong>{selectedSourceMeta?.category}</strong>
          </p>

          <label>
            Source Name
            <input
              value={formState.name}
              disabled={!hasProviders}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
              placeholder="friendly connector name"
            />
          </label>

          {selectedSourceMeta?.key === "zoho" && (
            <div className="card oauth-card">
              <strong>Zoho CRM OAuth</strong>
              <p className="muted">
                Use a <strong>Server-based</strong> client in Zoho API Console. Register the redirect URI below on the
                backend (same URL as &quot;Authorized Redirect URI&quot; in this form — typically{" "}
                <code>{`${API_URL.replace(/\/$/, "")}/api/oauth/zoho/callback`}</code>
                ).
              </p>
              <button
                className="button"
                type="button"
                disabled={!hasProviders || zohoBusy}
                onClick={handleZohoOAuth}
              >
                {zohoBusy ? "Authorizing..." : "Connect Zoho CRM"}
              </button>
              <p className="muted" style={{ marginTop: "12px" }}>
                <strong>Zoho only (not HubSpot):</strong> after OAuth, click <strong>Test connection</strong> — that writes
                preview rows into workspace memory so <strong>Talk to AI</strong> can use them. Then <strong>Save source</strong>{" "}
                (needs Postgres). EU: set <strong>Zoho accounts host</strong> to <code>accounts.zoho.eu</code> when possible.
                HubSpot&apos;s &quot;Load contacts / companies&quot; buttons only show for <strong>HubSpot</strong>.
              </p>
            </div>
          )}

          {selectedSourceMeta?.key === "hubspot" && (
            <div className="card oauth-card">
              <strong>HubSpot OAuth</strong>
              <p className="muted">
                Enter your HubSpot client ID and client secret, then authorize the app. The returned access and refresh
                tokens will be stored in this source config for future syncs.
              </p>
              <p className="muted">
                Optional HubSpot scopes for AI-driven campaigns and automations are requested during OAuth so the chat
                panel can plan around lists, campaigns, workflows, sequences, and subscription preferences when the
                HubSpot account tier allows them.
              </p>
              <button
                className="button"
                type="button"
                disabled={!hasProviders || hubspotBusy}
                onClick={handleHubSpotOAuth}
              >
                {hubspotBusy ? "Authorizing..." : "Connect HubSpot OAuth"}
              </button>
            </div>
          )}

          {selectedSourceMeta?.fields.map((field) => (
            <label key={field.key}>
              {field.label}
              {field.kind === "textarea" || field.kind === "json" ? (
                <textarea
                  rows={field.kind === "json" ? 4 : 5}
                  value={formState.config[field.key] ?? ""}
                  disabled={!hasProviders}
                  onChange={(event) => updateConfig(field.key, event.target.value)}
                  placeholder={field.placeholder ?? ""}
                />
              ) : (
                <input
                  type={field.secret ? "password" : "text"}
                  value={formState.config[field.key] ?? ""}
                  disabled={!hasProviders}
                  onChange={(event) => updateConfig(field.key, event.target.value)}
                  placeholder={field.placeholder ?? ""}
                />
              )}
              {field.help_text && <div className="muted">{field.help_text}</div>}
            </label>
          ))}

          <div className="actions">
            <button className="button" type="button" disabled={!hasProviders || busy !== "idle"} onClick={handleTest}>
              {busy === "testing" ? "Testing..." : "Test connection"}
            </button>
            <button className="button" type="button" disabled={!hasProviders || busy !== "idle"} onClick={handleSave}>
              {busy === "saving" ? "Saving..." : "Save source"}
            </button>
            {selectedSourceMeta?.key === "hubspot" && (
              <>
                <button
                  className="button"
                  type="button"
                  disabled={!hasProviders || hubspotBrowseBusy !== ""}
                  onClick={() => handleHubSpotBrowse("contacts", "initial")}
                >
                  {hubspotBrowseBusy === "contacts" ? "Loading contacts..." : "Load contacts"}
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={!hasProviders || hubspotBrowseBusy !== ""}
                  onClick={() => handleHubSpotBrowse("companies", "initial")}
                >
                  {hubspotBrowseBusy === "companies" ? "Loading companies..." : "Load companies"}
                </button>
              </>
            )}
          </div>

          {message && <div className="status">{message}</div>}

          {testResult && (
            <div className="card">
              <h3>Test Result</h3>
              <p className="muted">Sample rows returned: {testResult.sample_count}</p>
              <p className="muted">Detected fields: {testResult.sample_fields.join(", ") || "none"}</p>
              <p className="muted">Normalized fields: {testResult.normalized_fields.join(", ")}</p>
            </div>
          )}
        </div>
      </section>

      {selectedSourceMeta?.key === "hubspot" && (
        <section className="card">
          <h2>HubSpot Data Preview</h2>
          <div className="grid two">
            <div className="card">
              <div className="table-header">
                <h3>Contacts</h3>
                <div className="actions">
                  <button
                    className="button"
                    type="button"
                    disabled={hubspotBrowseBusy !== "" || hubspotPrev.contacts.length === 0}
                    onClick={() => handleHubSpotBrowse("contacts", "previous")}
                  >
                    Previous
                  </button>
                  <button
                    className="button"
                    type="button"
                    disabled={hubspotBrowseBusy !== "" || !hubspotContacts?.next_after}
                    onClick={() => handleHubSpotBrowse("contacts", "next")}
                  >
                    Next
                  </button>
                </div>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Company</th>
                    <th>Title</th>
                  </tr>
                </thead>
                <tbody>
                  {(hubspotContacts?.records ?? []).length === 0 && (
                    <tr>
                      <td colSpan={4}>No contacts loaded yet.</td>
                    </tr>
                  )}
                  {(hubspotContacts?.records ?? []).map((record, index) => (
                    <tr key={`${record.id ?? "contact"}-${index}`}>
                      <td>{`${record.firstname ?? ""} ${record.lastname ?? ""}`.trim() || record.name || "-"}</td>
                      <td>{record.email ?? "-"}</td>
                      <td>{record.company ?? "-"}</td>
                      <td>{record.jobtitle ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <div className="table-header">
                <h3>Companies</h3>
                <div className="actions">
                  <button
                    className="button"
                    type="button"
                    disabled={hubspotBrowseBusy !== "" || hubspotPrev.companies.length === 0}
                    onClick={() => handleHubSpotBrowse("companies", "previous")}
                  >
                    Previous
                  </button>
                  <button
                    className="button"
                    type="button"
                    disabled={hubspotBrowseBusy !== "" || !hubspotCompanies?.next_after}
                    onClick={() => handleHubSpotBrowse("companies", "next")}
                  >
                    Next
                  </button>
                </div>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Domain</th>
                    <th>Industry</th>
                    <th>Country</th>
                  </tr>
                </thead>
                <tbody>
                  {(hubspotCompanies?.records ?? []).length === 0 && (
                    <tr>
                      <td colSpan={4}>No companies loaded yet.</td>
                    </tr>
                  )}
                  {(hubspotCompanies?.records ?? []).map((record, index) => (
                    <tr key={`${record.id ?? "company"}-${index}`}>
                      <td>{record.name ?? "-"}</td>
                      <td>{record.domain ?? "-"}</td>
                      <td>{record.industry ?? "-"}</td>
                      <td>{record.country ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      <section className="card">
        <h2>Registered Connectors</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Connection</th>
              <th>Last Sync</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {sources.length === 0 && (
              <tr>
                <td colSpan={5}>No sources connected yet.</td>
              </tr>
            )}
            {sources.map((source) => (
              <tr key={source.id}>
                <td>{source.name}</td>
                <td>{source.source_type}</td>
                <td>{source.config.connection_url ?? source.config.file_path ?? "configured"}</td>
                <td>{source.last_synced_at ? new Date(source.last_synced_at).toLocaleString() : "Never"}</td>
                <td>
                  <button className="button" type="button" onClick={() => handleSync(source.id)}>
                    Sync now
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
