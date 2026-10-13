#!/usr/bin/env python3
"""Focused BountyHub listing-to-PR reconciliation cases; no provider calls."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bounty_portal_registration import AuditError, SCHEMA, reconcile

NOW = datetime(2026, 10, 8, 3, 55, tzinfo=timezone.utc)
A = "a0aa0aa0-a0aa-40aa-80aa-a0aa0aa0a0aa"
B = "b0bb0bb0-b0bb-40bb-80bb-b0bb0bb0b0bb"


def sample(listing=A):
    return {
        "schema": SCHEMA,
        "owned_prs": [{
            "provider": "BountyHub",
            "issue_url": "https://github.com/example/product/issues/17",
            "pr_url": "https://github.com/example/product/pull/22",
            "claimant": "OriginalContributor",
            "bounty_listing_id": listing,
            "head_sha": "a" * 40,
            "github_state": "open",
            "github_submitted_at": "2026-10-08T03:40:00Z",
            "github_checked_at": "2026-10-08T03:50:00Z",
        }],
        "provider_snapshots": [{
            "provider": "BountyHub",
            "issue_url": "https://github.com/example/product/issues/17",
            "source_url": "https://api.bountyhub.dev/api/bounties/" + A,
            "observed_at": "2026-10-08T03:51:00Z",
            "complete": True,
            "submissions": [],
        }],
    }


def audit(value):
    return reconcile(value, NOW, timedelta(hours=1))


class ListingIdentityTests(unittest.TestCase):
    def test_exact_listing_produces_action_on_complete_missing_claim(self):
        result = audit(sample())
        self.assertEqual(result["registration_gap_count"], 1)
        self.assertEqual(result["results"][0]["status"], "GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED")
        self.assertEqual(result["action_items"][0]["action"], "SUBMIT_CLAIM_FOR_PUBLISHED_PR")

    def test_other_listing_cannot_authorize_submission(self):
        result = audit(sample(B))
        self.assertEqual(result["registration_gap_count"], 0)
        self.assertEqual(result["results"][0]["status"], "UNKNOWN")
        self.assertIn("UUID", result["results"][0]["reason"])

    def test_missing_listing_fails_closed(self):
        data = sample()
        del data["owned_prs"][0]["bounty_listing_id"]
        result = audit(data)
        self.assertEqual(result["registration_gap_count"], 0)
        self.assertEqual(result["results"][0]["status"], "UNKNOWN")

    def test_own_pr_registered_is_not_missing(self):
        data = sample()
        data["provider_snapshots"][0]["submissions"] = [{
            "pr_url": "https://github.com/example/product/pull/22",
            "claimant": "originalcontributor",
            "state": "REGISTERED",
        }]
        result = audit(data)
        self.assertEqual(result["registration_gap_count"], 0)
        self.assertEqual(result["results"][0]["status"], "PORTAL_REGISTERED_UNAWARDED")

    def test_invalid_listing_id_is_rejected(self):
        with self.assertRaisesRegex(AuditError, "bounty_listing_id"):
            audit(sample("not-a-uuid"))

    def test_issuehunt_legacy_behavior_and_ids_preserved(self):
        data = sample()
        owned = data["owned_prs"][0]
        snapshot = data["provider_snapshots"][0]
        owned["provider"] = "IssueHunt"
        del owned["bounty_listing_id"]
        snapshot["provider"] = "IssueHunt"
        snapshot["source_url"] = "https://oss.issuehunt.io/r/example/product/issues/17"
        result = audit(data)
        self.assertEqual(result["registration_gap_count"], 1)
        self.assertEqual(result["action_items"][0]["action"], "VERIFY_AND_REGISTER_EXACT_PR")

    def test_relisting_changes_stable_action_identity(self):
        first = sample(A)
        second = sample(B)
        second["provider_snapshots"][0]["source_url"] = (
            "https://api.bountyhub.dev/api/bounties/" + B
        )
        self.assertNotEqual(
            audit(first)["results"][0]["operation_id"],
            audit(second)["results"][0]["operation_id"],
        )


if __name__ == "__main__":
    unittest.main()
