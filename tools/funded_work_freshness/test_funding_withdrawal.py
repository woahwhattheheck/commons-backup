from __future__ import annotations

import unittest

from funded_work_freshness import preflight
from test_support import NOW, FakeTransport, candidate, evidence_routes, open_issue


def authority_comment(body: str, stamp: str, *, association: str = "OWNER", login: str = "maintainer"):
    return {
        "body": body,
        "user": {"login": login},
        "author_association": association,
        "created_at": stamp,
        "updated_at": stamp,
    }


class FundingWithdrawalTests(unittest.TestCase):
    def test_newer_trusted_withdrawal_overrides_older_positive_evidence(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "The bounty is withdrawn and no longer funded. Do not work on this reward.",
                "2026-09-13T04:00:00Z",
            )
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertTrue(receipt["checks"]["sponsor_mechanism_present"])
        self.assertTrue(
            receipt["checks"]["advertised_amount_supported_by_canonical_evidence"]
        )
        self.assertTrue(receipt["checks"]["acceptance_criteria_reachable"])
        self.assertEqual(receipt["checks"]["authoritative_funding_state"], "withdrawn")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(
            receipt["reasons"], ["canonical_funding_authoritatively_withdrawn"]
        )

    def test_outsider_withdrawal_cannot_revoke_funding(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "The bounty is withdrawn and no longer funded.",
                "2026-09-13T04:00:00Z",
                association="NONE",
                login="random-outsider",
            )
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(
            receipt["checks"]["authoritative_funding_state"], "not_withdrawn"
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")

    def test_later_complete_trusted_restoration_can_reactivate(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "The bounty is withdrawn and no longer funded.",
                "2026-09-13T03:00:00Z",
            ),
            authority_comment(
                "Bounty restored and available again.\n\n"
                "## Acceptance Criteria\n"
                "- [ ] deterministic receipt\n\n"
                "Reward: $500 via Algora",
                "2026-09-13T04:00:00Z",
            ),
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(
            receipt["checks"]["authoritative_funding_state"], "not_withdrawn"
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")

    def test_incomplete_restore_does_not_resurrect_stale_terms(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "The bounty is withdrawn and no longer funded.",
                "2026-09-13T03:00:00Z",
            ),
            authority_comment(
                "Bounty restored. Same terms as before.",
                "2026-09-13T04:00:00Z",
            ),
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["checks"]["authoritative_funding_state"], "withdrawn")
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(
            receipt["reasons"], ["canonical_funding_authoritatively_withdrawn"]
        )

    def test_unrelated_cancelled_build_does_not_revoke_bounty(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "The cancelled build was rerun successfully; the bounty remains available.",
                "2026-09-13T04:00:00Z",
            )
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(
            receipt["checks"]["authoritative_funding_state"], "not_withdrawn"
        )
        self.assertEqual(receipt["freshness_status"], "actionable")

    def test_allowlisted_sponsor_bot_can_withdraw_reward(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            authority_comment(
                "Reward revoked.",
                "2026-09-13T04:00:00Z",
                association="NONE",
                login="algora-pbc[bot]",
            )
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["checks"]["authoritative_funding_state"], "withdrawn")
        self.assertEqual(receipt["freshness_status"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
