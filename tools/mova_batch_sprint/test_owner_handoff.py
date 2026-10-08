"""Focused offline regression for MOVA owner/duplicate-publication fencing.

Run just this check: python tools/mova_batch_sprint/test_owner_handoff.py
No GitHub, Slack or provider API calls.
"""
from datetime import datetime, timedelta, timezone
import unittest

from plan import plan


ISSUE = "https://github.com/example/rewarded-sdk/issues/42"


def record(platform, *, source="none", owner=None, checked_at=None):
    return {
        "issue_url": ISSUE,
        "platform": platform,
        "funding": "provider_listed",
        "funding_url": "https://%s.example.test/bounties/42" % platform,
        "eligibility": "eligible",
        "issue_state": "open",
        "source_state": source,
        "competition": "none",
        "claim_state": "not_submitted",
        "active_owner": owner,
        "reward_usd": 50,
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
    }


def actions(*records):
    manifest = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "records": list(records),
    }
    return plan(manifest, actor="woahwhattheheck")


class OwnerCollisionRegression(unittest.TestCase):
    def test_ready_source_respects_active_publication_owner(self):
        busy = actions(record("algora", source="ready", owner="publisher-1"))
        self.assertEqual(busy["work_orders"][0]["action"], "OWNER_CONTINUES")
        self.assertEqual(busy["build_slots_admitted"], 0)

        released = actions(record("algora", source="ready"))
        self.assertEqual(released["work_orders"][0]["action"], "PUBLISH_EXISTING")

    def test_shared_issue_with_active_builder_cannot_rebuild(self):
        for state in ("building", "ready", "none"):
            with self.subTest(source_state=state):
                batch = actions(
                    record("grantfox", source=state, owner="engineer-1"),
                    record("algora"),
                )
                chosen = {r["platform"]: r["action"] for r in batch["work_orders"]}
                self.assertEqual(chosen["grantfox"], "OWNER_CONTINUES")
                self.assertEqual(chosen["algora"], "RECONCILE_SHARED_SOURCE")
                self.assertEqual(batch["build_slots_admitted"], 0)

    def test_stale_known_upstream_pr_blocks_new_build(self):
        stale = record(
            "grantfox",
            source="published",
            checked_at=(datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
        )
        stale["pr_url"] = "https://github.com/example/rewarded-sdk/pull/12"
        stale["pr_author"] = "woahwhattheheck"
        batch = actions(stale, record("algora"))
        chosen = {r["platform"]: r["action"] for r in batch["work_orders"]}
        self.assertEqual(chosen["grantfox"], "REFRESH_CANONICAL")
        self.assertEqual(chosen["algora"], "RECONCILE_SHARED_PR")
        self.assertEqual(batch["build_slots_admitted"], 0)


if __name__ == "__main__":
    unittest.main()
