import unittest

from brief.calls import summarize_call
from brief.common import detect_service, load_json, money_amounts
from brief.leads import classify_lead, sort_leads

BUSINESS = load_json("business.json")


def lead(message, name="Test Person"):
    return {"id": "L-T", "name": name, "company": None, "email": "t@example.com",
            "source": "Website form", "received": "2026-12-01T07:00", "message": message}


class LeadSorting(unittest.TestCase):
    def test_active_leak_is_hot_and_most_urgent(self):
        result = classify_lead(lead("My roof is leaking and the ceiling is dripping."))
        self.assertEqual((result["category"], result["urgency"]), ("hot", 2))

    def test_hail_is_hot_but_less_urgent_than_an_active_leak(self):
        result = classify_lead(lead("Hail cracked a few shingles."))
        self.assertEqual((result["category"], result["urgency"]), ("hot", 1))

    def test_price_request_is_warm(self):
        self.assertEqual(classify_lead(lead("How much to clean gutters?"))["category"], "warm")

    def test_just_browsing_is_cold_even_when_it_mentions_prices(self):
        self.assertEqual(classify_lead(lead("Just browsing prices, maybe next year."))["category"], "cold")

    def test_spam_is_caught(self):
        self.assertEqual(classify_lead(lead("Rank #1 on Google! Click here."))["category"], "spam")

    def test_plumbing_is_not_a_fit(self):
        self.assertEqual(classify_lead(lead("Do you do plumbing?"))["category"], "not_a_fit")

    def test_sorted_order_puts_urgent_leads_first(self):
        leads = sort_leads(load_json("leads.json"))
        self.assertEqual([x["id"] for x in leads][:2], ["L-106", "L-101"])
        self.assertEqual(leads[-1]["category"], "spam")

    def test_every_lead_gets_a_category(self):
        counts = {}
        for x in sort_leads(load_json("leads.json")):
            counts[x["category"]] = counts.get(x["category"], 0) + 1
        self.assertEqual(counts, {"hot": 2, "warm": 4, "cold": 1, "not_a_fit": 1, "spam": 1})


class Helpers(unittest.TestCase):
    def test_money_with_commas_and_trailing_punctuation(self):
        self.assertEqual(money_amounts("It is $1,650. Or $149, maybe."), [1650, 149])

    def test_service_detection(self):
        self.assertEqual(detect_service("We want gutter guards"), "gutter_guards")
        self.assertEqual(detect_service("annual inspection of our flat roof"), "commercial_inspection")


class CallSummaries(unittest.TestCase):
    def test_summary_records_the_quote_and_the_promises(self):
        calls = {c["id"]: c for c in load_json("calls.json")}
        summary = summarize_call(calls["C-202"], BUSINESS)
        self.assertIn("$22,000", summary["text"])
        self.assertEqual(summary["action_items"], [
            "Email the written estimate by Wednesday.", "Check the weather window with the crew."])

    def test_single_price_quote_is_tied_to_its_service(self):
        calls = {c["id"]: c for c in load_json("calls.json")}
        summary = summarize_call(calls["C-201"], BUSINESS)
        self.assertEqual(summary["quotes"], [{"service": "gutter_cleaning", "amount": 149}])


class OwnerUpdate(unittest.TestCase):
    def setUp(self):
        from run_brief import build_brief
        self.update = build_brief(seeded=True)["owner_update"]

    def test_counts_match_the_run(self):
        done = " ".join(self.update["done"])
        self.assertIn("Sorted 9 overnight inquiries", done)
        self.assertIn("2 were clean. 4 had a problem", done)

    def test_old_quote_decision_goes_to_the_owner(self):
        (decision,) = self.update["needs_you"]
        self.assertIn("$1,650", decision)
        self.assertIn("$1,850", decision)

    def test_page_version_is_short_and_text_version_lists_every_promise(self):
        self.assertEqual(len(self.update["next"]), 3)
        self.assertIn("side gate note", self.update["text"])
        self.assertIn("Nothing has been sent", self.update["text"])


if __name__ == "__main__":
    unittest.main()
