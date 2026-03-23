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


def _recommended_action(overall_score: float) -> str:
    if overall_score >= 80:
        return "book_demo"
    if overall_score >= 60:
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
    action = _recommended_action(overall_score)
    explanation = generate_lead_explanation(lead, breakdown, overall_score, action)
    return ScoreResult(
        breakdown=breakdown,
        overall_score=overall_score,
        recommended_action=action,
        explanation=explanation,
    )
