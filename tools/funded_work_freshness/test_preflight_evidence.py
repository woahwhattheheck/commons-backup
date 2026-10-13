from __future__ import annotations

import unittest

from evaluation import amount_supported
from funded_work_freshness import preflight
from test_support import NOW, FakeTransport, api, candidate, evidence_routes, open_issue, response


class PreflightEvidenceTests(unittest.TestCase):
    def test_untrusted_comment_cannot_manufacture_funding_or_acceptance(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh, body="Please investigate this behavior.")
        issue["user"] = {"login": "maintainer"}
        comments = [
            {
                "body": "## Acceptance Criteria\n- [ ] ship it\n\nBounty: $500 via Algora",
                "user": {"login": "random-solver"},
                "author_association": "NONE",
                "created_at": "2026-09-13T04:00:00Z",
            }
        ]
        routes = evidence_routes("acme", "widget", 12, issue, comments, [])
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertIn("canonical_sponsor_mechanism_not_found", receipt["reasons"])
        self.assertFalse(receipt["checks"]["acceptance_criteria_reachable"])

    def test_trusted_maintainer_comment_can_supply_current_terms(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh, body="Terms are maintained below.")
        issue["user"] = {"login": "reporter"}
        comments = [
            {
                "body": "## Acceptance Criteria\n- [ ] deterministic receipt\n\nReward: $500 via Algora",
                "user": {"login": "maintainer"},
                "author_association": "MEMBER",
                "created_at": "2026-09-13T04:00:00Z",
            }
        ]
        routes = evidence_routes("acme", "widget", 12, issue, comments, [])
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "actionable")

    def test_amount_evidence_requires_exact_numeric_token(self):
        self.assertTrue(amount_supported("Reward: $500.00 via Algora", "500", "USD"))
        self.assertTrue(amount_supported("Reward: 500 USD via Algora", "500", "USD"))
        self.assertFalse(amount_supported("Reward: $5000 via Algora", "500", "USD"))
        self.assertFalse(amount_supported("Reward: $50 via Algora", "5", "USD"))

    def test_security_label_routes_to_research_only(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh, labels=[{"name": "security"}])
        routes = evidence_routes("acme", "widget", 12, issue)
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["route"], "research_only")
        self.assertTrue(receipt["checks"]["security_sensitive"])

    def test_future_activity_timestamp_is_ambiguous(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh)
        issue["updated_at"] = "2026-09-14T05:00:00Z"
        routes = evidence_routes("acme", "widget", 12, issue)
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertIn("substantive_activity_timestamp_in_future", receipt["reasons"])

    def test_receipt_is_deterministic_for_same_evidence_time(self):
        gh = "https://github.com/acme/widget/issues/12"
        first = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, open_issue(gh))),
            observed_at=NOW,
        )
        second = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, open_issue(gh))),
            observed_at=NOW,
        )
        self.assertEqual(first, second)

    def test_comment_pagination_is_followed_before_qualification(self):
        gh = "https://github.com/acme/widget/issues/12"
        base = api("acme", "widget", 12)
        comments_2 = f"{base}/comments?per_page=100&page=2"
        routes = {
            base: response(base, open_issue(gh)),
            f"{base}/comments?per_page=100": response(
                f"{base}/comments?per_page=100",
                [],
                headers={"link": f'<{comments_2}>; rel="next"'},
            ),
            comments_2: response(
                comments_2,
                [
                    {
                        "body": "/claim",
                        "user": {"login": "page-two-solver"},
                        "created_at": "2026-09-13T04:00:00Z",
                    }
                ],
            ),
            f"{base}/timeline?per_page=100": response(
                f"{base}/timeline?per_page=100", []
            ),
        }
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "occupied")
        self.assertEqual(receipt["checks"]["visible_claimants"], ["page-two-solver"])
