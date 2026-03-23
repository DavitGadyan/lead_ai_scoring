type LeadRow = {
  lead_id: string;
  company: string | null;
  email: string | null;
  source_name: string;
  overall_score: number;
  recommended_action: string;
  explanation: string;
  created_at: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getLeads(): Promise<LeadRow[]> {
  const response = await fetch(`${API_URL}/api/leads`, { cache: "no-store" });
  if (!response.ok) {
    return [];
  }
  return response.json();
}

export default async function LeadsPage() {
  const leads = await getLeads();

  return (
    <div className="grid">
      <section className="card">
        <h1 className="title">Recent Scored Leads</h1>
        <p className="muted">
          These records come from the normalized relational tables after imports from Excel, Postgres, or direct API submissions.
        </p>
      </section>

      <section className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Score</th>
              <th>Action</th>
              <th>Source</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {leads.length === 0 && (
              <tr>
                <td colSpan={5}>No leads scored yet.</td>
              </tr>
            )}
            {leads.map((lead) => (
              <tr key={lead.lead_id}>
                <td>{lead.company ?? lead.email ?? "Unknown"}</td>
                <td>{lead.overall_score}</td>
                <td>{lead.recommended_action}</td>
                <td>{lead.source_name}</td>
                <td>{lead.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
