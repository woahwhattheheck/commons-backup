from __future__ import annotations

import unittest

from funded_work_freshness import preflight
from test_support import NOW, FakeTransport, candidate, evidence_routes, open_issue


class ActivityAuthorityTests(unittest.TestCase):
    def _old_funded_issue(self, gh: str):
        issue = open_issue(gh)
        issue["created_at"] = "2026-07-01T00:00:00Z"
        # GitHub advances issue.updated_at for ordinary comment activity, so this
        # deliberately looks fresh even when no authoritative actor has spoken.
        issue["updated_at"] = "2026-09-13T06:00:00Z"
        return issue

    def test_outsider_chatter_cannot_refresh_old_funded_issue(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = self._old_funded_issue(gh)
        comments = [
            {
                "body": "Still available?",
                "user": {"login": "random-outsider"},
                "author_association": "NONE",
                "created_at": "2026-09-13T05:45:00Z",
                "updated_at": "2026-09-13T05:45:00Z",
            }
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "stale")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(receipt["reasons"], ["canonical_activity_too_old"])
        self.assertEqual(
            receipt["checks"]["last_substantive_activity"], "2026-07-01T00:00:00Z"
        )

    def test_comment_inflated_issue_updated_at_is_not_a_freshness_clock(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = self._old_funded_issue(gh)
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "stale")
        self.assertEqual(receipt["reasons"], ["canonical_activity_too_old"])
        self.assertEqual(
            receipt["checks"]["last_substantive_activity"], "2026-07-01T00:00:00Z"
        )

    def test_trusted_maintainer_comment_can_refresh_old_funded_issue(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = self._old_funded_issue(gh)
        comments = [
            {
                "body": "This reward remains available under the criteria above.",
                "user": {"login": "maintainer"},
                "author_association": "OWNER",
                "created_at": "2026-09-13T04:00:00Z",
                "updated_at": "2026-09-13T04:00:00Z",
            }
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")
        self.assertEqual(
            receipt["checks"]["last_substantive_activity"], "2026-09-13T04:00:00Z"
        )

    def test_current_issue_creation_remains_a_valid_freshness_baseline(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        # No comment is required for a genuinely recent canonical issue.
        issue["created_at"] = "2026-09-10T00:00:00Z"
        issue["updated_at"] = "2026-09-13T06:00:00Z"
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(
            receipt["checks"]["last_substantive_activity"], "2026-09-10T00:00:00Z"
        )

    def test_untrusted_claim_is_still_visible_to_occupancy_logic(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        comments = [
            {
                "body": "/attempt #12",
                "user": {"login": "solver"},
                "author_association": "NONE",
                "created_at": "2026-09-13T04:00:00Z",
                "updated_at": "2026-09-13T04:00:00Z",
            }
        ]
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue, comments)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "occupied")
        self.assertEqual(receipt["checks"]["visible_claimants"], ["solver"])
        self.assertEqual(
            receipt["checks"]["last_substantive_activity"], "2026-09-10T00:00:00Z"
        )


if __name__ == "__main__":
    unittest.main()
