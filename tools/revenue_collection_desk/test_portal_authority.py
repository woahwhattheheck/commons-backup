"""Focused, deterministic provider-authority cases for portal reconciliation."""
from __future__ import annotations

from copy import deepcopy
import unittest

from .core import ContractError
from .portal_registration import SCHEMA, audit


def case(provider="issuehunt"):
    repo = "example/project"
    source = (
        f"https://oss.issuehunt.io/r/{repo}/issues/25"
        if provider == "issuehunt" else
        "https://api.bountyhub.dev/api/bounties/521afa31-6c6f-4d2c-becc-c6b14318d2b4"
    )
    return {
        "schema": SCHEMA,
        "evaluated_at": "2026-10-08T03:50:00Z",
        "submissions": [{
            "provider": provider, "repository": repo, "issue": 25,
            "claimant": "woahwhattheheck",
            "pr_url": "https://github.com/example/project/pull/9",
            "head_sha": "a" * 40, "github_state": "open",
            "github_submitted_at": "2026-10-08T03:00:00Z",
            "github_checked_at": "2026-10-08T03:49:00Z",
        }],
        "portal_snapshots": [{
            "provider": provider, "repository": repo, "issue": 25,
            "source_url": source, "observed_at": "2026-10-08T03:48:00Z",
            "complete": True, "claims": [],
        }],
    }


class PortalAuthorityTest(unittest.TestCase):
    def test_fresh_issuehunt_absence_is_actionable(self):
        got = audit(case())
        self.assertEqual(got["rows"][0]["status"], "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED")
        self.assertEqual(len(got["actionable_registration_gaps"]), 1)

    def test_stale_snapshot_cannot_make_missing_claim_actionable(self):
        data = case()
        data["portal_snapshots"][0]["observed_at"] = "2026-10-07T23:00:00Z"
        self.assertEqual(audit(data)["rows"][0]["reason"], "portal_read_stale_or_future")
        self.assertFalse(audit(data)["actionable_registration_gaps"])

    def test_bountyhub_requires_captured_exact_issue_binding(self):
        data = case("bountyhub")
        self.assertEqual(audit(data)["rows"][0]["reason"], "bountyhub_listing_missing_exact_issue_binding")
        data["portal_snapshots"][0]["source_issue_url"] = "https://github.com/example/project/issues/25"
        self.assertEqual(audit(data)["rows"][0]["status"], "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED")
        data["portal_snapshots"][0]["source_issue_url"] = "https://github.com/example/other/issues/25"
        with self.assertRaises(ContractError):
            audit(data)

    def test_cross_repo_pr_is_matched_by_exact_url_and_owner(self):
        data = case()
        data["submissions"][0]["submission_repository"] = "example/other"
        data["submissions"][0]["pr_url"] = "https://github.com/example/other/pull/9"
        data["portal_snapshots"][0]["claims"] = [{
            "claimant": "woahwhattheheck", "pr_url": "https://github.com/example/other/pull/9",
            "awarded": None, "is_paid": None,
        }]
        got = audit(data)
        self.assertEqual(got["rows"][0]["status"], "PORTAL_REGISTERED_AWARD_UNKNOWN")
        self.assertEqual(got["actionable_registration_gaps"], [])

    def test_missing_clock_and_future_head_cannot_create_action(self):
        data = case()
        del data["evaluated_at"]
        self.assertEqual(audit(data)["rows"][0]["status"], "UNKNOWN")
        data["evaluated_at"] = "2026-10-08T03:50:00Z"
        data["submissions"][0]["github_checked_at"] = "2026-10-08T03:51:00Z"
        self.assertEqual(audit(data)["rows"][0]["reason"], "github_read_stale_or_future")


if __name__ == "__main__":
    unittest.main()
