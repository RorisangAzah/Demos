"""The reviewer: independent checks that run on every agent output before a human sees it.

It never reads the agents' caches or templates. It checks the output against the
business's own source of truth (data/business.json) and against the input record.
Each finding says what is wrong, shows the exact text, and offers a fix when one is safe.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .common import DAYS, fmt_money, format_slot, is_open, money_amounts

PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]+\}|\{\{[^}]+\}\}|\[(?:first )?name\]", re.IGNORECASE)
GREETING_RE = re.compile(r"^(?:Hi|Hello|Hey) ([A-Z][a-z]+),")

SECRET_PATTERNS = [
    ("API key", re.compile(r"sk-[A-Za-z0-9_\-]{16,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Password or token", re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret|token)\b\s*[:=]\s*[^\s'\"]{6,}")),
]

LESSONS = {
    "price_mismatch": "Read prices from data/business.json every time you write one. Never reuse a remembered or cached price.",
    "placeholder": "If a lead has no personal name, greet the company or use a neutral hello. Never send a draft with a template field left in it.",
    "closed_day": "Check every proposed visit against business hours before writing it. If a customer says 'weekend', offer Saturday morning.",
    "banned_wording": "Do not promise outcomes or timelines the business has not approved. Offer the earliest date after an inspection instead.",
    "outdated_quote": "When a call summary shows a price that differs from the price list, flag it for the owner. Do not repeat it in a follow-up.",
    "hallucinated_amount": "Only put a dollar amount in a summary if the caller or rep said it on the call.",
    "wrong_recipient": "Greet the person on the lead record, using the same first name and the same email.",
    "secret": "Never write a key, password or token into any message, summary or file.",
}


def _finding(rule: str, severity: str, title: str, detail: str, evidence: str | None = None,
             replacement: str | None = None, **extra) -> dict:
    return {"rule": rule, "severity": severity, "title": title, "detail": detail,
            "evidence": evidence, "replacement": replacement, **extra}


# ---------- individual checks ----------

def check_placeholders(draft: dict, lead: dict) -> list[dict]:
    findings = []
    first_line = draft["body"].split("\n", 1)[0]
    for match in PLACEHOLDER_RE.finditer(draft["body"]):
        in_greeting = match.group(0) in first_line
        replacement = None
        if in_greeting:
            replacement = f"Hello {lead['company']} team," if lead.get("company") else "Hi there,"
        findings.append(_finding(
            "placeholder", "block", "Template field left in the message",
            f"The text {match.group(0)} would reach the customer exactly as written.",
            evidence=first_line if in_greeting else match.group(0), replacement=replacement))
        break
    return findings


def check_prices(draft: dict, business: dict) -> list[dict]:
    prices = business["prices"]
    amounts = money_amounts(draft["body"])
    expected = {s: prices[s]["amount"] for s in draft.get("services", []) if s in prices}
    if expected:
        wrong = sorted({a for a in amounts if a not in expected.values()})
    else:
        wrong = sorted({a for a in amounts if a not in {p["amount"] for p in prices.values()}})
    if not wrong:
        return []
    if len(expected) == 1 and len(wrong) == 1:
        service, current = next(iter(expected.items()))
        return [_finding(
            "price_mismatch", "block", "Wrong price",
            f"The draft quotes {fmt_money(wrong[0])} for {prices[service]['short']}. "
            f"The current price list says {fmt_money(current)}.",
            evidence=fmt_money(wrong[0]), replacement=fmt_money(current))]
    return [_finding(
        "price_mismatch", "block", "Price not on the price list",
        f"The draft quotes {', '.join(fmt_money(a) for a in wrong)}, which does not match the price list.",
        evidence=fmt_money(wrong[0]))]


def nearest_open_slot(slot: datetime, business: dict, not_before: date) -> datetime:
    """Same time of day, closest open day: the day before first, then the day after."""
    for step in range(1, 15):
        for sign in (-1, 1):
            candidate = slot + timedelta(days=sign * step)
            if candidate.date() >= not_before and is_open(candidate, business)[0]:
                return candidate
    return slot


def check_slot(draft: dict, business: dict, today: date) -> list[dict]:
    slot = datetime.fromisoformat(draft["slot"])
    ok, reason = is_open(slot, business)
    if ok:
        return []
    better = nearest_open_slot(slot, business, today)
    new_label = format_slot(better, today)
    return [_finding(
        "closed_day", "block", "Visit offered when the business is closed", reason,
        evidence=draft["slot_label"], replacement=new_label, new_slot=better.isoformat(timespec="minutes"))]


def check_wording(draft: dict, business: dict) -> list[dict]:
    body = draft["body"]
    lower = body.lower()
    for key, safe in business["safe_rewrites"].items():
        index = lower.find(key.lower())
        if index >= 0:
            return [_finding(
                "banned_wording", "block", "Promise the business has not approved",
                "The draft promises same-day repair. We can offer the earliest date after an inspection, not a guarantee.",
                evidence=body[index:index + len(key)], replacement=safe)]
    for phrase in business["banned_phrases"]:
        index = lower.find(phrase.lower())
        if index >= 0:
            return [_finding(
                "banned_wording", "block", "Wording the business does not use",
                f"The draft uses \"{phrase}\". Rewrite the sentence by hand.",
                evidence=body[index:index + len(phrase)])]
    return []


def check_recipient(draft: dict, lead: dict) -> list[dict]:
    findings = []
    if draft["to"].lower() != lead["email"].lower():
        findings.append(_finding(
            "wrong_recipient", "block", "Sent to a different address than the lead",
            f"The lead's email is {lead['email']} but the draft is addressed to {draft['to']}.",
            evidence=draft["to"]))
    match = GREETING_RE.match(draft["body"])
    if match and lead.get("name"):
        if match.group(1).lower() != lead["name"].split(" ")[0].lower():
            findings.append(_finding(
                "wrong_recipient", "block", "Greeting names someone else",
                f"The greeting says {match.group(1)} but the lead is {lead['name']}.",
                evidence=match.group(0), replacement=f"Hi {lead['name'].split(' ')[0]},"))
    return findings


def check_secrets(text: str) -> list[dict]:
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            return [_finding(
                "secret", "block", "Credential in the output",
                f"Looks like a {label.lower()}. Remove it, rotate it if it was real, and tell the owner.",
                evidence=match.group(0))]
    return []


# ---------- reviewing whole outputs ----------

def review_draft(draft: dict, lead: dict, business: dict, today: date) -> list[dict]:
    return (
        check_placeholders(draft, lead)
        + check_prices(draft, business)
        + check_slot(draft, business, today)
        + check_wording(draft, business)
        + check_recipient(draft, lead)
        + check_secrets(draft["subject"] + "\n" + draft["body"])
    )


def review_call_summary(summary: dict, call: dict, business: dict) -> list[dict]:
    findings = []
    spoken = set(money_amounts(" ".join(t["text"] for t in call["transcript"])))
    for amount in money_amounts(summary["text"]):
        if amount not in spoken:
            findings.append(_finding(
                "hallucinated_amount", "block", "Amount that was never said",
                f"The summary mentions {fmt_money(amount)} but nobody said it on the call.",
                evidence=fmt_money(amount)))
    for quote in summary["quotes"]:
        price = business["prices"].get(quote["service"])
        if price and price["amount"] != quote["amount"]:
            short = price["short"]
            findings.append(_finding(
                "outdated_quote", "warn", "Customer was quoted an old price",
                f"The rep quoted {short} at {fmt_money(quote['amount'])} on the call. "
                f"The price list now says {fmt_money(price['amount'])}. "
                f"The summary is accurate, but the customer expects the lower number.",
                evidence=fmt_money(quote["amount"]),
                contact=call["contact"], quoted=quote["amount"], current=price["amount"], service_short=short,
                options=[f"Honor {fmt_money(quote['amount'])} for this customer",
                         f"Call to explain the new {fmt_money(price['amount'])} price"]))
    findings += check_secrets(summary["text"])
    return findings


# ---------- fixes and status ----------

def status_for(findings: list[dict]) -> str:
    if not findings:
        return "clean"
    if all(f.get("replacement") for f in findings):
        return "fix_ready"
    return "needs_decision"


def apply_fixes(draft: dict, findings: list[dict]) -> dict:
    """Return a corrected copy of the draft. Only findings with a safe replacement are applied."""
    fixed = dict(draft)
    for finding in findings:
        if finding.get("replacement") and finding.get("evidence") and finding["evidence"] in fixed["body"]:
            fixed["body"] = fixed["body"].replace(finding["evidence"], finding["replacement"], 1)
            if finding.get("new_slot"):
                fixed["slot"] = finding["new_slot"]
                fixed["slot_label"] = finding["replacement"]
    return fixed


def lessons_from(review_items: list[dict]) -> list[dict]:
    """One proposed lesson per rule that fired, with the items that triggered it."""
    seen: dict[str, list[str]] = {}
    for item in review_items:
        for finding in item["findings"]:
            seen.setdefault(finding["rule"], []).append(item["id"])
    return [{"rule": rule, "lesson": LESSONS[rule], "items": ids} for rule, ids in seen.items()]
