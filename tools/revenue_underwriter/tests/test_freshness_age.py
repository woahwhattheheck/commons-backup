from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from underwriter import Config, underwrite  # noqa: E402
from tests.test_underwriter import NOW, packet, receipt_hash  # noqa: E402


class FreshnessAgeTests(unittest.TestCase):
    def test_old_actionable_open_snapshot_rejects_with_fresh_payout_history(self):
        value = packet()
        freshness = value["freshness_receipt"]
        freshness["generated_at"] = "2026-09-12T07:29:59Z"
        freshness["receipt_sha256"] = receipt_hash(freshness)

        result = underwrite(value, observed_at=NOW)

        self.assertEqual(result["disposition"], "reject")
        self.assertIn("freshness_observation_stale", result["reasons"])
        self.assertNotIn("payout_history_stale", result["reasons"])

    def test_exact_freshness_horizon_remains_admissible(self):
        value = packet()
        freshness = value["freshness_receipt"]
        freshness["generated_at"] = "2026-09-12T07:30:00Z"
        freshness["receipt_sha256"] = receipt_hash(freshness)

        result = underwrite(value, observed_at=NOW)

        self.assertEqual(result["disposition"], "pursue")
        self.assertNotIn("freshness_observation_stale", result["reasons"])

    def test_custom_freshness_horizon_is_enforced_independently(self):
        value = packet()
        freshness = value["freshness_receipt"]
        freshness["generated_at"] = "2026-09-13T05:30:00Z"
        freshness["receipt_sha256"] = receipt_hash(freshness)

        result = underwrite(
            value,
            observed_at=NOW,
            config=Config(max_freshness_age_hours=1),
        )

        self.assertEqual(result["disposition"], "reject")
        self.assertIn("freshness_observation_stale", result["reasons"])
        self.assertNotIn("payout_history_stale", result["reasons"])


if __name__ == "__main__":
    unittest.main()
