#!/usr/bin/env python3
"""Run the Morning Brief: sort leads, summarize calls, draft follow-ups, review everything.

Usage:
    python3 run_brief.py                      # with the four seeded agent mistakes
    python3 run_brief.py --no-seeded-faults   # the same agents without the mistakes
    python3 run_brief.py --out some/folder    # write results somewhere else

No network access and no API keys are used.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from brief.calls import summarize_call
from brief.common import ROOT, load_json
from brief.followups import draft_followup, plan_slots
from brief.leads import sort_leads
from brief.owner_update import build_owner_update
from brief.reviewer import (apply_fixes, lessons_from, review_call_summary, review_draft, status_for)

BRIEF_DATE = date(2026, 12, 1)  # a Tuesday; the brief is written at 7:45 AM Central

DRAFT_CHECKS = ["Prices match the price list", "No template fields left in the text", "Visit falls inside business hours",
                "No promises the business has not approved", "Greeting and address match the lead", "No credentials in the text"]
CALL_CHECKS = ["Every amount was said on the call", "Quoted prices match the price list", "No credentials in the text"]


def build_brief(seeded: bool = True, today: date = BRIEF_DATE) -> dict:
    business = load_json("business.json")
    leads = sort_leads(load_json("leads.json"))
    calls = load_json("calls.json")
    stale_cache = load_json("price_cache_stale.json")
    leads_by_id = {x["id"]: x for x in leads}

    slots = plan_slots(leads, business, today, seeded)
    drafts = [draft_followup(x, slots[x["id"]], business, stale_cache, today, seeded)
              for x in leads if x["id"] in slots]

    review = []
    for draft in drafts:
        lead = leads_by_id[draft["lead_id"]]
        findings = review_draft(draft, lead, business, today)
        fixed = apply_fixes(draft, findings) if findings else None
        recheck = review_draft(fixed, lead, business, today) if fixed else []
        review.append({
            "id": draft["id"], "kind": "draft",
            "title": f"{lead['name'] or lead['company']}: {lead['topic'].lower()}",
            "subtitle": f"To {draft['to']}", "subject": draft["subject"],
            "original": draft["body"], "findings": findings,
            "status": status_for(findings),
            "suggested": fixed["body"] if fixed and fixed["body"] != draft["body"] else None,
            "suggested_is_clean": bool(fixed) and not recheck,
            "checks": DRAFT_CHECKS,
        })

    summaries = [summarize_call(c, business) for c in calls]
    for call, summary in zip(calls, summaries):
        findings = review_call_summary(summary, call, business)
        review.append({
            "id": f"CS-{call['id']}", "kind": "call_summary",
            "title": f"{call['contact']}: {call['subject']}",
            "subtitle": f"Call {call['id']}, {call['duration_min']} min", "subject": None,
            "original": summary["text"], "findings": findings,
            "status": status_for(findings), "suggested": None, "suggested_is_clean": False,
            "checks": CALL_CHECKS,
        })

    flagged = [r for r in review if r["status"] != "clean"]
    owner_update = build_owner_update(business, leads, calls, review, summaries)
    return {
        "business": {k: business[k] for k in ("name", "owner", "owner_first", "city")},
        "date_label": "Tuesday, Dec 1 · 7:45 AM Central",
        "seeded_faults": seeded,
        "prices": {k: {"short": v["short"], "amount": v["amount"]} for k, v in business["prices"].items()},
        "leads": [{k: x[k] for k in ("id", "name", "company", "source", "received", "message",
                                     "category", "reason", "topic")} for x in leads],
        "calls": [{**c, "summary": s["text"], "action_items": s["action_items"],
                   "review_id": f"CS-{c['id']}"} for c, s in zip(calls, summaries)],
        "review": review,
        "lessons": lessons_from(review),
        "owner_update": owner_update,
        "stats": {
            "leads": len(leads), "calls": len(calls), "drafts": len(drafts),
            "outputs_reviewed": len(review), "flagged": len(flagged), "clean": len(review) - len(flagged),
        },
    }


def write_outputs(brief: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "owner_update.md").write_text(brief["owner_update"]["text"] + "\n", encoding="utf-8")
    lines = ["# Proposed lessons for the agents", "",
             "Each line is a change to the agent instructions. Nothing is applied until the owner approves it.", ""]
    for lesson in brief["lessons"]:
        lines.append(f"- {lesson['lesson']} (caught on {', '.join(lesson['items'])})")
    (out / "lessons.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-seeded-faults", action="store_true", help="run the agents without the planted mistakes")
    parser.add_argument("--out", default=str(ROOT / "output"), help="folder for brief.json, owner_update.md, lessons.md")
    args = parser.parse_args()

    brief = build_brief(seeded=not args.no_seeded_faults)
    write_outputs(brief, Path(args.out))

    stats = brief["stats"]
    print(f"{stats['leads']} leads sorted, {stats['calls']} calls summarized, {stats['drafts']} follow-ups drafted.")
    print(f"{stats['outputs_reviewed']} outputs reviewed: {stats['clean']} clean, {stats['flagged']} flagged.\n")
    for item in brief["review"]:
        marker = "ok  " if item["status"] == "clean" else "FLAG"
        print(f"  [{marker}] {item['id']:<10} {item['title']}")
        for finding in item["findings"]:
            print(f"           - {finding['title']}: {finding['detail']}")
    print(f"\nWrote {Path(args.out)}/brief.json, owner_update.md, lessons.md")


if __name__ == "__main__":
    main()
