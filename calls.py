"""Agent 2: summarize yesterday's calls and pull out promises and quoted prices."""
from __future__ import annotations

import re

from .common import detect_service, fmt_money, money_amounts

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
COMMITMENT = re.compile(r"\b(?:I'll|I will|we'll|we will)\s+(.+?)[.!]?$", re.IGNORECASE)
CONCERN = re.compile(r"worried|concern|forecast|delay", re.IGNORECASE)


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def summarize_call(call: dict, business: dict) -> dict:
    prices = business["prices"]
    quotes: list[dict] = []
    discussed: list[int] = []
    action_items: list[str] = []
    concerns: list[str] = []

    for turn in call["transcript"]:
        for sentence in SENTENCE_SPLIT.split(turn["text"]):
            sentence = sentence.strip()
            if turn["speaker"] == "rep":
                amounts = money_amounts(sentence)
                if amounts:
                    service = detect_service(sentence)
                    if len(amounts) == 1 and service in prices:
                        quotes.append({"service": service, "amount": amounts[0]})
                    else:
                        discussed.extend(a for a in amounts if a not in discussed)
                for part in re.split(r"\s+and\s+(?=I'll|I will)", sentence):
                    match = COMMITMENT.search(part)
                    if match:
                        action_items.append(_capitalize(match.group(1)) + ".")
            elif CONCERN.search(sentence):
                concerns.append(sentence)

    parts = [f"{call['contact']} called about {call['subject']}."]
    for quote in quotes:
        parts.append(f"Rep quoted {prices[quote['service']]['short']} at {fmt_money(quote['amount'])}.")
    if discussed:
        parts.append("Amounts discussed: " + ", ".join(fmt_money(a) for a in discussed) + ".")
    if concerns:
        parts.append("Caller said: " + " ".join(f'"{c}"' for c in concerns[:2]))

    return {
        "call_id": call["id"],
        "text": " ".join(parts),
        "quotes": quotes,
        "action_items": action_items,
    }
