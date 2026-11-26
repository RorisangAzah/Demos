"""Agent 3: draft follow-up emails for hot and warm leads.

The drafting here is template-based so the demo runs offline with no API key.
In a real client build, the template step is where a Claude call would go.

Four mistakes are seeded on purpose, each one a failure that real agents make:
  1. Quoting a price from a stale cache instead of the current price list.
  2. Leaving a {first_name} placeholder when a lead has no personal name.
  3. Offering a Sunday visit when the business is closed on Sundays.
  4. Promising "same-day repair", which the business does not guarantee.
Run `python3 run_brief.py --no-seeded-faults` to see the agent without them.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .common import DAYS, fmt_money, format_slot

SAFE_PROMISE = "we'll give you the earliest repair date as soon as we've found the cause"
SEEDED_PROMISE = "we guarantee same-day repair once we've found the cause"

TEMPLATES = {
    "storm": (
        "Your roof: we can look at it today",
        "{greeting}\n\n"
        "Thanks for reaching out about the hail damage. We put storm calls first, and {promise}. "
        "I can have an inspector at your home {slot} for our {short} ({price}). "
        "The fee is credited toward any repair we do.\n\n"
        "Reply YES to confirm, or call us at {phone}.\n\n{signoff}",
    ),
    "leak": (
        "Your roof leak: we can be there today",
        "{greeting}\n\n"
        "An active leak needs eyes on it quickly. I can have an inspector at your home {slot} "
        "for our {short} ({price}). The fee is credited toward any repair we do. "
        "If water is coming in now, put a bucket under the drip and move anything valuable out of the way.\n\n"
        "Reply YES to confirm, or call us at {phone}.\n\n{signoff}",
    ),
    "gutter_guards": (
        "Your gutter guard quote",
        "{greeting}\n\n"
        "Thanks for your voicemail about gutter guards. For a home up to 2,500 sq ft, our {short} is {price}, "
        "and we can schedule it {slot}. Spring fills up fast, so booking now keeps your date.\n\n"
        "Reply with a time that works, or call us at {phone}.\n\n{signoff}",
    ),
    "commercial_inspection": (
        "Your roof inspection pricing",
        "{greeting}\n\n"
        "Thanks for your request about the roof at your office building. Our {short} is {price}. "
        "I can have an inspector there {slot} to look at the roof and write up what we find.\n\n"
        "Reply to confirm, or call us at {phone}.\n\n{signoff}",
    ),
    "gutter_cleaning": (
        "Your gutter cleaning",
        "{greeting}\n\n"
        "Thanks for asking about gutter cleaning. It's {price}, and we can do it {slot}.\n\n"
        "Reply YES to book it, or call us at {phone}.\n\n{signoff}",
    ),
    "roof_replacement": (
        "Your free roof estimate",
        "{greeting}\n\n"
        "Thanks for getting in touch, and for the referral. Estimates for full roof replacement are free. "
        "I can have an estimator at your home {slot} to measure the roof and walk you through shingle options.\n\n"
        "Reply to confirm, or call us at {phone}.\n\n{signoff}",
    ),
}


def _is_open_day(day: date, business: dict) -> bool:
    return business["hours"][DAYS[day.weekday()]] is not None


def _next_open_day(day: date, business: dict) -> date:
    while not _is_open_day(day, business):
        day += timedelta(days=1)
    return day


def plan_slots(leads: list[dict], business: dict, today: date, seeded: bool) -> dict[str, datetime]:
    """Pick a visit time for each hot or warm lead."""
    hot = sorted((x for x in leads if x["category"] == "hot"), key=lambda x: (-x["urgency"], x["received"]))
    warm = sorted((x for x in leads if x["category"] == "warm"), key=lambda x: x["received"])
    slots: dict[str, datetime] = {}

    for i, lead in enumerate(hot):
        slots[lead["id"]] = datetime.combine(today, time(13 + i))

    weekday_slots = [(1, 10), (1, 16), (2, 9), (3, 9), (4, 9)]
    taken = 0
    for lead in warm:
        if "weekend" in lead["message"].lower():
            saturday = today + timedelta(days=(5 - today.weekday()) % 7)
            # Seeded fault 3: the agent reads "weekend" as Sunday.
            day = saturday + timedelta(days=1) if seeded else saturday
            slots[lead["id"]] = datetime.combine(day, time(10))
        else:
            offset, hour = weekday_slots[taken]
            taken += 1
            day = _next_open_day(today + timedelta(days=offset), business)
            slots[lead["id"]] = datetime.combine(day, time(hour))
    return slots


def _template_key(lead: dict) -> str:
    if lead["category"] == "hot":
        return "leak" if lead["urgency"] == 2 else "storm"
    return lead["service"]


def draft_followup(lead: dict, slot: datetime, business: dict, stale_cache: dict,
                   today: date, seeded: bool) -> dict:
    service = lead["service"] or "roof_inspection"
    key = _template_key(lead)
    subject, body = TEMPLATES[key]

    first_name = (lead["name"] or "").split(" ")[0]
    if first_name:
        greeting = f"Hi {first_name},"
    elif seeded:
        # Seeded fault 2: no personal name, so the placeholder is never filled.
        greeting = "Hi {first_name},"
    else:
        greeting = f"Hello {lead['company']} team,"

    price_info = business["prices"].get(service)
    price = ""
    short = ""
    if price_info:
        short = price_info["short"]
        # Seeded fault 1: quotes the March cache instead of today's price list.
        amount = stale_cache[service] if seeded else price_info["amount"]
        price = fmt_money(amount)

    label = format_slot(slot, today)
    text = body.format(
        greeting=greeting,
        promise=SEEDED_PROMISE if seeded else SAFE_PROMISE,
        slot=label,
        short=short,
        price=price,
        phone=business["phone"],
        signoff=f"The {business['name']} team",
    )
    return {
        "id": f"FU-{lead['id']}",
        "lead_id": lead["id"],
        "to": lead["email"],
        "subject": subject,
        "body": text,
        "services": [service] if price_info else [],
        "slot": slot.isoformat(timespec="minutes"),
        "slot_label": label,
    }
