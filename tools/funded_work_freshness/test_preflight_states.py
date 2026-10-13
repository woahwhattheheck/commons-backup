from __future__ import annotations

import unittest

from funded_work_freshness import preflight
from test_support import (
    NOW,
    FakeTransport,
    api,
    candidate,
    evidence_routes,
    html_response,
    open_issue,
    response,
)


class PreflightStateTests(unittest.TestCase):
    def test_board_open_but_canonical_closed_is_stale(self):
        page = "https://algora.io/electron-48191"
        gh = "https://github.com/electron/electron/issues/48191"
        issue = open_issue(gh)
        issue["state"] = "closed"
        endpoint = api("electron", "electron", 48191)
        routes = {
            page: html_response(page, f'<a href="{gh}">open $500 reward</a>'),
            endpoint: response(endpoint, issue),
        }
        transport = FakeTransport(routes)
        receipt = preflight(candidate(page), transport, observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "stale")
        self.assertEqual(receipt["reasons"], ["canonical_state_closed"])
        self.assertFalse(receipt["checks"]["canonical_state_open"])
        self.assertTrue(receipt["checks"]["evidence_complete"])
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(receipt["canonical"]["url"], gh)
        self.assertEqual(receipt["canonical"]["title"], issue["title"])
        self.assertEqual([url for url, _accept in transport.calls], [page, endpoint])

    def test_redirect_to_deleted_canonical_target_is_stale(self):
        page = "https://opire.dev/zeroperl-7"
        gh = "https://github.com/6over3/zeroperl/issues/7"
        routes = {page: html_response(gh, "not found", status=404)}
        receipt = preflight(candidate(page, amount="1500"), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "stale")
        self.assertEqual(receipt["canonical"]["state"], "deleted_or_missing")
        self.assertIn("canonical_target_deleted_or_missing", receipt["reasons"])

    def test_fresh_open_unoccupied_funded_candidate_is_actionable(self):
        page = "https://polar.sh/fresh-1"
        gh = "https://github.com/acme/widget/issues/12"
        routes = {
            page: html_response(page, f'<a href="{gh}">candidate</a>'),
            **evidence_routes("acme", "widget", 12, open_issue(gh)),
        }
        receipt = preflight(candidate(page), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertEqual(receipt["route"], "qualified_for_human_claim_decision")
        self.assertTrue(receipt["checks"]["advertised_amount_supported_by_canonical_evidence"])
        self.assertRegex(receipt["receipt_sha256"], r"^[0-9a-f]{64}$")

    def test_archived_repo_is_stale_without_a_delivery_route(self):
        gh = "https://github.com/acme/widget/issues/12"
        repo_api = "https://api.github.com/repos/acme/widget"
        routes = evidence_routes("acme", "widget", 12, open_issue(gh), archived=True)
        transport = FakeTransport(routes)
        receipt = preflight(candidate(gh, canonical_url=gh), transport, observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "stale")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(receipt["reasons"], ["canonical_repository_archived"])
        self.assertTrue(receipt["canonical"]["repository_archived"])
        self.assertEqual(transport.calls[-1][0], repo_api)

    def test_unknown_repo_archive_flag_fails_closed(self):
        gh = "https://github.com/acme/widget/issues/12"
        repo_api = "https://api.github.com/repos/acme/widget"
        routes = evidence_routes("acme", "widget", 12, open_issue(gh))
        routes[repo_api] = response(repo_api, {"name": "widget"})
        receipt = preflight(
            candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW
        )
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(
            receipt["reasons"], ["canonical_repository_archived_state_missing"]
        )

    def test_unknown_board_requires_canonical_url_before_any_fetch(self):
        page = "https://board.example/reward/1"
        transport = FakeTransport({})
        receipt = preflight(candidate(page), transport, observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(receipt["reasons"], ["candidate_source_requires_canonical_url"])
        self.assertEqual(transport.calls, [])

    def test_unknown_board_with_explicit_canonical_skips_board_fetch(self):
        page = "https://board.example/reward/1"
        gh = "https://github.com/acme/widget/issues/12"
        transport = FakeTransport(evidence_routes("acme", "widget", 12, open_issue(gh)))
        receipt = preflight(
            candidate(page, canonical_url=gh), transport, observed_at=NOW
        )
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertNotIn(page, [url for url, _accept in transport.calls])

    def test_moved_but_live_target_binds_returned_canonical_url(self):
        old = "https://github.com/oldco/widget/issues/9"
        new = "https://github.com/newco/widget/issues/9"
        old_api = api("oldco", "widget", 9)
        routes = {
            old_api: response(old_api, open_issue(new)),
            **{
                key: value
                for key, value in evidence_routes("newco", "widget", 9, open_issue(new)).items()
                if key != api("newco", "widget", 9)
            },
        }
        receipt = preflight(candidate(old, canonical_url=old), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "actionable")
        self.assertTrue(receipt["canonical"]["moved"])
        self.assertEqual(receipt["canonical"]["url"], new)

    def test_rate_limited_canonical_read_is_ambiguous_not_open(self):
        gh = "https://github.com/acme/widget/issues/12"
        endpoint = api("acme", "widget", 12)
        routes = {
            endpoint: response(
                endpoint,
                {"message": "API rate limit exceeded"},
                status=403,
                headers={"x-ratelimit-remaining": "0"},
            )
        }
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "reject")
        self.assertEqual(receipt["reasons"], ["canonical_issue_rate_limited"])

    def test_assignments_claims_and_open_cross_reference_make_candidate_occupied(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh, assignees=[{"login": "maintainer"}])
        comments = [
            {
                "body": "/attempt #12",
                "user": {"login": "solver"},
                "created_at": "2026-09-13T04:00:00Z",
                "updated_at": "2026-09-13T04:00:00Z",
            }
        ]
        timeline = [
            {
                "event": "cross-referenced",
                "source": {
                    "issue": {
                        "html_url": "https://github.com/acme/widget/pull/44",
                        "state": "open",
                        "pull_request": {
                            "url": "https://api.github.com/repos/acme/widget/pulls/44"
                        },
                    }
                },
            }
        ]
        routes = evidence_routes("acme", "widget", 12, issue, comments, timeline)
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "occupied")
        self.assertEqual(receipt["checks"]["assignee_count"], 1)
        self.assertEqual(receipt["checks"]["visible_claim_count"], 1)
        self.assertEqual(receipt["checks"]["active_competing_pr_count"], 1)
        self.assertEqual(
            set(receipt["reasons"]),
            {
                "canonical_issue_assigned",
                "visible_claim_threshold_exceeded",
                "active_competing_pull_requests",
            },
        )

    def test_missing_canonical_amount_support_fails_closed(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(
            gh,
            body="## Acceptance Criteria\n- [ ] deterministic receipt\n\nA reward exists via Algora.",
        )
        routes = evidence_routes("acme", "widget", 12, issue)
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertIn("advertised_amount_not_supported_by_canonical_evidence", receipt["reasons"])

    def test_security_candidate_routes_to_research_only(self):
        gh = "https://github.com/acme/widget/issues/12"
        issue = open_issue(gh, title="Security vulnerability bounty")
        routes = evidence_routes("acme", "widget", 12, issue)
        receipt = preflight(candidate(gh, canonical_url=gh), FakeTransport(routes), observed_at=NOW)
        self.assertEqual(receipt["freshness_status"], "ambiguous")
        self.assertEqual(receipt["route"], "research_only")
        self.assertIn("security_scope_requires_research_only_route", receipt["reasons"])
