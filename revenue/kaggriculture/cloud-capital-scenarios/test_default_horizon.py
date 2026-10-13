# SPDX-License-Identifier: Apache-2.0
"""Default-horizon compatibility; fixtures are not game evidence.

DATE_RUNTIME_ROOT optionally selects an original source tree for negative control.
"""
from copy import deepcopy
import os
import sys
import unittest

if os.environ.get("DATE_RUNTIME_ROOT"):
    sys.path.insert(0, os.environ["DATE_RUNTIME_ROOT"])

from dated_scenarios import DatedSelector
from physical_outcomes import _digest, compare_replay


def fixture(start=717, end=718, alternative_gain=20):
    observation = {"step": start, "player": 0, "farms": [{"money": 100}, {"money": 200}]}
    offers = [{"route_id": "main"}, {"route_id": "alternative"}]
    report = {
        "schema": "titan.capital-physical-replay.v1", "complete": True,
        "observation_sha256": _digest(observation), "start_step": start,
        "end_step": end, "original_route": "main", "scenarios": {"declared": {}},
        "cases": [],
    }
    for route, final in (("main", 120), ("alternative", 120 + alternative_gain)):
        current, rows = 100, []
        for step in range(start, end + 1):
            after = final if step == end else current
            rows.append({"step": step, "cash_before": current,
                         "cash_after": after, "cash_delta": after - current})
            current = after
        report["cases"].append({
            "offered_route": route, "scenario_id": "declared", "status": "complete",
            "program_sha256": ("a" if route == "main" else "b") * 64,
            "rival_cash_delta": None, "final_cash": final, "cash_gain": final - 100,
            "minimum_after_market_cash": min(100, final), "market_rows": rows,
            "result": {"farm": {"money": final}, "cash_gain": final - 100,
                       "start_step": start, "end_step": end},
        })
    return offers, observation, report


def compare(config, data=None):
    offers, observation, report = fixture() if data is None else data
    return compare_replay(offers, observation, report, config, scenario_ids=("declared",))


class DefaultHorizonTests(unittest.TestCase):
    def test_omitted_horizon_equals_explicit_default(self):
        self.assertEqual(compare({}), compare({"episodeSteps": 720}))

    def test_unrelated_config_does_not_disable_default(self):
        self.assertEqual(compare({"turnsPerDay": 24}), compare({"episodeSteps": 720}))

    def test_existing_selector_factory_accepts_default_config(self):
        offers, obs, replay = fixture()
        selector = DatedSelector.from_completed_replay(replay, {}, scenario_ids=("declared",))
        self.assertEqual(selector(offers, obs), "alternative")
        self.assertEqual(selector.last_report["reason"], "covered_executed_own_cash_improvement")

    def test_default_negative_result_is_valid_comparison_not_invalid_input(self):
        result = compare({}, fixture(alternative_gain=-20))
        self.assertEqual(result["selected"], "main")
        self.assertEqual(result["reason"], "no_covered_improvement")
        self.assertEqual(result["candidates"]["alternative"]["worst_paired_gain"], -20)

    def test_explicit_custom_horizon_still_works(self):
        result = compare({"episodeSteps": 5}, fixture(start=2, end=3))
        self.assertEqual(result["selected"], "alternative")
        self.assertEqual(result["terminal_step"], 3)

    def test_default_does_not_adopt_short_report_horizon(self):
        result = compare({}, fixture(start=2, end=3))
        self.assertEqual(result["reason"], "execution_report_invalid")
        self.assertEqual(result["invalid_input"], "replay is not this terminal horizon")

    def test_explicit_invalid_values_are_not_defaulted(self):
        for value in (None, True, False, "720", 720.0, float("nan"), -1, 0, 1):
            with self.subTest(value=value):
                result = compare({"episodeSteps": value})
                self.assertEqual(result["reason"], "execution_report_invalid")
                self.assertEqual(result["selected"], "main")

    def test_explicit_mismatched_horizon_rejected(self):
        result = compare({"episodeSteps": 719})
        self.assertEqual(result["invalid_input"], "replay is not this terminal horizon")

    def test_default_does_not_hide_missing_case(self):
        offers, obs, replay = fixture()
        replay["cases"].pop()
        result = compare({}, (offers, obs, replay))
        self.assertEqual(result["invalid_input"], "missing route/scenario case")
        self.assertEqual(result["selected"], "main")

    def test_default_validation_does_not_modify_inputs(self):
        data, config = fixture(), {"turnsPerDay": 24}
        before = deepcopy((data, config))
        result = compare(config, data)
        self.assertEqual((data, config), before)
        self.assertEqual(result["selected"], "alternative")


if __name__ == "__main__":
    unittest.main()
