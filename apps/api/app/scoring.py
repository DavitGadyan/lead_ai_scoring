from dataclasses import dataclass

from .llm import generate_lead_explanation
from .schemas import LeadCanonical, ScoreBreakdown

WEIGHTS = {
    "fit_score": 0.35,
    "intent_score": 0.25,
    "urgency_score": 0.15,
    "budget_score": 0.15,
    "authority_score": 0.10,
}


@dataclass
class ScoreResult:
    breakdown: ScoreBreakdown
    overall_score: float
    directional_score: float
    recommended_action: str
    explanation: str


def _bounded(score: int) -> int:
    return max(0, min(100, score))


def _fit_score(lead: LeadCanonical) -> int:
    score = 40
    if lead.industry and lead.industry.lower() in {"saas", "healthcare", "fintech", "logistics"}:
        score += 20
    if lead.employee_count and 50 <= lead.employee_count <= 1000:
        score += 20
    if lead.country and lead.country.lower() in {"united states", "canada", "united kingdom", "germany"}:
        score += 10
    if lead.company:
        score += 10
    return _bounded(score)


def _intent_score(lead: LeadCanonical) -> int:
    notes = (lead.notes or "").lower()
    score = 25
    keywords = {
        "demo": 20,
        "pricing": 20,
        "automation": 15,
        "proposal": 15,
        "timeline": 10,
        "pilot": 10,
        "implementation": 15,
    }
    for keyword, value in keywords.items():
        if keyword in notes:
            score += value
    return _bounded(score)


def _urgency_score(lead: LeadCanonical) -> int:
    notes = (lead.notes or "").lower()
    score = 20
    urgency_terms = {
        "this month": 35,
        "30 days": 35,
        "60 days": 25,
        "quarter": 15,
        "urgent": 30,
        "asap": 35,
    }
    for term, value in urgency_terms.items():
        if term in notes:
            score += value
    return _bounded(score)


def _budget_score(lead: LeadCanonical) -> int:
    budget = (lead.budget_range or "").lower()
    score = 20
    if "100k" in budget or "enterprise" in budget:
        score += 60
    elif "50k" in budget:
        score += 45
    elif "25k" in budget:
        score += 35
    elif "10k" in budget:
        score += 20
    elif budget:
        score += 10
    return _bounded(score)


def _authority_score(lead: LeadCanonical) -> int:
    title = (lead.job_title or "").lower()
    score = 20
    leadership_terms = {
        "chief": 50,
        "cto": 50,
        "ceo": 50,
        "cmo": 45,
        "vp": 40,
        "director": 30,
        "head of": 35,
        "manager": 15,
    }
    for term, value in leadership_terms.items():
        if term in title:
            score += value
    return _bounded(score)


def _clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _normalized_probability(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 1:
        return max(0.0, min(1.0, value / 100))
    return max(0.0, min(1.0, value))


def _directional_score(lead: LeadCanonical, breakdown: ScoreBreakdown) -> float:
    notes = (lead.notes or "").lower()
    status = " ".join(part for part in [lead.lifecycle_stage or "", lead.lead_status or ""] if part).lower()

    buy_signal = 0.0
    churn_signal = 0.0

    explicit_buy = _normalized_probability(lead.conversion_likelihood)
    explicit_churn = _normalized_probability(lead.churn_risk)
    if explicit_buy is not None:
        buy_signal += 0.45 * explicit_buy
    if explicit_churn is not None:
        churn_signal += 0.55 * explicit_churn

    buy_signal += 0.12 * (breakdown.intent_score / 100)
    buy_signal += 0.08 * (breakdown.urgency_score / 100)
    buy_signal += 0.06 * (breakdown.budget_score / 100)
    buy_signal += 0.05 * (breakdown.authority_score / 100)

    if lead.engagement_score is not None:
        buy_signal += 0.12 * max(0.0, min(1.0, lead.engagement_score / 100))
    if lead.health_score is not None:
        health = max(0.0, min(1.0, lead.health_score / 100))
        buy_signal += 0.08 * health
        churn_signal += 0.14 * (1 - health)
    if lead.product_usage_score is not None:
        usage = max(0.0, min(1.0, lead.product_usage_score / 100))
        buy_signal += 0.07 * usage
        churn_signal += 0.07 * (1 - usage)
    if lead.nps_score is not None:
        if lead.nps_score >= 30:
            buy_signal += 0.08
        elif lead.nps_score <= 0:
            churn_signal += 0.12
    if lead.support_ticket_count is not None:
        if lead.support_ticket_count >= 4:
            churn_signal += 0.12
        elif lead.support_ticket_count == 0:
            buy_signal += 0.03
    if lead.days_since_last_activity is not None:
        if lead.days_since_last_activity <= 7:
            buy_signal += 0.08
        elif lead.days_since_last_activity >= 30:
            churn_signal += 0.14

    positive_terms = ("demo", "proposal", "pilot", "pricing", "expansion", "upgrade", "automation", "implementation")
    negative_terms = ("cancel", "churn", "at risk", "friction", "stale", "complained", "unhappy", "downgrade")
    if any(term in notes for term in positive_terms):
        buy_signal += 0.12
    if any(term in notes for term in negative_terms):
        churn_signal += 0.18

    if any(term in status for term in ("customer", "qualified", "proposal", "sales_qualified", "opportunity", "demo")):
        buy_signal += 0.08
    if any(term in status for term in ("at_risk", "at risk", "churn", "inactive", "lost", "stalled")):
        churn_signal += 0.16

    return round(_clamp_unit(buy_signal - churn_signal), 2)


def _recommended_action(overall_score: float, directional_score: float) -> str:
    if directional_score <= -0.45:
        return "retention_intervention"
    if directional_score <= -0.2:
        return "customer_health_review"
    if directional_score >= 0.7 or overall_score >= 80:
        return "book_demo"
    if directional_score >= 0.4 or overall_score >= 60:
        return "sales_followup"
    if overall_score >= 40:
        return "nurture_sequence"
    return "low_priority"


def score_lead(lead: LeadCanonical) -> ScoreResult:
    breakdown = ScoreBreakdown(
        fit_score=_fit_score(lead),
        intent_score=_intent_score(lead),
        urgency_score=_urgency_score(lead),
        budget_score=_budget_score(lead),
        authority_score=_authority_score(lead),
    )
    overall_score = round(
        sum(getattr(breakdown, key) * weight for key, weight in WEIGHTS.items()),
        2,
    )
    directional_score = _directional_score(lead, breakdown)
    action = _recommended_action(overall_score, directional_score)
    explanation = generate_lead_explanation(lead, breakdown, overall_score, directional_score, action)
    return ScoreResult(
        breakdown=breakdown,
        overall_score=overall_score,
        directional_score=directional_score,
        recommended_action=action,
        explanation=explanation,
    )
