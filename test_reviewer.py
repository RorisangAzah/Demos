import unittest
from datetime import date, datetime

from brief.common import load_json
from brief.reviewer import (apply_fixes, check_placeholders, check_prices, check_recipient, check_secrets,
                            check_slot, check_wording, review_call_summary, review_draft, status_for)
from run_brief import BRIEF_DATE, build_brief

BUSINESS = load_json("business.json")
TODAY = date(2026, 12, 1)


def make_draft(**overrides):
    draft = {
        "id": "FU-T", "lead_id": "L-T", "to": "pat@example.com", "subject": "Test",
        "body": "Hi Pat,\n\nOur gutter guard install is $1,850, and we can do it Wednesday, Dec 2 at 10:00 AM.",
        "services": ["gutter_guards"], "slot": "2026-12-02T10:00", "slot_label": "Wednesday, Dec 2 at 10:00 AM",
    }
    draft.update(overrides)
    return draft


LEAD = {"id": "L-T", "name": "Pat Jones", "company": None, "email": "pat@example.com"}


class PriceChecks(unittest.TestCase):
    def test_correct_price_passes(self):
        self.assertEqual(check_prices(make_draft(), BUSINESS), [])

    def test_stale_price_is_flagged_with_fix(self):
        draft = make_draft(body="Our gutter guard install is $1,650.")
        (finding,) = check_prices(draft, BUSINESS)
        self.assertEqual(finding["rule"], "price_mismatch")
        self.assertEqual(finding["evidence"], "$1,650")
        self.assertEqual(finding["replacement"], "$1,850")

    def test_another_services_price_is_wrong_for_this_service(self):
        draft = make_draft(body="Our gutter guard install is $149.")
        self.assertEqual(check_prices(draft, BUSINESS)[0]["rule"], "price_mismatch")

    def test_unknown_amount_without_a_service_is_flagged_without_a_fix(self):
        draft = make_draft(services=[], body="This costs $999.")
        (finding,) = check_prices(draft, BUSINESS)
        self.assertIsNone(finding["replacement"])


class PlaceholderChecks(unittest.TestCase):
    def test_company_lead_gets_company_greeting(self):
        draft = make_draft(body="Hi {first_name},\n\nHello.")
        lead = {**LEAD, "name": None, "company": "Oak Ridge Dental"}
        (finding,) = check_placeholders(draft, lead)
        self.assertEqual(finding["replacement"], "Hello Oak Ridge Dental team,")

    def test_person_without_company_gets_neutral_greeting(self):
        draft = make_draft(body="Hi {first_name},\n\nHello.")
        (finding,) = check_placeholders(draft, LEAD)
        self.assertEqual(finding["replacement"], "Hi there,")

    def test_placeholder_in_body_has_no_automatic_fix(self):
        draft = make_draft(body="Hi Pat,\n\nWe will see you at {slot}.")
        (finding,) = check_placeholders(draft, LEAD)
        self.assertIsNone(finding["replacement"])

    def test_clean_text_passes(self):
        self.assertEqual(check_placeholders(make_draft(), LEAD), [])


class SlotChecks(unittest.TestCase):
    def slot(self, iso):
        return make_draft(slot=iso, slot_label="the label")

    def test_weekday_in_hours_passes(self):
        self.assertEqual(check_slot(self.slot("2026-12-02T10:00"), BUSINESS, TODAY), [])

    def test_sunday_is_flagged_and_moved_to_saturday(self):
        (finding,) = check_slot(self.slot("2026-12-06T10:00"), BUSINESS, TODAY)
        self.assertEqual(finding["new_slot"], "2026-12-05T10:00")
        self.assertEqual(finding["replacement"], "Saturday, Dec 5 at 10:00 AM")

    def test_saturday_morning_passes(self):
        self.assertEqual(check_slot(self.slot("2026-12-05T10:00"), BUSINESS, TODAY), [])

    def test_saturday_afternoon_is_flagged(self):
        self.assertEqual(check_slot(self.slot("2026-12-05T14:00"), BUSINESS, TODAY)[0]["rule"], "closed_day")

    def test_visit_that_ends_after_closing_is_flagged(self):
        self.assertEqual(check_slot(self.slot("2026-12-02T16:30"), BUSINESS, TODAY)[0]["rule"], "closed_day")

    def test_last_full_hour_before_closing_passes(self):
        self.assertEqual(check_slot(self.slot("2026-12-02T16:00"), BUSINESS, TODAY), [])

    def test_before_opening_is_flagged(self):
        self.assertEqual(check_slot(self.slot("2026-12-02T07:30"), BUSINESS, TODAY)[0]["rule"], "closed_day")

    def test_fix_never_moves_a_visit_into_the_past(self):
        (finding,) = check_slot(self.slot("2026-12-06T10:00"), BUSINESS, date(2026, 12, 6))
        self.assertGreaterEqual(datetime.fromisoformat(finding["new_slot"]).date(), date(2026, 12, 6))


class WordingChecks(unittest.TestCase):
    def test_guarantee_is_flagged_with_approved_rewrite(self):
        draft = make_draft(body="We put storm calls first, and we guarantee same-day repair once we've found the cause.")
        (finding,) = check_wording(draft, BUSINESS)
        self.assertEqual(finding["rule"], "banned_wording")
        self.assertIn("earliest repair date", finding["replacement"])

    def test_other_banned_phrase_has_no_automatic_fix(self):
        (finding,) = check_wording(make_draft(body="We have the lowest price in town."), BUSINESS)
        self.assertIsNone(finding["replacement"])

    def test_normal_wording_passes(self):
        self.assertEqual(check_wording(make_draft(), BUSINESS), [])


