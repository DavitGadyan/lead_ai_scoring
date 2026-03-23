const pipelineSteps = [
  "Register an automated source such as SQL, NoSQL, Excel, or CSV.",
  "Pull source records on demand or from a scheduler like n8n or CronJob.",
  "Normalize each record into one canonical lead shape.",
  "Score with deterministic Python logic and optional LLM explanation.",
  "Persist scores for dashboards, automations, and downstream CRM sync."
];

export default function AdminPage() {
  return (
    <div className="grid">
      <section className="card">
        <h1 className="title">Admin Overview</h1>
        <p className="muted">
          This starter admin view explains the operating model so you can expand it into scoring profile management, prompt tuning, and team-specific routing rules.
        </p>
      </section>

      <section className="grid two">
        <div className="card">
          <h2>Core Inputs</h2>
          <ul>
            <li>SQL sources such as Postgres, MySQL, or SQLite through connection URL plus query</li>
            <li>NoSQL sources such as MongoDB collections with optional filters</li>
            <li>Excel and CSV files for offline imports and scheduled file drops</li>
          </ul>
        </div>

        <div className="card">
          <h2>Deployment Modes</h2>
          <ul>
            <li>`n8n + FastAPI` for lower-scale automation and fast iteration</li>
            <li>`Docker + Kubernetes` for worker queues and higher concurrency</li>
            <li>`Terraform + GitHub Actions` for reproducible infrastructure and deployment</li>
          </ul>
        </div>
      </section>

      <section className="card">
        <h2>Scoring Pipeline</h2>
        <ol>
          {pipelineSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      <section className="card">
        <h2>Website Connection Management</h2>
        <p className="muted">
          Use the new <strong>Sources</strong> page to create connectors for Postgres, Supabase, MySQL, MongoDB,
          Excel, and CSV directly from the website, test them, and trigger syncs without editing backend code.
        </p>
      </section>
    </div>
  );
}
