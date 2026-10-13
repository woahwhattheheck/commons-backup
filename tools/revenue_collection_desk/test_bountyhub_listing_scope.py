"""Focused regression: separate BountyHub listings can fund one GitHub issue.

Run: python -m unittest tools.revenue_collection_desk.test_bountyhub_listing_scope
No provider/network or payment writes.
"""
from datetime import datetime, timedelta, timezone
import unittest

from tools.revenue_collection_desk.portal_registration import SCHEMA, audit

ISSUE = "https://github.com/microg/gmscore/issues/580"
PR = "https://github.com/microg/gmscore/pull/3845"
LISTING_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
LISTING_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PAGE_A = f"https://www.bountyhub.dev/en/bounty/view/{LISTING_A}/cast"
API_A = f"https://api.bountyhub.dev/api/bounties/{LISTING_A}"
PAGE_B = f"https://www.bountyhub.dev/en/bounty/view/{LISTING_B}/cast"


def fixture(scoped):
    now = datetime.now(timezone.utc)
    stamp = lambda x: x.isoformat()
    common = {
        "provider": "bountyhub",
        "repository": "microg/GmsCore",
        "issue": 580,
        "claimant": "woahwhattheheck",
        "pr_url": PR,
        "head_sha": "a" * 40,
        "github_state": "open",
        "github_submitted_at": stamp(now - timedelta(minutes=3)),
        "github_checked_at": stamp(now - timedelta(seconds=10)),
    }
    submissions = [
        dict(common, portal_source_url=API_A),
        dict(common, portal_source_url=PAGE_B),
    ] if scoped else [common]
    common_snapshot = {
        "provider": "bountyhub", "repository": "microg/GmsCore",
        "issue": 580, "observed_at": stamp(now - timedelta(seconds=5)),
        "source_issue_url": ISSUE, "complete": True,
    }
    a = dict(common_snapshot, source_url=PAGE_A,
             claims=[{"pr_url": PR, "claimant": "woahwhattheheck",
                      "awarded": None, "is_paid": None}])
    b = dict(common_snapshot, source_url=PAGE_B, claims=[])
    return {"schema": SCHEMA, "evaluated_at": stamp(now),
            "submissions": submissions, "portal_snapshots": [a, b]}


class DualBountyListingTests(unittest.TestCase):
    def test_unscoped_duplicate_listing_never_dispatches_false_registration(self):
        result = audit(fixture(scoped=False))
        self.assertEqual("UNKNOWN", result["rows"][0]["status"])
        self.assertEqual("multiple_provider_listings_require_source_binding",
                         result["rows"][0]["reason"])
        self.assertEqual([], result["actionable_registration_gaps"])

    def test_explicit_listing_binding_preserves_independent_registration(self):
        result = audit(fixture(scoped=True))
        by_listing = {row["portal_listing_id"]: row for row in result["rows"]}
        self.assertEqual(2, len(by_listing))
        self.assertEqual("PORTAL_REGISTERED_AWARD_UNKNOWN", by_listing[LISTING_A]["status"])
        self.assertEqual("GITHUB_SUBMITTED_PORTAL_NOT_REGISTERED", by_listing[LISTING_B]["status"])
        self.assertNotEqual(by_listing[LISTING_A]["operation_id"],
                            by_listing[LISTING_B]["operation_id"])
        self.assertEqual(1, len(result["actionable_registration_gaps"]))
        self.assertEqual(PAGE_B, result["actionable_registration_gaps"][0]["source_url"])
        self.assertFalse(any(r["cash_settlement_verified"] for r in result["rows"]))


if __name__ == "__main__":
    unittest.main()
