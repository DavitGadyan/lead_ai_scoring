from app.schemas import LeadCanonical
from app.scoring import score_lead


def test_score_lead_returns_expected_action() -> None:
    lead = LeadCanonical(
        full_name="Jane Doe",
        email="jane@example.com",
        company="Acme Health",
        job_title="VP Operations",
        industry="Healthcare",
        country="United States",
        employee_count=300,
        budget_range="25k-50k",
        notes="Need automation in 60 days and want a demo with pricing.",
    )

    result = score_lead(lead)

    assert result.overall_score >= 60
    assert result.recommended_action in {"book_demo", "sales_followup"}
    assert result.breakdown.fit_score >= 70
