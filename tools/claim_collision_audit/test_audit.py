"""Focused stdlib check for idempotent original PR readback.

Run only: python -m unittest tools.claim_collision_audit.test_audit
"""
import unittest
from datetime import datetime, timedelta, timezone

from tools.claim_collision_audit.audit import audit, canonical_issue, slack_report


ISSUE_URL = "https://github.com/Example/Sponsor/issues/42"
ISSUE_KEY = canonical_issue(ISSUE_URL)
ORIGINAL_PR = "https://github.com/Example/Sponsor/pull/19"
OTHER_PR = "https://github.com/Example/Sponsor/pull/20"


class PublicationIdempotencyTest(unittest.TestCase):
    def test_same_sponsor_pr_recheck_is_not_a_second_publication(self):
        now = datetime(2026, 10, 8, 6, 30, tzinfo=timezone.utc)

        def event(kind, idx, **extras):
            at = now - timedelta(minutes=5 - idx)
            return {
                "data": {
                    "event": kind, "at": at.isoformat(),
                    "issue_url": ISSUE_URL, "session": "owner-woah",
                    "operation_id": f"receipt-{idx}", **extras
                },
                "kind": kind, "issue": ISSUE_KEY,
                "session": "owner-woah", "at": at, "line": idx
            }

        rows = [
            event("TAKE", 1, lease_seconds=900),
            event("PUBLISH", 2, pr_url=ORIGINAL_PR),
            event("PUBLISH", 3, pr_url=ORIGINAL_PR),
            event("PUBLISH", 4, pr_url=OTHER_PR)
        ]
        result = audit(rows, [], now, ttl_seconds=900,
                       max_head_age_seconds=300)
        info = result["issues"][ISSUE_KEY]
        self.assertEqual(info["publishes_attempted"], 3)
        self.assertEqual(info["publishes_confirmed"], 1)
        self.assertEqual(info["publication_rechecks"], 1)
        self.assertEqual(info["collisions"], 1)
        self.assertEqual(info["sponsor_pr"], "example/sponsor#19")
        self.assertEqual(result["summary"]["publication_rechecks"], 1)
        self.assertEqual(
            [entry["code"] for entry in result["anomalies"]],
            ["DUPLICATE_SPONSOR_PR"]
        )
        self.assertIn("Existing sponsor PR rechecks suppressed: 1",
                      slack_report(result))


if __name__ == "__main__":
    unittest.main()