class RecipientChecks(unittest.TestCase):
    def test_matching_recipient_passes(self):
        self.assertEqual(check_recipient(make_draft(), LEAD), [])

    def test_wrong_first_name_is_flagged(self):
        (finding,) = check_recipient(make_draft(body="Hi Priya,\n\nHello."), LEAD)
        self.assertEqual(finding["replacement"], "Hi Pat,")

    def test_wrong_email_is_flagged(self):
        (finding,) = check_recipient(make_draft(to="someone.else@example.com"), LEAD)
        self.assertEqual(finding["rule"], "wrong_recipient")

    def test_company_greeting_is_not_mistaken_for_a_name(self):
        draft = make_draft(body="Hello Oak Ridge Dental team,\n\nHello.")
        self.assertEqual(check_recipient(draft, {**LEAD, "name": None}), [])


class SecretChecks(unittest.TestCase):
    # Fake keys are assembled at runtime so no key-shaped string sits in the repository.
    def test_api_key_shape_is_blocked(self):
        self.assertEqual(check_secrets("Use this: " + "sk-" + "ab12" * 6)[0]["rule"], "secret")

    def test_aws_key_shape_is_blocked(self):
        self.assertEqual(check_secrets("AKIA" + "ABCD1234" * 2)[0]["rule"], "secret")

    def test_password_assignment_is_blocked(self):
        self.assertEqual(check_secrets("the " + "pass" + "word: hunter2hunter2")[0]["rule"], "secret")

    def test_private_key_header_is_blocked(self):
        self.assertEqual(check_secrets("-----BEGIN " + "RSA PRIVATE KEY-----")[0]["rule"], "secret")

    def test_normal_text_passes(self):
        self.assertEqual(check_secrets("Reply YES to confirm, or call us at (214) 555-0142."), [])

    def test_secret_in_a_draft_blocks_it(self):
        draft = make_draft(body="Hi Pat,\n\nOur gutter guard install is $1,850. Key: sk-" + "zz99" * 6)
        rules = [f["rule"] for f in review_draft(draft, LEAD, BUSINESS, TODAY)]
        self.assertIn("secret", rules)


class CallSummaryChecks(unittest.TestCase):
    CALL = {"id": "C-T", "contact": "Sam", "transcript": [
        {"speaker": "rep", "text": "Gutter guard install is $1,850."}]}

    def test_amount_nobody_said_is_flagged(self):
        summary = {"text": "Sam called. Rep quoted $2,000.", "quotes": []}
        self.assertEqual(review_call_summary(summary, self.CALL, BUSINESS)[0]["rule"], "hallucinated_amount")

    def test_old_quote_needs_a_decision_not_an_automatic_fix(self):
        call = {**self.CALL, "transcript": [{"speaker": "rep", "text": "Gutter guard install is $1,650."}]}
        summary = {"text": "Sam called. Rep quoted gutter guard install at $1,650.",
                   "quotes": [{"service": "gutter_guards", "amount": 1650}]}
        (finding,) = review_call_summary(summary, call, BUSINESS)
        self.assertEqual(finding["rule"], "outdated_quote")
        self.assertEqual(status_for([finding]), "needs_decision")
        self.assertEqual(len(finding["options"]), 2)

    def test_current_quote_passes(self):
        summary = {"text": "Sam called. Rep quoted gutter guard install at $1,850.",
                   "quotes": [{"service": "gutter_guards", "amount": 1850}]}
        self.assertEqual(review_call_summary(summary, self.CALL, BUSINESS), [])


class WholeRun(unittest.TestCase):
    def test_seeded_run_flags_exactly_the_planted_mistakes(self):
        brief = build_brief(seeded=True)
        flagged = {r["id"]: [f["rule"] for f in r["findings"]] for r in brief["review"] if r["status"] != "clean"}
        self.assertEqual(flagged, {
            "FU-L-101": ["banned_wording"], "FU-L-102": ["price_mismatch"],
            "FU-L-103": ["placeholder"], "FU-L-104": ["closed_day"],
            "CS-C-203": ["outdated_quote"],
        })

    def test_clean_drafts_are_not_flagged(self):
        brief = build_brief(seeded=True)
        clean = {r["id"] for r in brief["review"] if r["status"] == "clean" and r["kind"] == "draft"}
        self.assertEqual(clean, {"FU-L-105", "FU-L-106"})

    def test_agents_without_seeded_faults_produce_no_draft_findings(self):
        brief = build_brief(seeded=False)
        draft_findings = [f for r in brief["review"] if r["kind"] == "draft" for f in r["findings"]]
        self.assertEqual(draft_findings, [])

    def test_every_suggested_fix_passes_review_when_checked_again(self):
        brief = build_brief(seeded=True)
        fixable = [r for r in brief["review"] if r["kind"] == "draft" and r["status"] == "fix_ready"]
        self.assertEqual(len(fixable), 4)
        for item in fixable:
            self.assertTrue(item["suggested_is_clean"], item["id"])
            self.assertNotEqual(item["suggested"], item["original"])

    def test_apply_fixes_leaves_unfixable_text_alone(self):
        draft = make_draft(body="We have the lowest price in town.", services=[])
        findings = review_draft(draft, LEAD, BUSINESS, TODAY)
        self.assertEqual(apply_fixes(draft, findings)["body"], draft["body"])

    def test_the_calendar_date_is_a_tuesday(self):
        self.assertEqual(BRIEF_DATE.strftime("%A"), "Tuesday")


if __name__ == "__main__":
    unittest.main()
