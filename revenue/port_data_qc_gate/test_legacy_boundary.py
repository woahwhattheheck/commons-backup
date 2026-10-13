from __future__ import annotations

import unittest
from datetime import timezone

import revenue.port_data_qc_gate._legacy_engine as frozen
from revenue.port_data_qc_gate.test_gate import policy, snapshot


class FrozenEngineAuthorityBoundaryTests(unittest.TestCase):
    def test_direct_current_entry_point_fails_closed(self):
        with self.assertRaises(frozen.GateInputError):
            frozen.evaluate(
                policy(),
                snapshot("2026-09-14T12:00:00Z"),
                evaluated_at="2026-09-14T12:00:01Z",
            )

    def test_retained_explicit_time_replay_is_mechanically_historical(self):
        result = frozen._evaluate_historical_at(
            policy(),
            snapshot("2026-09-14T12:00:00Z"),
            evaluated_at="2026-09-14T12:00:01Z",
        )
        self.assertEqual("PASS", result["receipt"]["decision"])
        self.assertEqual(
            "HISTORICAL_INTEGRITY_ONLY",
            result["receipt"]["temporal_authority"],
        )

    def test_executed_predecessor_namespace_is_not_exported(self):
        self.assertFalse(hasattr(frozen, "_namespace"))
        self.assertFalse(hasattr(frozen, "_source"))

    def test_compatibility_utc_parser_is_local_and_operational(self):
        parsed = frozen._parse_utc("2026-09-14T12:00:00Z", name="probe")
        self.assertEqual(timezone.utc.utcoffset(parsed), parsed.utcoffset())
        with self.assertRaises(frozen.GateInputError):
            frozen._parse_utc("2026-09-14T12:00:00+00:00", name="probe")


if __name__ == "__main__":
    unittest.main()
