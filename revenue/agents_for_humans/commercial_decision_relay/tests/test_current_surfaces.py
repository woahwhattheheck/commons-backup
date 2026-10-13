from __future__ import annotations

import json
from pathlib import Path
import unittest

from decision_relay import (
    DecisionRelayError,
    RelayEngine,
    reconcile,
    reconcile_historical,
)
from decision_relay.cli import main as cli_main
from decision_relay import web_demo


FIXTURE = Path(__file__).parents[1] / "fixtures" / "demo-batch.json"
TRUSTED_AFTER_EXPIRY = "2026-09-21T12:00:00Z"


def batch() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def series(receipt: dict, series_id: str) -> dict:
    return next(item for item in receipt["series"] if item["series_id"] == series_id)


class CurrentSurfaceTests(unittest.TestCase):
    def test_public_reconcile_requires_trusted_time(self):
        with self.assertRaises(DecisionRelayError) as ctx:
            reconcile(batch())
        self.assertEqual(ctx.exception.code, "trusted_time_required")

    def test_explicit_historical_replay_cannot_masquerade_as_current(self):
        historical = reconcile_historical(batch())
        current = reconcile(batch(), evaluated_at=TRUSTED_AFTER_EXPIRY)

        self.assertEqual("AWAITING_RESPONSE", series(historical, "delta-services")["status"])
        self.assertEqual("REISSUE_REQUIRED", series(current, "delta-services")["status"])
        self.assertEqual("2026-09-13T12:00:00Z", historical["evaluated_at"])
        self.assertEqual(TRUSTED_AFTER_EXPIRY, current["evaluated_at"])

    def test_public_relay_engine_requires_trusted_time(self):
        engine = RelayEngine()
        engine.ingest(batch())
        with self.assertRaises(DecisionRelayError) as ctx:
            engine.reconcile()
        self.assertEqual(ctx.exception.code, "trusted_time_required")
        current = engine.reconcile(evaluated_at=TRUSTED_AFTER_EXPIRY)
        self.assertEqual("REISSUE_REQUIRED", series(current, "delta-services")["status"])

    def test_cli_current_reconcile_requires_evaluated_at_before_file_read(self):
        with self.assertRaises(SystemExit) as ctx:
            cli_main(["reconcile", "--batch", "definitely-missing.json"])
        self.assertEqual(2, ctx.exception.code)

    def test_web_demo_requires_trusted_evaluated_at(self):
        with self.assertRaises(SystemExit) as ctx:
            web_demo.main([])
        self.assertEqual(2, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
