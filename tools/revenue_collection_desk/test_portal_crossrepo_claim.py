"""Focused cross-repository portal-claim matching regressions (offline)."""
from __future__ import annotations

import copy
import unittest

from .core import ContractError
from .portal_registration import SCHEMA, audit


class PortalCrossRepoClaimTests(unittest.TestCase):
    def evidence(self, provider: str) -> dict:
        issue_url = "https://github.com/sponsor/funded/issues/17"
        pr_url = "https://github.com/implementer/delivery/pull/42"
        portal_url = (
            "https://oss.issuehunt.io/r/sponsor/funded/issues/17"
            if provider == "issuehunt"
            else "https://api.bountyhub.dev/api/bounties/12345678-1234-1234-1234-123456789abc"
        )
        snapshot = {
            "provider": provider,
            "repository": "sponsor/funded",
            "issue": 17,
            "source_url": portal_url,
            "observed_at": "2026-10-08T03:51:10Z",
            "complete": True,
            "claims": [
                {"pr_url": pr_url, "claimant": "original-author", "awarded": False, "is_paid": False}
            ],
        }
        if provider == "bountyhub":
            snapshot["source_issue_url"] = issue_url
        return {
            "schema": SCHEMA,
            "evaluated_at": "2026-10-08T03:51:15Z",
            "submissions": [
                {
                    "provider": provider,
                    "repository": "sponsor/funded",
                    "issue": 17,
                    "claimant": "original-author",
                    "pr_url": pr_url,
                    "submission_repository": "implementer/delivery",
                    "head_sha": "a" * 40,
                    "github_state": "open",
                    "github_submitted_at": "2026-10-08T03:40:00Z",
                    "github_checked_at": "2026-10-08T03:51:00Z",
                }
            ],
            "portal_snapshots": [snapshot],
        }

    def test_registered_cross_repo_claim_matches_exact_original_author(self):
        for provider in ("issuehunt", "bountyhub"):
            with self.subTest(provider=provider):
                report = audit(self.evidence(provider))
                self.assertEqual(report["rows"][0]["status"], "PORTAL_REGISTERED_UNAWARDED")
                self.assertEqual(report["rows"][0]["reason"], "portal_registration_confirmed")
                self.assertEqual(report["actionable_registration_gaps"], [])

    def test_cross_repo_different_claimant_never_registers_original_author(self):
        data = self.evidence("issuehunt")
        data["portal_snapshots"][0]["claims"][0]["claimant"] = "someone-else"
        report = audit(data)
        self.assertEqual(report["rows"][0]["status"], "UNKNOWN")
        self.assertEqual(report["rows"][0]["reason"], "portal_pr_author_mismatch")
        self.assertEqual(report["actionable_registration_gaps"], [])

    def test_cross_repo_requires_explicit_github_submission_repository(self):
        data = copy.deepcopy(self.evidence("issuehunt"))
        del data["submissions"][0]["submission_repository"]
        with self.assertRaises(ContractError):
            audit(data)


if __name__ == "__main__":
    unittest.main()
