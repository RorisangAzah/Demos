"""Write the plain-English update for the owner: done, next, needs you."""
from __future__ import annotations

from .common import fmt_money

RULE_WORDS = {
    "price_mismatch": "a wrong price",
    "placeholder": "an unfilled name field",
    "closed_day": "a visit offered on a day we are closed",
    "banned_wording": "a promise we do not make",
    "wrong_recipient": "the wrong name",
    "secret": "a password-like string",
    "hallucinated_amount": "an amount nobody said",
}


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def build_owner_update(business: dict, leads: list[dict], calls: list[dict],
                       review: list[dict], summaries: list[dict]) -> dict:
    by_cat = {c: [x for x in leads if x["category"] == c] for c in ("hot", "warm", "cold", "not_a_fit", "spam")}
    drafts = [r for r in review if r["kind"] == "draft"]
    clean = [r for r in drafts if r["status"] == "clean"]
    flagged = [r for r in drafts if r["status"] != "clean"]
    caught = [RULE_WORDS[f["rule"]] for r in flagged for f in r["findings"] if f["rule"] in RULE_WORDS]

    done = [
        f"Sorted {len(leads)} overnight inquiries: {len(by_cat['hot'])} urgent, {len(by_cat['warm'])} quote requests, "
        f"{len(by_cat['cold']) + len(by_cat['not_a_fit'])} not ready or not a fit, {len(by_cat['spam'])} spam.",
        f"Summarized yesterday's {len(calls)} calls.",
        f"Drafted {len(drafts)} follow-ups and checked every one before anything went out. "
        f"{len(clean)} were clean. {len(flagged)} had a problem I caught: {_join(caught)}. Fixes are ready.",
    ]

    hot_names = [x["name"] or x["company"] for x in by_cat["hot"]]
    hot_topics = [x["topic"].lower() for x in by_cat["hot"]]
    next_steps = [
        "Call the urgent leads first: " + _join([f"{n} ({t})" for n, t in zip(hot_names, hot_topics)]) + ".",
        f"Approve the {len(clean)} clean follow-ups and look over the {len(flagged)} fixes.",
    ]
    promises = []
    for summary in summaries:
        call = next(c for c in calls if c["id"] == summary["call_id"])
        for item in summary["action_items"]:
            promises.append(f"From {call['contact']}'s call: {item[0].lower() + item[1:]}")
    next_short = next_steps + [f"Keep the {len(promises)} promises made on yesterday's calls. Each one is listed with its call."]
    next_full = next_steps + promises

    needs_you = []
    for r in review:
        for f in r["findings"]:
            if f["rule"] == "outdated_quote":
                needs_you.append(
                    f"{f['contact']} was quoted {fmt_money(f['quoted'])} for {f['service_short']} on Monday's call. "
                    f"The price list now says {fmt_money(f['current'])}. Do we honor {fmt_money(f['quoted'])} for them, "
                    f"or do we call to explain the new price?")
    if not needs_you:
        needs_you.append("Nothing needs a decision from you.")

    blocked = "Nothing is blocked. Nothing has been sent."
    text = "\n".join(
        [f"Good morning, {business['owner_first']}.", "", "Done"] + [f"- {x}" for x in done]
        + ["", "Next"] + [f"- {x}" for x in next_full]
        + ["", "Needs your call"] + [f"- {x}" for x in needs_you]
        + ["", blocked]
    )
    return {"done": done, "next": next_short, "needs_you": needs_you, "blocked": blocked, "text": text}
