"""Focused Algora advertised-vs-canonical issue/claim regression."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import unittest

from tools.algora_canonical_intake.cli import IntakeError, reconcile

ROOT = Path(__file__).parent


class AlgoraCanonicalIntakeTest(unittest.TestCase):
    def test_stale_board_claims_and_duplicate_issue_fence(self):
        payload = json.loads((ROOT / "example.synthetic.json").read_text(encoding="utf-8"))
        now = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
        report = reconcile(payload, now=now, minimum_usd=Decimal("15"))
        self.assertEqual(report["summary"], {
            "provider_listing_rows": 6,
            "unique_canonical_issues": 5,
            "ready": 1,
            "hold": 2,
            "prune": 2,
        })
        decisions = {d["issue_url"].rsplit("/", 1)[-1]: d for d in report["decisions"]}
        self.assertEqual(decisions["373"]["decision"], "PRUNE")
        self.assertIn("CANONICAL_CLOSED", decisions["373"]["reasons"])
        self.assertEqual(decisions["16"]["decision"], "PRUNE")
        self.assertIn("CANONICAL_NOT_FOUND", decisions["16"]["reasons"])
        self.assertEqual(decisions["272"]["decision"], "HOLD")
        self.assertIn("CLAIM_PR_EXISTS", decisions["272"]["reasons"])
        self.assertEqual(decisions["10"]["decision"], "HOLD")
        self.assertIn("BELOW_MINIMUM_USD", decisions["10"]["reasons"])
        self.assertEqual(decisions["321"]["decision"], "READY_FOR_COORDINATED_TAKE")
        self.assertEqual(decisions["321"]["advertised_max_usd"], "25.00")
        self.assertEqual(decisions["321"]["listing_ids"], ["ex-ready-1", "ex-ready-2"])
        self.assertEqual(len(report["work_orders"]), 1)
        self.assertEqual(report["work_orders"][0]["reward_awarded"], "UNKNOWN")
        self.assertEqual(report["work_orders"][0]["payment_received"], "UNKNOWN")
        self.assertEqual(report, reconcile(payload, now=now))

        payload["provider_observed_at"] = "2026-10-01T00:00:00Z"
        stale = reconcile(payload, now=now)
        self.assertEqual(stale["summary"]["ready"], 0)
        self.assertIn("PROVIDER_SNAPSHOT_STALE",
                      next(d for d in stale["decisions"] if d["issue_url"].endswith("/321"))["reasons"])

        payload["provider_observed_at"] = "2026-10-08T03:55:00Z"
        next(i for i in payload["github_issues"] if i["issue_url"].endswith("/321"))["claim_scan_complete"] = False
        incomplete = reconcile(payload, now=now)
        self.assertEqual(incomplete["summary"]["ready"], 0)
        self.assertIn("CLAIM_SCAN_INCOMPLETE",
                      next(d for d in incomplete["decisions"] if d["issue_url"].endswith("/321"))["reasons"])

        payload["listings"][1]["listing_id"] = payload["listings"][0]["listing_id"]
        with self.assertRaises(IntakeError):
            reconcile(payload, now=now)


if __name__ == "__main__":
    unittest.main()
