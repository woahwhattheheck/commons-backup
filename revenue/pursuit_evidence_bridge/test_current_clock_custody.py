"""Security regression for process-owned current UTC in the pursuit bridge."""
from __future__ import annotations

import json
import unittest
from datetime import datetime as RealDateTime, timezone as RealTimezone
from pathlib import Path

import revenue.pursuit_evidence_bridge.bridge as bridge_module


class CurrentClockCustodyTests(unittest.TestCase):
    def test_public_current_clock_ignores_ordinary_module_rebinding(self):
        """The predecessor could be backdated by rebinding module clock globals."""
        repo = Path(bridge_module.__file__).resolve().parents[2]
        source = json.loads((repo / "opportunities/jersey_connecting_health_cdr_openehr_dn827803/sources.json").read_text())
        manifest = json.loads((repo / "opportunities/jersey_connecting_health_cdr_openehr_dn827803/fixtures/public_hold.json").read_text())

        fake_now = RealDateTime(2001, 1, 1, 0, 0, 0, tzinfo=RealTimezone.utc)
        before = RealDateTime.now(RealTimezone.utc).replace(microsecond=0)

        originals = {
            "datetime": bridge_module.datetime,
            "timezone": bridge_module.timezone,
            "_process_now": bridge_module._process_now,
            "_parse_ts": bridge_module._parse_ts,
            "_normalize_process_now": bridge_module._normalize_process_now,
            "_evaluate_at": bridge_module._evaluate_at,
        }
        try:
            # Exercise the exact predecessor seam and adjacent exposed clock helpers.
            # Supported CURRENT evaluation must continue to use the import-time
            # capabilities captured in compile_bridge's lexical cells.
            bridge_module.datetime = object()
            bridge_module.timezone = object()
            bridge_module._process_now = lambda: fake_now
            bridge_module._parse_ts = lambda *_: (_ for _ in ()).throw(AssertionError("rebound parser used"))
            bridge_module._normalize_process_now = lambda *_: (_ for _ in ()).throw(AssertionError("rebound normalizer used"))
            bridge_module._evaluate_at = lambda *_args, **_kwargs: {
                "status": "OPPORTUNITY_EVIDENCE_READY",
                "evaluated_at": "2001-01-01T00:00:00Z",
            }

            result = bridge_module.compile_bridge(
                "jersey-dn827803-main-v1", source, manifest, None,
            )
        finally:
            for name, value in originals.items():
                setattr(bridge_module, name, value)

        after = RealDateTime.now(RealTimezone.utc).replace(microsecond=0)
        evaluated = RealDateTime.strptime(
            result["evaluated_at"], "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=RealTimezone.utc)

        self.assertLessEqual(before, evaluated)
        self.assertLessEqual(evaluated, after)
        self.assertNotEqual(fake_now, evaluated)
        self.assertEqual("HOLD", result["status"])
        self.assertIn("CONTROLLING_TENDER_PACK_NOT_REVIEWED", result["reason_codes"])
        self.assertIn("TENDER_PACK_NOT_ACQUIRED", result["reason_codes"])
        self.assertIn("VAULT_ROOTS_NOT_PINNED", result["reason_codes"])
        self.assertFalse(result["external_submission_authorized"])
        self.assertTrue(all(value is False for value in result["authority"].values()))


if __name__ == "__main__":
    unittest.main()
