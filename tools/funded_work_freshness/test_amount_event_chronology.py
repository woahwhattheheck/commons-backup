from __future__ import annotations

import unittest

from funded_work_freshness import Candidate, preflight
from test_support import NOW, FakeTransport, evidence_routes, open_issue


GH = "https://github.com/acme/widget/issues/12"


def authority_comment(body: str, stamp: str):
    return {
        "body": body,
        "user": {"login": "maintainer"},
        "author_association": "OWNER",
        "created_at": stamp,
        "updated_at": stamp,
    }


class AmountEventChronologyTests(unittest.TestCase):
    def _receipt(
        self,
        *,
        issue_amount: str,
        issue_currency: str = "USD",
        issue_updated_at: str,
        comments=(),
        candidate_amount: str,
        candidate_currency: str = "USD",
    ):
        symbol_or_code = "$" if issue_currency == "USD" else issue_currency + " "
        issue = open_issue(
            GH,
            body=(
                "## Acceptance Criteria\n"
                "- [ ] deterministic receipt\n\n"
                f"Reward: {symbol_or_code}{issue_amount} via Algora"
            ),
            updated_at=issue_updated_at,
        )
        candidate = Candidate.validated(
            candidate_url=GH,
            platform="fixture-board",
            advertised_amount=candidate_amount,
            currency=candidate_currency,
            canonical_url=GH,
            max_age_days=30,
        )
        return preflight(
            candidate,
            FakeTransport(evidence_routes("acme", "widget", 12, issue, list(comments))),
            observed_at=NOW,
        )

    def test_newer_issue_edit_supersedes_older_comment(self):
        comment = authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z")
        current = self._receipt(
            issue_amount="300",
            issue_updated_at="2026-09-13T05:00:00Z",
            comments=[comment],
            candidate_amount="300",
        )
        stale = self._receipt(
            issue_amount="300",
            issue_updated_at="2026-09-13T05:00:00Z",
            comments=[comment],
            candidate_amount="200",
        )
        self.assertEqual(current["freshness_status"], "actionable")
        self.assertEqual(current["checks"]["canonical_current_reward_amount"], "300")
        self.assertEqual(stale["freshness_status"], "ambiguous")
        self.assertEqual(
            stale["reasons"], ["advertised_amount_superseded_by_newer_canonical_evidence"]
        )

    def test_newer_comment_supersedes_older_issue_snapshot(self):
        comment = authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z")
        receipt = self._receipt(
            issue_amount="300",
            issue_updated_at="2026-09-13T03:00:00Z",
            comments=[comment],
            candidate_amount="200",
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")

    def test_newer_issue_currency_change_beats_older_comment_without_fx(self):
        comment = authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z")
        receipt = self._receipt(
            issue_amount="300",
            issue_currency="EUR",
            issue_updated_at="2026-09-13T05:00:00Z",
            comments=[comment],
            candidate_amount="300",
            candidate_currency="EUR",
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_currency"], "EUR")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "300")

    def test_equal_time_conflicting_authority_fails_closed(self):
        comment = authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z")
        receipt = self._receipt(
            issue_amount="300",
            issue_updated_at="2026-09-13T04:00:00Z",
            comments=[comment],
            candidate_amount="200",
        )
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["checks"]["authoritative_amount_state"], "ambiguous")
        self.assertIsNone(receipt["checks"]["canonical_current_reward_amount"])
        self.assertEqual(receipt["reasons"], ["canonical_reward_amount_ambiguous"])

    def test_equal_time_identical_authority_is_deterministic(self):
        comment = authority_comment("Reward: $200 via Algora.", "2026-09-13T04:00:00Z")
        receipt = self._receipt(
            issue_amount="200",
            issue_updated_at="2026-09-13T04:00:00Z",
            comments=[comment],
            candidate_amount="200",
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["checks"]["canonical_current_reward_currency"], "USD")
        self.assertEqual(receipt["checks"]["canonical_current_reward_amount"], "200")


if __name__ == "__main__":
    unittest.main()
