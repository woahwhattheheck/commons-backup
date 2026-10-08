"""Focused source-carrier and ownership fences for the MOVA publisher lane."""

from datetime import datetime, timezone
import unittest

from tools.mova_batch_sprint.plan import action, normalize


NOW = datetime(2026, 10, 8, 5, 52, tzinfo=timezone.utc)


def candidate(**overrides):
    record = {
        "issue_url": "https://github.com/example/project/issues/42",
        "platform": "issuehunt",
        "funding": "escrow_verified",
        "funding_url": "https://oss.issuehunt.io/r/example/project/issues/42",
        "reward_usd": 100,
        "checked_at": NOW.isoformat(),
        "issue_state": "open",
        "eligibility": "eligible",
        "competition": "none",
        "source_state": "ready",
        "claim_state": "unknown",
    }
    record.update(overrides)
    return normalize(record, NOW, 6)


class ReadySourceReferenceTests(unittest.TestCase):
    def test_released_ready_source_without_carrier_cannot_publish(self):
        order, reason = action(candidate(), 15, "woahwhattheheck")
        self.assertEqual(order, "SOURCE_REFERENCE_HOLD")
        self.assertIn("fork PR", reason)

    def test_named_active_owner_still_continues_even_without_carrier(self):
        order, _ = action(candidate(active_owner="publisher-in-progress"), 15, "woahwhattheheck")
        self.assertEqual(order, "OWNER_CONTINUES")

    def test_matching_original_author_ready_carrier_can_publish(self):
        item = candidate(
            source_pr_url="https://github.com/woahwhattheheck/project/pull/7",
            source_pr_author="woahwhattheheck",
        )
        order, _ = action(item, 15, "woahwhattheheck")
        self.assertEqual(order, "PUBLISH_EXISTING")

    def test_foreign_carrier_remains_owned_by_its_author(self):
        item = candidate(
            source_pr_url="https://github.com/someoneelse/project/pull/7",
            source_pr_author="someoneelse",
        )
        order, _ = action(item, 15, "woahwhattheheck")
        self.assertEqual(order, "PRESERVE_FOREIGN_PR")

    def test_portal_claim_without_upstream_pr_still_held(self):
        order, _ = action(candidate(claim_state="submitted"), 15, "woahwhattheheck")
        self.assertEqual(order, "CLAIM_SOURCE_HOLD")


if __name__ == "__main__":
    unittest.main()
