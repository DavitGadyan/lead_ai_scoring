import { IntelligenceWorkspace } from "../components/intelligence-workspace";

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

export default async function HomePage() {
  const [sourcesResult, providersResult] = await Promise.all([getSources(), getProviders()]);
  const backendAvailable = sourcesResult !== null && providersResult !== null;
  const sources = sourcesResult ?? [];
  const providers = providersResult ?? [];

  return (
    <IntelligenceWorkspace
      initialSources={sources}
      providers={providers}
      backendAvailable={backendAvailable}
    />
  );
}
