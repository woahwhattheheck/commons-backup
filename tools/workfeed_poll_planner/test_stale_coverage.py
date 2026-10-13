from __future__ import annotations

import copy
import unittest

from .core import compile_plan
from .demo import sample_packet


class StaleCoveredSnapshotTest(unittest.TestCase):
    def test_coverage_expires_without_bypassing_backoff(self) -> None:
        fresh = sample_packet()
        fresh["surfaces"] = [fresh["surfaces"][0]]
        fresh["evidence_ttl_seconds"] = 60
        surface = fresh["surfaces"][0]
        surface["covered_by_generation"] = surface["snapshot_generation"]

        fresh_row = compile_plan(fresh)["surfaces"][0]
        self.assertEqual(fresh_row["decision"], "SKIP_REDUNDANT")

        expired = copy.deepcopy(fresh)
        expired["evaluation_utc"] = "2026-09-17T23:21:10Z"
        expired_row = compile_plan(expired)["surfaces"][0]
        self.assertEqual(expired_row["decision"], "POLL_NOW")
        self.assertTrue(expired_row["evidence_stale"])

        throttled = copy.deepcopy(expired)
        throttled_surface = throttled["surfaces"][0]
        throttled_surface["last_throttle_utc"] = "2026-09-17T23:19:57Z"
        throttled_surface["retry_after_seconds"] = 120
        throttled_surface["consecutive_throttles"] = 1
        throttle_row = compile_plan(throttled)["surfaces"][0]
        self.assertEqual(throttle_row["decision"], "HOLD_THROTTLED")
        self.assertFalse(throttle_row["request_allocated"])


if __name__ == "__main__":
    unittest.main()
