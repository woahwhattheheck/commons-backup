from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "townclock", HERE / "townclock_attribution.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Tests(unittest.TestCase):
    def classify(self, **overrides):
        values = dict(
            now=24,
            item="MILK",
            reference=[(24, 2), (26, 3)],
            plan=[(24, 4), (26, 1)],
            config={},
        )
        values.update(overrides)
        return mod.classify_candidate(**values)

    def test_center_tick_future_to_now_advance_is_veto(self):
        got = self.classify()
        self.assertEqual(got["decision"], "VETO")
        self.assertEqual(got["advanced_units"], 2)
        self.assertFalse(mod.candidate_allowed(
            now=24, item="MILK",
            reference=[(24, 2), (26, 3)],
            plan=[(24, 4), (26, 1)], config={}
        ))

    def test_due_and_base_quantity_is_not_vetoed(self):
        got = self.classify(plan=[(24, 2), (25, 1), (26, 2)])
        self.assertEqual(got["decision"], "PASS")
        self.assertEqual(got["advanced_units"], 0)

    def test_future_to_future_retiming_is_not_e7(self):
        got = self.classify(
            reference=[(24, 2), (26, 3)],
            plan=[(24, 2), (25, 3)]
        )
        self.assertEqual(got["decision"], "PASS")

    def test_non_center_tick_does_not_veto(self):
        got = self.classify(
            now=25,
            reference=[(25, 2), (27, 3)],
            plan=[(25, 4), (27, 1)]
        )
        self.assertEqual(got["decision"], "PASS")
        self.assertEqual(got["advanced_units"], 2)
        self.assertEqual(got["reason"], "not-town-center-tick")

    def test_fertilizer_is_explicitly_excluded(self):
        got = self.classify(item="FERTILIZER")
        self.assertEqual(got["decision"], "PASS")
        self.assertEqual(got["reason"], "town-center-excluded-product")

    def test_configured_interval_is_respected(self):
        got = self.classify(
            now=36,
            reference=[(36, 1), (40, 2)],
            plan=[(36, 2), (40, 1)],
            config={"townCenterSellInterval": 12},
        )
        self.assertEqual(got["decision"], "VETO")
        self.assertEqual(got["interval"], 12)

    def test_invalid_interval_refuses_candidate(self):
        got = self.classify(config={"townCenterSellInterval": "24"})
        self.assertEqual(got["decision"], "REFUSE")
        self.assertFalse(mod.candidate_allowed(
            now=24, item="MILK",
            reference=[(24, 2), (26, 3)],
            plan=[(24, 4), (26, 1)],
            config={"townCenterSellInterval": "24"},
        ))

    def test_quantity_drift_refuses_candidate(self):
        got = self.classify(plan=[(24, 4), (26, 2)])
        self.assertEqual(got["decision"], "REFUSE")
        self.assertEqual(got["reason"], "quantity-drift")

    def test_past_or_negative_rows_refuse_candidate(self):
        self.assertEqual(
            self.classify(reference=[(23, 1), (24, 4)])["decision"], "REFUSE"
        )
        self.assertEqual(
            self.classify(plan=[(24, -1), (26, 6)])["decision"], "REFUSE"
        )

    def test_duplicate_dates_are_aggregated(self):
        got = self.classify(
            reference=[(24, 1), (24, 1), (26, 3)],
            plan=[(24, 3), (24, 1), (26, 1)],
        )
        self.assertEqual(got["decision"], "VETO")
        self.assertEqual(got["advanced_units"], 2)

    def test_census_is_deterministic_and_counts_refusal(self):
        records = [
            {
                "now": 24, "item": "MILK",
                "reference": [[24, 2], [26, 3]],
                "plan": [[24, 4], [26, 1]], "config": {}
            },
            {
                "now": 25, "item": "WOOL",
                "reference": [[25, 1], [27, 2]],
                "plan": [[25, 1], [26, 2]], "config": {}
            },
            {"bad": True},
        ]
        report = mod.census(records)
        self.assertEqual(report["decisions"], {"PASS": 1, "VETO": 1, "REFUSE": 1})
        self.assertEqual(report["veto_advanced_units"], 2)
        self.assertFalse(report["policy_claim"])
        self.assertFalse(report["economic_claim"])

    def test_engine_verifier_rejects_unpinned_source(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "kaggriculture.py"
            path.write_text("not the pinned engine\n")
            with self.assertRaisesRegex(ValueError, "engine source drift"):
                mod.verify_engine_source(path)

    def test_constants_bind_current_engine_and_historical_donor(self):
        self.assertEqual(
            mod.ENGINE_GIT_BLOB,
            "3c202c7ee921da239356789e266b694635103fc4",
        )
        self.assertEqual(mod.HISTORICAL_DONOR_PR, 12423)
        self.assertEqual(mod.DEFAULT_TOWN_CENTER_INTERVAL, 24)


if __name__ == "__main__":
    unittest.main()
