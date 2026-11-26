"""Agent 1: sort overnight leads into hot, warm, cold, not a fit, or spam."""
from __future__ import annotations

from .common import detect_service

SPAM = ("rank #1", "click here", "seo", "guaranteed traffic", "backlinks", "crypto")
NOT_A_FIT = ("plumbing", "plumber", "hvac", "electrician")
HOT = ("leak", "dripping", "hail", "storm damage", "water stain", "emergency")
ACTIVE_WATER = ("leak", "dripping")
COLD = ("just browsing", "next year", "someday", "maybe later")
WARM = ("quote", "price", "pricing", "how much", "estimate", "inspection", "replace", "gutter", "roof")

TOPICS = {
    "gutter_guards": "Gutter guards",
    "gutter_cleaning": "Gutter cleaning",
    "commercial_inspection": "Commercial roof inspection",
    "roof_replacement": "Roof replacement estimate",
}


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def classify_lead(lead: dict) -> dict:
    """Return the lead with category, the signals that decided it, and a service guess."""
    text = f"{lead.get('name') or ''} {lead['message']}".lower()
    service = detect_service(lead["message"])
    urgency = 2 if _hits(text, ACTIVE_WATER) else 1

    if (hits := _hits(text, SPAM)):
        category = "spam"
    elif (hits := _hits(text, NOT_A_FIT)) and service is None:
        category = "not_a_fit"
    elif (hits := _hits(text, HOT)):
        category = "hot"
    elif (hits := _hits(text, COLD)):
        category = "cold"
    elif (hits := _hits(text, WARM)):
        category = "warm"
    else:
        category, hits = "cold", []

    reason = ("Matched: " + ", ".join(hits)) if hits else "No buying signal found"
    if category == "hot":
        topic = "Active roof leak" if urgency == 2 else "Storm damage inspection"
    else:
        topic = TOPICS.get(service, "General question")

    return {
        **lead,
        "category": category,
        "reason": reason,
        "service": service,
        "urgency": urgency if category == "hot" else 0,
        "topic": topic,
    }


ORDER = {"hot": 0, "warm": 1, "cold": 2, "not_a_fit": 3, "spam": 4}


def sort_leads(leads: list[dict]) -> list[dict]:
    classified = [classify_lead(lead) for lead in leads]
    return sorted(classified, key=lambda x: (ORDER[x["category"]], -x["urgency"], x["received"]))
