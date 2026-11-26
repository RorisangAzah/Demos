"""Shared helpers: data loading, money parsing, service detection, slot labels."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def load_json(name: str, data_dir: Path = DATA_DIR):
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


MONEY_RE = re.compile(r"\$\s?(\d[\d,]*)(?:\.\d{2})?")


def money_amounts(text: str) -> list[int]:
    """Whole-dollar amounts found in text, in order. '$1,650.' -> 1650."""
    return [int(m.group(1).replace(",", "") or 0) for m in MONEY_RE.finditer(text)]


def fmt_money(amount: int) -> str:
    return f"${amount:,}"


# Order matters: the first service whose keyword appears wins.
SERVICE_KEYWORDS = [
    ("gutter_guards", ("gutter guard", "leaf guard")),
    ("gutter_cleaning", ("clean gutters", "gutter cleaning", "cleaning gutters")),
    ("commercial_inspection", ("office building", "flat roof", "commercial")),
    ("roof_replacement", ("replace", "replacing", "new roof", "year-old roof")),
    ("roof_inspection", ("inspection", "leak", "hail", "storm", "shingle", "water stain", "dripping")),
]


def detect_service(text: str) -> str | None:
    lower = text.lower()
    for service_id, keywords in SERVICE_KEYWORDS:
        if any(k in lower for k in keywords):
            return service_id
    return None


def clock_label(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def format_slot(dt: datetime, today) -> str:
    """'today at 1:00 PM' or 'Wednesday, Dec 2 at 10:00 AM'."""
    if dt.date() == today:
        return f"today at {clock_label(dt)}"
    return f"{dt:%A}, {dt:%b} {dt.day} at {clock_label(dt)}"


def is_open(dt: datetime, business: dict) -> tuple[bool, str]:
    """Whether a whole appointment starting at dt fits inside business hours."""
    hours = business["hours"][DAYS[dt.weekday()]]
    day_name = f"{dt:%A}"
    if not hours:
        return False, f"Hartwell is closed on {day_name}s."
    open_t = datetime.strptime(hours[0], "%H:%M").time()
    close_t = datetime.strptime(hours[1], "%H:%M").time()
    end_minutes = dt.hour * 60 + dt.minute + business["appointment_minutes"]
    close_minutes = close_t.hour * 60 + close_t.minute
    if dt.time() < open_t or end_minutes > close_minutes:
        return False, (
            f"{day_name} hours are {clock_label(datetime.combine(dt.date(), open_t))} "
            f"to {clock_label(datetime.combine(dt.date(), close_t))}, and "
            f"{clock_label(dt)} does not fit a {business['appointment_minutes']}-minute visit."
        )
    return True, ""
