from __future__ import annotations

import copy
import unittest

from .fixture import EVALUATED_AT, build_acceptance_batch, build_policy
from .gate import digest, evaluate


def _readdress(case):
    core = copy.deepcopy(case)
    core.pop("event_id", None)
    case["event_id"] = digest(core)
    return case


class PeerInvariantTest(unittest.TestCase):
    def test_stale_source_snapshot_holds_even_when_case_capture_is_fresh(self):
        policy = build_policy()
        batch = build_acceptance_batch()
        case = copy.deepcopy(batch["cases"][0])
        case["source_snapshots"][0]["captured_at"] = "2026-09-13T07:00:00Z"
        _readdress(case)
        one = {
            "schema": batch["schema"],
            "capture_complete": True,
            "captured_at": batch["captured_at"],
            "cases": [case],
        }
        result = evaluate(policy, one, evaluated_at=EVALUATED_AT)
        self.assertIn("SOURCE_SNAPSHOT_STALE", result["manifest"]["rows"][0]["codes"])


if __name__ == "__main__":
    unittest.main()
