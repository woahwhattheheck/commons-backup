from __future__ import annotations
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from land_counterfactual import compare_land_shift, make_land_candidate


class FakeEngine:
    LAND_PRICES = [2000, 3000, 4000]

    @staticmethod
    def _quadrant_of(x, y, board_size):
        half = board_size // 2
        if y < half:
            return "NW" if x < half else "NE"
        return "SW" if x < half else "SE"


class FakeLabor:
    @staticmethod
    def _configuration(configuration):
        return SimpleNamespace(maxMarketOrdersPerTurn=3)

    @staticmethod
    def project_shift(engine, observation, parent_after_call, selected_action, cfg, *, fork_parent):
        initial_land = list(observation["farms"][0]["unlocked_quadrants"])
        initial_buy = any(order == ["BUY_LAND"] for order in selected_action["market"])
        continuation = fork_parent()
        later_observation = copy.deepcopy(observation)
        later_observation["step"] = 11
        if initial_buy:
            later_observation["farms"][0]["unlocked_quadrants"] = [*initial_land, "SW"]
        later_action = continuation(later_observation)
        later_buy = any(order == ["BUY_LAND"] for order in later_action["market"])

        unlocked = list(initial_land)
        cash = 5000
        if initial_buy:
            unlocked.append("SW")
            cash -= 2000
        if later_buy:
            unlocked.append("SE" if "SW" in unlocked else "SW")
            cash -= 3000 if initial_buy else 2000
        farm = copy.deepcopy(observation["farms"][0])
        farm["unlocked_quadrants"] = unlocked
        return SimpleNamespace(
            productive_state={"farm": farm, "private": copy.deepcopy(observation["private"])},
            market_inventory=copy.deepcopy(observation["market"]["inventory"]),
            horizon_step=11,
            estimated_cash=cash,
            minimum_cash=cash,
            hiring_outflow=0,
            net_nonhire_outflow=5000-cash,
            net_nonhire_inflow=0,
        )


def observation():
    tile = {"type": "EMPTY", "owner": 0}
    farm = {
        "money": 5000,
        "farmer": [0, 0],
        "hands": [[0, 1]],
        "tiles": [[copy.deepcopy(tile) for _ in range(4)] for _ in range(4)],
        "unlocked_quadrants": ["NW"],
    }
    return {
        "step": 10,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {"inventory": {}, "seeds": {}},
        "market": {"inventory": {"WHEAT": 100}},
    }


def incumbent():
    return {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["SELL", "WHEAT", 0]]}


def factory_counter(counter):
    def factory():
        counter.append(object())
        def continuation(obs):
            return {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["BUY_LAND"]]}
        return continuation
    return factory


class LandCounterfactualUnitTests(unittest.TestCase):
    def test_make_candidate_is_slot_preserving_and_input_safe(self):
        base = incumbent()
        frozen = copy.deepcopy(base)
        candidate = make_land_candidate(base, slot=2, max_orders=3)
        self.assertEqual(base, frozen)
        self.assertEqual(candidate["market"], [
            ["SELL", "WHEAT", 0], ["SELL", "WHEAT", 0], ["BUY_LAND"]])

    def test_active_slot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty or a zero-quantity SELL"):
            make_land_candidate({"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}, slot=0)

    def test_suppression_models_move_earlier_not_extra_land(self):
        base = incumbent()
        candidate = make_land_candidate(base, slot=1, max_orders=3)
        forks = []
        report = compare_land_shift(
            FakeLabor, FakeEngine, observation(), object(), base, candidate, {},
            fork_parent=factory_counter(forks), suppress_next_land=True)
        self.assertEqual(len(forks), 2)
        self.assertEqual(report["suppressed_next_land"], {"step": 11, "slot": 0})
        self.assertEqual(report["candidate_unlock_step"], 10)
        self.assertEqual(report["baseline_unlock_step"], 11)
        self.assertEqual(report["cash"]["delta"], 0)
        self.assertTrue(report["state"]["same_productive_state"])
        self.assertEqual(report["state"]["future_action_divergence_steps"], [10, 11])

    def test_without_suppression_buys_an_extra_quadrant(self):
        base = incumbent()
        candidate = make_land_candidate(base, slot=1, max_orders=3)
        report = compare_land_shift(
            FakeLabor, FakeEngine, observation(), object(), base, candidate, {},
            fork_parent=factory_counter([]), suppress_next_land=False)
        self.assertIsNone(report["suppressed_next_land"])
        self.assertNotEqual(report["state"]["candidate_final_unlocked"],
                            report["state"]["incumbent_final_unlocked"])
        self.assertLess(report["cash"]["delta"], 0)

    def test_candidate_cannot_change_worker_actions(self):
        base = incumbent()
        candidate = make_land_candidate(base, slot=1, max_orders=3)
        candidate["farmer"] = ["WEST"]
        with self.assertRaisesRegex(ValueError, "farmer"):
            compare_land_shift(
                FakeLabor, FakeEngine, observation(), object(), base, candidate, {},
                fork_parent=factory_counter([]))

    def test_requested_turns_are_not_reported_as_receipts(self):
        base = incumbent()
        candidate = make_land_candidate(base, slot=1, max_orders=3)
        report = compare_land_shift(
            FakeLabor, FakeEngine, observation(), object(), base, candidate, {},
            fork_parent=factory_counter([]), suppress_next_land=True)
        self.assertTrue(report["limits"]["requested_worker_turns_are_not_successful-action_receipts"])
        self.assertTrue(report["limits"]["future_cash_or_win_value_not_established"])
        self.assertTrue(report["limits"]["candidate_selection_not_performed"])


if __name__ == "__main__":
    unittest.main()
