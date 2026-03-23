import { SourceManager } from "../../components/source-manager";

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

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getSources(): Promise<SourceRecord[] | null> {
  try {
    const response = await fetch(`${API_URL}/api/sources`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    return response.json();
  } catch {
    return null;
  }
}

async function getProviders(): Promise<ProviderDefinition[] | null> {
  try {
    const response = await fetch(`${API_URL}/api/providers`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    return response.json();
  } catch {
    return null;
  }
}

export default async function SourcesPage() {
  const [sourcesResult, providersResult] = await Promise.all([getSources(), getProviders()]);
  const backendAvailable = sourcesResult !== null && providersResult !== null;
  const sources = sourcesResult ?? [];
  const providers = providersResult ?? [];

  return (
    <div className="grid">
      <section className="card">
        <h1 className="title">Source Connections</h1>
        <p className="muted">
          Manage live connections to CRM platforms, enterprise sales suites, databases, and files directly from the website.
        </p>
      </section>

      {!backendAvailable && (
        <section className="card warning">
          <strong>Backend unavailable</strong>
          <p className="muted">
            The frontend loaded, but the API at <code>{API_URL}</code> could not be reached. Start the backend to load providers and sync connectors.
          </p>
        </section>
      )}

      <SourceManager initialSources={sources} providers={providers} />
    </div>
  );
}
