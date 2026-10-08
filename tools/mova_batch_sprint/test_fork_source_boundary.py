"""Focused regression: a fork PR must not masquerade as an upstream sponsor claim."""
import unittest
from datetime import datetime, timezone

from plan import plan


class ForkSourceBoundaryTest(unittest.TestCase):
    def row(self, **changes):
        row = {
            "issue_url": "https://github.com/Stellar-PocketPay/pocketpay-sdk/issues/312",
            "platform": "grantfox",
            "funding": "conditional",
            "funding_url": "https://example.test/conditional/312",
            "reward_usd": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "issue_state": "open",
            "eligibility": "eligible",
            "competition": "none",
            "source_state": "ready",
            "claim_state": "unknown",
            "active_owner": None,
        }
        row.update(changes)
        return row

    def batch(self, row):
        return plan({"as_of": datetime.now(timezone.utc).isoformat(), "records": [row]})

    def test_rejects_fork_as_upstream_pr(self):
        with self.assertRaisesRegex(ValueError, "sponsor-repository PR"):
            self.batch(self.row(
                pr_url="https://github.com/woahwhattheheck/pocketpay-sdk/pull/5",
                pr_author="woahwhattheheck",
            ))

    def test_ready_original_fork_remains_publication_not_claim(self):
        result = self.batch(self.row(
            source_pr_url="https://github.com/woahwhattheheck/pocketpay-sdk/pull/5",
            source_pr_author="woahwhattheheck",
        ))
        item = result["work_orders"][0]
        self.assertEqual(item["action"], "PUBLISH_EXISTING")
        self.assertIsNone(item["pr_url"])
        self.assertEqual(item["source_pr_author"], "woahwhattheheck")
        self.assertEqual(result["build_slots_admitted"], 0)

    def test_preserves_foreign_fork_author(self):
        item = self.batch(self.row(
            source_pr_url="https://github.com/tokenjunkielabs/pocketpay-sdk/pull/14",
            source_pr_author="tokenjunkielabs",
        ))["work_orders"][0]
        self.assertEqual(item["action"], "PRESERVE_FOREIGN_PR")

    def test_actual_sponsor_pr_keeps_claim_reconciliation(self):
        item = self.batch(self.row(
            source_state="none",
            pr_url="https://github.com/Stellar-PocketPay/pocketpay-sdk/pull/466",
            pr_author="woahwhattheheck",
        ))["work_orders"][0]
        self.assertEqual(item["action"], "VERIFY_CLAIM")
        self.assertEqual(item["source_state"], "published")

    def test_source_requires_author_and_explicit_state(self):
        with self.assertRaisesRegex(ValueError, "source_pr_author"):
            self.batch(self.row(
                source_pr_url="https://github.com/woahwhattheheck/pocketpay-sdk/pull/5",
            ))
        with self.assertRaisesRegex(ValueError, "explicit building or ready"):
            self.batch(self.row(
                source_state="none",
                source_pr_url="https://github.com/woahwhattheheck/pocketpay-sdk/pull/5",
                source_pr_author="woahwhattheheck",
            ))


if __name__ == "__main__":
    unittest.main()
