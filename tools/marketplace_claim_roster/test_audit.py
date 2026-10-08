"""Focused paid-claim identity and roster-freshness contracts (offline)."""
import unittest

from tools.marketplace_claim_roster.audit import audit, canonical_pr, review


class ClaimRosterTest(unittest.TestCase):
    def item(self, **changes):
        item = {
            "provider": "bountyhub",
            "listing_url": "https://www.bountyhub.dev/en/bounty/view/example-uuid/example",
            "expected_login": "woahwhattheheck",
            "source_pr_author": "woahwhattheheck",
            "source_pr_url": "https://github.com/react/react/pull/37729",
            "checked_at": "2026-10-08T05:50:00Z",
            "roster_complete": True,
            "claims": [],
        }
        item.update(changes)
        return item

    def test_exact_original_author_and_upstream_pr_required(self):
        row = self.item(claims=[{
            "claimant": "WoahWhatTheHeck",
            "pr_url": "https://www.github.com/React/React/pull/037729?ref=portal",
            "status": "submitted",
        }])
        self.assertEqual("EXACT_CLAIM_VISIBLE", review(row)["status"])
        self.assertEqual("NOT_EVALUATED", review(row)["payment_status"])
        self.assertEqual("AUTHOR_UNVERIFIED_OR_MISMATCHED",
                         review(self.item(source_pr_author="otheruser"))["status"])
        self.assertEqual("PR_UNVERIFIED", review(self.item(source_pr_url=""))["status"])

    def test_claimant_presence_is_not_exact_pr_registration(self):
        row = self.item(claims=[{"claimant": "woahwhattheheck"}])
        self.assertEqual("CLAIMANT_VISIBLE_PR_UNVERIFIED", review(row)["status"])
        row["claims"][0]["pr_url"] = "https://github.com/react/react/pull/100"
        self.assertEqual("CLAIMANT_VISIBLE_PR_UNVERIFIED", review(row)["status"])

    def test_only_complete_roster_supports_absence_finding(self):
        self.assertEqual("ABSENT_FROM_COMPLETE_ROSTER", review(self.item())["status"])
        self.assertEqual("ROSTER_INCOMPLETE", review(self.item(roster_complete=False))["status"])
        row = self.item(manual_contribution_required=True)
        self.assertEqual("HUMAN_CONTRIBUTION_ELIGIBILITY_REVIEW",
                         review(row)["next_action"])

    def test_other_claimant_and_rejected_claim_are_not_success(self):
        row = self.item(claims=[{
            "claimant": "otheruser",
            "pr_url": "https://github.com/react/react/pull/37729",
        }])
        self.assertEqual("PR_ASSOCIATED_WITH_OTHER_ACCOUNT", review(row)["status"])
        row["claims"][0]["claimant"] = "woahwhattheheck"
        row["claims"][0]["status"] = "rejected"
        self.assertEqual("REJECTED_OR_WITHDRAWN_CLAIM_VISIBLE", review(row)["status"])

    def test_listing_ids_deduped_but_issue_can_have_multiple_bounties(self):
        first = self.item()
        same_issue_other_listing = self.item(
            listing_url="https://www.bountyhub.dev/en/bounty/view/other-uuid/example")
        self.assertEqual(2, audit({"listings": [first, same_issue_other_listing]})["count"])
        with self.assertRaisesRegex(ValueError, "Duplicate marketplace listing"):
            audit({"listings": [first, first]})

    def test_canonical_pr_rejects_unrelated_links(self):
        for value in ["https://github.com/react/react/issues/37729",
                      "http://github.com/react/react/pull/37729",
                      "https://evilgithub.com/react/react/pull/37729",
                      "https://github.com/react/react/pull/notanumber", None]:
            self.assertIsNone(canonical_pr(value))


if __name__ == "__main__":
    unittest.main()
