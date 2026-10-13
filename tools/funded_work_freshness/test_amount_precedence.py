from __future__ import annotations

import unittest

from funded_work_freshness import Candidate, preflight
from test_support import NOW, FakeTransport, candidate, evidence_routes, open_issue


def authority_comment(body: str, stamp: str, *, association: str = "OWNER", login: str = "maintainer"):
    return {
        "body": body,
        "user": {"login": login},
        "author_association": association,
        "created_at": stamp,
        "updated_at": stamp,
    }


class AmountPrecedenceTests(unittest.TestCase):
    def _receipt(self, comments, *, amount="500", issue=None):
        gh = "https://github.com/acme/widget/issues/12"
        return preflight(
            candidate(gh, amount=amount, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue or open_issue(gh), comments)),
            observed_at=NOW,
        )

    def test_newer_trusted_amount_supersedes_stale_board_amount(self):
        receipt = self._receipt([authority_comment("Reward: $200 via Algora. Effective immediately.", "2026-09-13T04:00:00Z")])
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertFalse(receipt["checks"]["advertised_amount_supported_by_canonical_evidence"])
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "resolved")
        self.assertEqual(receipt["checks"]["canonical_current_reward_currency"], "USD")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")
        self.assertEqual(receipt["reasons"], ["advertised_amount_superseded_by_newer_canonical_evidence"])

    def test_candidate_matching_newer_trusted_amount_is_actionable(self):
        receipt = self._receipt([authority_comment("Reward: $200 via Algora. Effective immediately.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")
        self.assertTrue(receipt["checks"]["advertised_amount_supported_by_canonical_evidence"])
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_outsider_amount_chatter_cannot_supersede_trusted_amount(self):
        receipt = self._receipt([authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z", association="NONE", login="random-outsider")])
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "500")

    def test_allowlisted_sponsor_bot_can_supersede_amount(self):
        receipt = self._receipt([authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z", association="NONE", login="algora-pbc[bot]")])
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")
        self.assertEqual(receipt["reasons"], ["advertised_amount_superseded_by_newer_canonical_evidence"])

    def test_unrelated_budget_money_does_not_change_reward_amount(self):
        receipt = self._receipt([authority_comment("The test budget is $200; the bounty remains available.", "2026-09-13T04:00:00Z")])
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "500")

    def test_comment_chronology_uses_timestamps_not_api_input_order(self):
        receipt = self._receipt([
            authority_comment("Reward: $300 via Algora.", "2026-09-13T04:00:00Z"),
            authority_comment("Reward: $200 via Algora.", "2026-09-13T03:00:00Z"),
        ], amount="300")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "300")

    def test_currency_change_supersedes_old_currency_without_fx_inference(self):
        gh = "https://github.com/acme/widget/issues/12"
        comments = [authority_comment("Reward: EUR 200 via Algora.", "2026-09-13T04:00:00Z")]
        usd_receipt = preflight(
            candidate(gh, amount="500", canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, open_issue(gh), comments)),
            observed_at=NOW,
        )
        self.assertEqual(usd_receipt["freshness_status"], "ambiguous")
        self.assertEqual(usd_receipt["checks"]["canonical_current_reward_currency"], "EUR")
        self.assertEqual(usd_receipt["reasons"], ["advertised_amount_superseded_by_newer_canonical_evidence"])

        eur_candidate = Candidate.validated(
            candidate_url=gh,
            platform="fixture-board",
            advertised_amount="200",
            currency="EUR",
            canonical_url=gh,
            max_age_days=30,
        )
        eur_receipt = preflight(
            eur_candidate,
            FakeTransport(evidence_routes("acme", "widget", 12, open_issue(gh), comments)),
            observed_at=NOW,
        )
        self.assertEqual(eur_receipt["freshness_status"], "actionable")
        self.assertTrue(eur_receipt["checks"]["advertised_amount_supported_by_canonical_evidence"])

    def test_explicit_from_to_transition_resolves_destination(self):
        receipt = self._receipt([authority_comment("Reward increased from $500 to $200 via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_unrelated_to_between_amounts_does_not_invent_transition(self):
        receipt = self._receipt([authority_comment("Reward: $500 donated to charity $200.", "2026-09-13T04:00:00Z")], amount="500")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_from_to_transition_with_third_amount_fails_closed(self):
        receipt = self._receipt([authority_comment("Reward changed from $500 to $200, with $50 allocated for CI costs.", "2026-09-13T04:00:00Z")], amount="50")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_now_transition_with_third_amount_fails_closed(self):
        receipt = self._receipt([authority_comment("Reward was $500, now $200, with $50 allocated for CI costs.", "2026-09-13T04:00:00Z")], amount="50")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_unrelated_now_subject_does_not_invent_reward_transition(self):
        receipt = self._receipt([authority_comment("Reward was $500, test budget now $200.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_failed_from_to_cannot_be_rescued_by_unrelated_now(self):
        receipt = self._receipt([authority_comment("Reward changed from $500 to TBD. CI budget is now $200.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_unrelated_to_subject_does_not_invent_reward_transition(self):
        receipt = self._receipt([authority_comment("Reward changed from $500, CI budget goes to $200.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_leading_unrelated_money_does_not_hide_from_to_transition(self):
        receipt = self._receipt([authority_comment("CI budget is $50. Reward changed from $500 to $200.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_leading_unrelated_money_does_not_hide_now_transition(self):
        receipt = self._receipt([authority_comment("CI budget is $50. Reward was $500, now $200.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_leading_unrelated_money_does_not_hide_direct_reward_amount(self):
        receipt = self._receipt([authority_comment("CI budget is $50. Reward: $500 via Algora.", "2026-09-13T04:00:00Z")])
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "500")

    def test_leading_unrelated_money_preserves_reward_ambiguity(self):
        receipt = self._receipt([authority_comment("CI budget is $50. Reward: $200 or $300 depending on scope.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_conflicting_trailing_currency_code_fails_closed(self):
        receipt = self._receipt([authority_comment("Reward: $200 CAD via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_conflicting_prefix_currency_code_fails_closed(self):
        receipt = self._receipt([authority_comment("Reward: CAD $200 via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_consistent_trailing_currency_code_resolves(self):
        receipt = self._receipt([authority_comment("Reward: $200 USD via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_currency"], "USD")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_consistent_prefix_currency_code_resolves(self):
        receipt = self._receipt([authority_comment("Reward: USD $200 via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_currency"], "USD")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_euro_symbol_with_usd_code_fails_closed(self):
        receipt = self._receipt([authority_comment("Reward: €200 USD via Algora.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_multiple_current_amounts_without_transition_fail_closed(self):
        receipt = self._receipt([authority_comment("Reward: $200 or $300 depending on scope.", "2026-09-13T04:00:00Z")], amount="200")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])


if __name__ == "__main__":
    unittest.main()
