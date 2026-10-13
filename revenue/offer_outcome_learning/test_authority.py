from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from revenue.offer_outcome_learning.engine import LearningError, compile_historical, sha256_json, verify_package
from revenue.offer_outcome_learning.test_engine import AT, base_input, h


class AuthorityBoundaryTests(unittest.TestCase):
    def _current_resealed(self):
        raw = base_input()
        package = compile_historical(raw, AT)
        package["payload"]["mode"] = "CURRENT"
        package["receipt_sha256"] = sha256_json(package["payload"])
        return raw, package

    def test_caller_clock_override_cannot_revive_current_package(self):
        raw, package = self._current_resealed()
        with patch(
            "revenue.offer_outcome_learning.engine._utc_now",
            return_value=datetime(2026, 9, 14, 0, 10, 1, tzinfo=timezone.utc),
        ):
            with self.assertRaisesRegex(LearningError, "CALLER_CLOCK_OVERRIDE_FORBIDDEN"):
                verify_package(raw, package, now="2026-09-13T23:40:01Z")

    def test_current_package_uses_process_clock(self):
        raw, package = self._current_resealed()
        with patch(
            "revenue.offer_outcome_learning.engine._utc_now",
            return_value=datetime(2026, 9, 14, 0, 10, 1, tzinfo=timezone.utc),
        ):
            with self.assertRaisesRegex(LearningError, "CURRENT_PACKAGE_STALE"):
                verify_package(raw, package)

    def test_settlement_ref_cannot_fork_across_digests(self):
        raw = base_input()
        confirmed = [e for e in raw["events"] if e["stage"] == "PAYMENT_CONFIRMED"]
        self.assertGreaterEqual(len(confirmed), 2)
        confirmed[1]["settlement_ref"] = confirmed[0]["settlement_ref"]
        confirmed[1]["settlement_sha256"] = h("different-settlement-generation")
        with self.assertRaisesRegex(LearningError, "SETTLEMENT_REF_DIGEST_CONFLICT"):
            compile_historical(raw, AT)

    def test_exact_settlement_replay_still_dedupes_only_by_event_id(self):
        raw = base_input()
        row = next(e for e in raw["events"] if e["stage"] == "PAYMENT_CONFIRMED")
        raw["events"].append(copy.deepcopy(row))
        package = compile_historical(raw, AT)
        self.assertEqual(package["payload"]["event_count"], len(raw["events"]) - 1)


if __name__ == "__main__":
    unittest.main()
