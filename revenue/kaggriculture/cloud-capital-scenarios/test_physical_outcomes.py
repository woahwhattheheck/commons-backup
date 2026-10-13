# SPDX-License-Identifier: Apache-2.0
"""Engine-free input-bridge tests; these synthetic records are not game evidence."""
from copy import deepcopy
import json
import unittest

from dated_scenarios import DatedSelector
from physical_outcomes import _digest


def fixture():
    obs = {"step": 0, "player": 0, "farms": [{"money": 100}, {"money": 200}]}
    offers = [{"route_id": "main"}, {"route_id": "sheep"}]
    report = {"schema": "titan.capital-physical-replay.v1", "complete": True,
              "observation_sha256": _digest(obs), "start_step": 0, "end_step": 2,
              "original_route": "main", "scenarios": {"a": {}, "b": {}}, "cases": []}
    for route, finals in (("main", (200, 250)), ("sheep", (220, 280))):
        for name, final in zip(("a", "b"), finals):
            rows = [dict(step=0, cash_before=100, cash_after=90, cash_delta=-10),
                    dict(step=1, cash_before=90, cash_after=final, cash_delta=final-90),
                    dict(step=2, cash_before=final, cash_after=final, cash_delta=0)]
            report["cases"].append(dict(offered_route=route, scenario_id=name, status="complete",
                program_sha256=("a" if route=="main" else "b")*64, rival_cash_delta=None,
                final_cash=final, cash_gain=final-100, minimum_after_market_cash=90,
                market_rows=rows, result={"farm":{"money":final}, "cash_gain":final-100,
                                          "start_step":0,"end_step":2}))
    return obs, offers, report


class CompletedOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.obs, self.offers, self.replay = fixture()

    def select(self, **kwargs):
        selector = DatedSelector.from_completed_replay(self.replay, {"episodeSteps": 4},
                                                       scenario_ids=("a", "b"), **kwargs)
        chosen = selector(self.offers, self.obs)
        json.dumps(selector.last_report, allow_nan=False)
        return chosen, selector.last_report

    def invalid(self):
        chosen, report = self.select()
        self.assertEqual(chosen, "main")
        self.assertEqual(report["reason"], "execution_report_invalid")
        self.assertEqual(report["scenarios"], [])

    def test_positive_bank_uses_same_selector_and_paired_ranking(self):
        chosen, result = self.select()
        self.assertEqual(chosen, "sheep")
        self.assertEqual(result["candidates"]["sheep"]["worst_paired_gain"], 20)
        self.assertIsNone(result["rival_utility"])
        self.assertNotIn("minimum_nominal_cash", result["scenarios"][0]["routes"]["sheep"])

    def test_strict_margin_retains_incumbent(self):
        self.assertEqual(self.select(minimum_gain=20)[0], "main")

    def test_missing_negative_or_positive_case_cannot_shrink_bank(self):
        for index in range(4):
            original = deepcopy(self.replay)
            del self.replay["cases"][index]
            self.invalid()
            self.replay = original

    def test_removed_scenario_header_and_cases_cannot_shrink_bank(self):
        del self.replay["scenarios"]["b"]
        self.replay["cases"] = [c for c in self.replay["cases"] if c["scenario_id"] == "a"]
        self.invalid()

    def test_incomplete_status_rejected_even_with_complete_top_flag(self):
        for status in ("incomplete", "incompatible", "unknown"):
            self.replay["cases"][0]["status"] = status
            self.invalid()

    def test_top_complete_flag_must_be_true_not_truthy(self):
        for value in (False, 1, "true", None):
            self.replay["complete"] = value
            self.invalid()

    def test_duplicate_case_rejected(self):
        self.replay["cases"].append(deepcopy(self.replay["cases"][0]))
        self.invalid()

    def test_observation_and_seat_binding(self):
        self.obs["farms"][0]["money"] += 1
        self.invalid()
        self.obs, self.offers, self.replay = fixture()
        self.obs["player"] = 1
        self.invalid()

    def test_nonterminal_replay_not_a_terminal_outcome(self):
        self.replay["end_step"] = 1
        self.invalid()

    def test_delegated_horizon_and_missing_queue_rejected(self):
        self.replay["cases"][0]["result"]["end_step"] = 1
        self.invalid()
        self.obs, self.offers, self.replay = fixture()
        self.replay["cases"][0]["market_rows"].pop()
        self.invalid()

    def test_changed_offered_program_between_scenarios_rejected(self):
        self.replay["cases"][1]["program_sha256"] = "c" * 64
        self.invalid()

    def test_static_quote_costs_not_charged_again(self):
        for offer in self.offers:
            offer["orders"] = [{"delta": -999999, "order": ["BUY_ANIMAL", "GOOSE", 1]}]
        self.assertEqual(self.select()[0], "sheep")
        self.assertEqual(self.select()[1]["candidates"]["sheep"]["worst_paired_gain"], 20)

    def test_changed_incumbent_rejected(self):
        self.offers.reverse()
        chosen, result = self.select()
        self.assertEqual(chosen, "sheep")
        self.assertEqual(result["reason"], "execution_report_invalid")

    def test_cash_and_order_binding_mutations_rejected(self):
        mutations = [lambda c: c.update(final_cash=999), lambda c: c.update(cash_gain=999),
                     lambda c: c.update(minimum_after_market_cash=0),
                     lambda c: c["market_rows"][1].update(step=2),
                     lambda c: c["market_rows"][1].update(cash_before=99),
                     lambda c: c["market_rows"][1].update(cash_delta=999),
                     lambda c: c["result"]["farm"].update(money=999)]
        for mutate in mutations:
            self.obs, self.offers, self.replay = fixture()
            mutate(self.replay["cases"][0])
            self.invalid()

    def test_nonfinite_cash_and_rival_model_rejected(self):
        for value in (float("inf"), float("nan"), True, None):
            self.replay["cases"][0]["final_cash"] = value
            self.invalid()
        self.obs, self.offers, self.replay = fixture()
        self.replay["cases"][0]["rival_cash_delta"] = 10
        self.invalid()

    def test_report_read_only_and_revalidated_not_stale_cache(self):
        before = deepcopy((self.obs, self.offers, self.replay))
        selector = DatedSelector.from_completed_replay(self.replay, {"episodeSteps": 4},
                                                       scenario_ids=("a", "b"))
        self.assertEqual(selector(self.offers, self.obs), "sheep")
        self.assertEqual((self.obs, self.offers, self.replay), before)
        self.replay["cases"].pop()
        self.assertEqual(selector(self.offers, self.obs), "main")
        self.assertEqual(selector.last_report["reason"], "execution_report_invalid")


if __name__ == "__main__":
    unittest.main()
