from __future__ import annotations

import unittest

from constants import GITHUB_ITEM_RE
from errors import EvidenceError
from funded_work_freshness import preflight
from github_evidence import github_urls, resolve_candidate
from test_support import NOW, FakeTransport, candidate, evidence_routes, open_issue


class GithubUrlBoundaryTests(unittest.TestCase):
    def test_identifier_suffixes_never_bind_issue_prefix(self):
        base = "https://github.com/acme/widget/issues/42"
        for suffix in ("abc", "_a", "deadbeef", "px"):
            bad = base + suffix
            with self.subTest(bad=bad):
                self.assertIsNone(GITHUB_ITEM_RE.fullmatch(bad))
                self.assertEqual(github_urls(f"see {bad} now"), [])
                transport = FakeTransport({})
                with self.assertRaises(EvidenceError) as caught:
                    resolve_candidate(candidate(bad), transport)
                self.assertEqual(
                    caught.exception.code, "candidate_source_requires_canonical_url"
                )
                self.assertEqual(transport.calls, [])

    def test_legitimate_continuations_and_punctuation_still_bind(self):
        base = "https://github.com/acme/widget/issues/42"
        continuations = (
            "#issuecomment-123",
            "?notification_referrer_id=1",
            "/comments",
        )
        for continuation in continuations:
            url = base + continuation
            with self.subTest(url=url):
                self.assertIsNotNone(GITHUB_ITEM_RE.fullmatch(url))
                self.assertEqual(github_urls(url), [base])
        self.assertEqual(github_urls(f"See {base}."), [base])


class FundingAuthorityTests(unittest.TestCase):
    def test_external_issue_author_cannot_self_assert_funding_authority(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            author_login="external-reporter",
            author_association="NONE",
        )
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertFalse(receipt["checks"]["sponsor_mechanism_present"])
        self.assertFalse(
            receipt["checks"]["advertised_amount_supported_by_canonical_evidence"]
        )
        self.assertFalse(receipt["checks"]["acceptance_criteria_reachable"])
        self.assertIn("canonical_sponsor_mechanism_not_found", receipt["reasons"])

    def test_external_acceptance_prose_is_not_funding_evidence(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            body="## Acceptance Criteria\n- [ ] reporter-authored scope",
            author_login="external-reporter",
            author_association="CONTRIBUTOR",
        )
        comments = [
            {
                "body": "Reward: $500 via Algora",
                "user": {"login": "algora-pbc[bot]"},
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
        self.assertTrue(receipt["checks"]["sponsor_mechanism_present"])
        self.assertTrue(
            receipt["checks"]["advertised_amount_supported_by_canonical_evidence"]
        )
        self.assertFalse(receipt["checks"]["acceptance_criteria_reachable"])
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertIn("acceptance_criteria_not_reachable", receipt["reasons"])

    def test_allowlisted_sponsor_bot_can_supply_complete_funding_evidence(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            body="Reporter-authored technical context only.",
            author_login="external-reporter",
            author_association="NONE",
        )
        comments = [
            {
                "body": (
                    "## Acceptance Criteria\n"
                    "- [ ] deterministic receipt\n\n"
                    "Reward: $500 via Algora"
                ),
                "user": {"login": "algora-pbc[bot]"},
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
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")

    def test_member_issue_body_remains_authoritative(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            author_login="repo-member",
            author_association="MEMBER",
        )
        receipt = preflight(
            candidate(gh, canonical_url=gh),
            FakeTransport(evidence_routes("acme", "widget", 12, issue)),
            observed_at=NOW,
        )
        self.assertEqual(receipt["freshness_status"], "actionable")

    def test_external_issue_security_text_remains_fail_closed(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            title="Security vulnerability bounty",
            body="Reporter-authored security scope.",
            author_login="external-reporter",
            author_association="NONE",
        )
        comments = [
            {
                "body": (
                    "## Acceptance Criteria\n"
                    "- [ ] deterministic receipt\n\n"
                    "Reward: $500 via Algora"
                ),
                "user": {"login": "algora-pbc[bot]"},
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
        self.assertTrue(receipt["checks"]["security_sensitive"])
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "research_only")
        self.assertIn(
            "security_scope_requires_research_only_route", receipt["reasons"]
        )


if __name__ == "__main__":
    unittest.main()
