"""Focused offline MOVA incorporation of the existing Slack TAKE preflight.

No provider, GitHub, Slack or payout calls. One overlap and one stale-feed
scenario protect source coordination without changing paid claim decisions.
"""
from datetime import datetime, timezone
import time
import unittest

from plan import annotate_take_advisories, plan, render_slack

PR = "https://github.com/example/rewarded-sdk/pull/12"
ISSUE = "https://github.com/example/rewarded-sdk/issues/42"
PATH = "src/vault/intents.ts"


def planned_batch():
    now = datetime.now(timezone.utc).isoformat()
    return plan({"as_of": now, "records": [{
        "issue_url": ISSUE, "platform": "grantfox",
        "funding": "provider_listed",
        "funding_url": "https://grantfox.example.test/bounties/42",
        "reward_usd": 90, "checked_at": now,
        "issue_state": "open", "eligibility": "eligible",
        "source_state": "published", "competition": "ours",
        "claim_state": "unknown", "pr_url": PR,
        "pr_author": "woahwhattheheck",
        "take_paths": [PATH], "take_head": "deadbeef",
        "take_kind": "source",
    }]}, actor="woahwhattheheck")


def slack_take(ts):
    return [{"ts": str(ts - 3), "user": "peer-1",
             "channel": "bug-bounty",
             "text": ("TAKE · OTHER-PAID-PR-OPERATION-42 · "
                      "sponsor PR " + PR + " HEAD deadbeef " + PATH)}]


class PlannerTakeAdvisoryTests(unittest.TestCase):
    def test_live_same_head_overlap_preserves_payout_routing_and_surfaces_peer(self):
        clock = time.time()
        batch = planned_batch()
        prior_action = batch["work_orders"][0]["action"]
        annotate_take_advisories(batch, slack_take(clock), as_of_ts=clock)
        item = batch["work_orders"][0]
        self.assertEqual(item["action"], prior_action)
        self.assertEqual(item["action"], "VERIFY_CLAIM")
        self.assertEqual(item["take_advisory"]["status"], "COORDINATE_SOURCE")
        self.assertTrue(item["take_advisory"]["peers"][0]["same_head"])
        self.assertEqual(item["take_advisory"]["peers"][0]["overlap_paths"], [PATH])
        text = render_slack(batch)
        self.assertIn("take_preflight | status=COORDINATE_SOURCE", text)
        self.assertIn("active_take=OTHER-PAID-PR-OPERATION-42", text)
        self.assertIn("head=deadbeef", text)
        self.assertIn("scope=" + PATH, text)
        self.assertIn("pr_url=" + PR, text)

    def test_stale_snapshot_requires_refresh_and_preserves_action(self):
        clock = time.time()
        batch = planned_batch()
        annotate_take_advisories(batch, slack_take(clock - 3600), as_of_ts=clock)
        item = batch["work_orders"][0]
        self.assertEqual(item["take_advisory"]["status"], "REFRESH_FEED")
        self.assertEqual(item["action"], "VERIFY_CLAIM")
        self.assertIn("take_preflight | status=REFRESH_FEED", render_slack(batch))

    def test_disjoint_known_path_allows_parallel_coordination_without_owner_gate(self):
        clock = time.time()
        batch = planned_batch()
        batch["work_orders"][0]["take_paths"] = ["docs/README.md"]
        annotate_take_advisories(batch, slack_take(clock), as_of_ts=clock)
        item = batch["work_orders"][0]
        self.assertEqual(item["take_advisory"]["status"], "PARALLEL_SCOPE_ADVISORY")
        self.assertEqual(item["action"], "VERIFY_CLAIM")


if __name__ == "__main__":
    unittest.main()
