"use client";

import { FormEvent, useState } from "react";

type LeadResponse = {
  lead_id: string;
  overall_score: number;
  recommended_action: string;
  explanation: string;
  breakdown: {
    fit_score: number;
    intent_score: number;
    urgency_score: number;
    budget_score: number;
    authority_score: number;
  };
};

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function LeadForm() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LeadResponse | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setResult(null);

    const formData = new FormData(event.currentTarget);
    const getValue = (name: string) => String(formData.get(name) ?? "");

    const payload = {
      full_name: getValue("full_name"),
      email: getValue("email"),
      company: getValue("company"),
      job_title: getValue("job_title"),
      industry: getValue("industry"),
      country: getValue("country"),
      employee_count: Number(getValue("employee_count")),
      budget_range: getValue("budget_range"),
      notes: getValue("notes"),
      source_type: "manual",
      source_name: "web_form"
    };

    const response = await fetch(`${API_URL}/api/score/lead`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    setResult(data);
    setLoading(false);
  }

  return (
    <div className="grid two">
      <section className="card">
        <h2>Score a Lead</h2>
        <p className="muted">
          This form hits the shared FastAPI scoring core used by both the n8n MVP and the Kubernetes scale path.
        </p>
        <form className="form" onSubmit={onSubmit}>
          <input name="full_name" placeholder="Full name" defaultValue="Jane Doe" />
          <input name="email" placeholder="Email" defaultValue="jane@acmehealth.com" />
          <input name="company" placeholder="Company" defaultValue="Acme Health" />
          <input name="job_title" placeholder="Job title" defaultValue="VP Operations" />
          <input name="industry" placeholder="Industry" defaultValue="Healthcare" />
          <input name="country" placeholder="Country" defaultValue="United States" />
          <input name="employee_count" type="number" placeholder="Employees" defaultValue="320" />
          <input name="budget_range" placeholder="Budget" defaultValue="25k-50k" />
          <textarea
            name="notes"
            rows={4}
            defaultValue="We need lead qualification automation within 60 days and want a demo with pricing."
          />
          <button className="button" type="submit" disabled={loading}>
            {loading ? "Scoring..." : "Score lead"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Result</h2>
        {!result && <p className="muted">Submit a lead to see the deterministic score breakdown.</p>}
        {result && (
          <div className="grid">
            <div>
              <span className="tag">{result.recommended_action}</span>
            </div>
            <div>
              <strong>Overall score:</strong> {result.overall_score}
            </div>
            <div>
              <strong>Explanation:</strong> {result.explanation}
            </div>
            <div className="grid two">
              <div className="card">
                <strong>Fit</strong>
                <div>{result.breakdown.fit_score}</div>
              </div>
              <div className="card">
                <strong>Intent</strong>
                <div>{result.breakdown.intent_score}</div>
              </div>
              <div className="card">
                <strong>Urgency</strong>
                <div>{result.breakdown.urgency_score}</div>
              </div>
              <div className="card">
                <strong>Budget</strong>
                <div>{result.breakdown.budget_score}</div>
              </div>
              <div className="card">
                <strong>Authority</strong>
                <div>{result.breakdown.authority_score}</div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
