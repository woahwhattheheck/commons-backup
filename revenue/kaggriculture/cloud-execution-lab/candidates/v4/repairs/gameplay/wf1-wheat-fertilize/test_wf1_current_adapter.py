# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace
from unittest import mock

import wf1_current_adapter as adapter

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "marketParams": {},
}


def _grid():
    return [[None for _ in range(10)] for _ in range(10)]


def _case():
    farm0 = {"farmer": [1, 1], "hands": [[2, 2]], "tiles": _grid()}
    farm1 = {"farmer": [3, 3], "hands": [], "tiles": _grid()}
    observation = {
        "step": 25,
        "player": 0,
        "farms": [farm0, farm1],
        "private": {
            "inventories": [{"FERTILIZER": 0}, {"FERTILIZER": 1}],
            "shed": {"WHEAT": 0, "FERTILIZER": 0},
        },
        "market": {"prices": {"WHEAT": 25, "CARROT": 25, "FERTILIZER": 10}},
    }
    action = {"farmer": ["PASS"], "hands": [["WATER"]], "market": []}
    return observation, action


class CurrentAdapterTests(unittest.TestCase):
    def setUp(self):
        adapter._donor._STATE.clear()

    def test_off_is_exact_identity_and_never_calls_donor(self):
        obs, action = _case()
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            self.assertIs(adapter.apply_wf1_current(obs, action, CONFIG, enabled=False), action)
            self.assertIs(adapter.apply_wf1_current(obs, action, CONFIG, enabled=1), action)

    def test_standard_domain_delegates_exact_objects(self):
        obs, action = _case()
        sentinel = {"ok": True}
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", return_value=sentinel) as call:
            out = adapter.apply_wf1_current(obs, action, CONFIG, enabled=True)
        self.assertIs(out, sentinel)
        call.assert_called_once_with(obs, action, enabled=True)

    def test_attribute_configuration_is_supported(self):
        obs, action = _case()
        cfg = SimpleNamespace(**CONFIG)
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", return_value=action) as call:
            self.assertIs(adapter.apply_wf1_current(obs, action, cfg, enabled=True), action)
        self.assertEqual(call.call_count, 1)

    def test_configuration_drift_fails_closed_before_donor(self):
        obs, action = _case()
        bads = []
        for name in ("episodeSteps", "turnsPerDay", "boardSize", "shedCapacity", "maxMarketOrdersPerTurn"):
            cfg = dict(CONFIG)
            cfg[name] += 1
            bads.append(cfg)
            cfg_bool = dict(CONFIG)
            cfg_bool[name] = True
            bads.append(cfg_bool)
        bad_market = dict(CONFIG); bad_market["marketParams"] = {"x": 1}; bads.append(bad_market)
        bads.extend([None, {}])
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            for cfg in bads:
                with self.subTest(cfg=cfg):
                    self.assertIs(adapter.apply_wf1_current(obs, action, cfg, enabled=True), action)

    def test_player_domain_and_two_farm_contract(self):
        obs, action = _case()
        poisons = []
        for player in (True, -1, 2, "0"):
            x = copy.deepcopy(obs); x["player"] = player; poisons.append(x)
        x = copy.deepcopy(obs); x["farms"].append(copy.deepcopy(obs["farms"][0])); poisons.append(x)
        x = copy.deepcopy(obs); x["farms"] = [obs["farms"][0]]; poisons.append(x)
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            for poisoned in poisons:
                self.assertIs(adapter.apply_wf1_current(poisoned, action, CONFIG, enabled=True), action)

    def test_exact_actor_inventory_cardinality(self):
        obs, action = _case()
        too_many = copy.deepcopy(obs)
        too_many["private"]["inventories"].append({})
        too_few = copy.deepcopy(obs)
        too_few["private"]["inventories"].pop()
        wrong_actions = copy.deepcopy(action)
        wrong_actions["hands"].append(["PASS"])
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            self.assertIs(adapter.apply_wf1_current(too_many, action, CONFIG, enabled=True), action)
            self.assertIs(adapter.apply_wf1_current(too_few, action, CONFIG, enabled=True), action)
            self.assertIs(adapter.apply_wf1_current(obs, wrong_actions, CONFIG, enabled=True), wrong_actions)

    def test_board_and_position_contract(self):
        obs, action = _case()
        wrong_board = copy.deepcopy(obs)
        wrong_board["farms"][0]["tiles"] = _grid()[:-1]
        bool_pos = copy.deepcopy(obs)
        bool_pos["farms"][0]["farmer"] = [True, 1]
        off_board = copy.deepcopy(obs)
        off_board["farms"][0]["hands"][0] = [10, 2]
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            for poisoned in (wrong_board, bool_pos, off_board):
                self.assertIs(adapter.apply_wf1_current(poisoned, action, CONFIG, enabled=True), action)

    def test_inventory_and_shed_numeric_poison(self):
        obs, action = _case()
        inv = copy.deepcopy(obs); inv["private"]["inventories"][0]["FERTILIZER"] = True
        shed = copy.deepcopy(obs); shed["private"]["shed"]["WHEAT"] = -1
        key = copy.deepcopy(obs); key["private"]["shed"][1] = 0
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            for poisoned in (inv, shed, key):
                self.assertIs(adapter.apply_wf1_current(poisoned, action, CONFIG, enabled=True), action)

    def test_action_shape_poison(self):
        obs, action = _case()
        x = copy.deepcopy(action); x["farmer"] = ["PASS", 1]
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", return_value=x) as call:
            self.assertIs(adapter.apply_wf1_current(obs, x, CONFIG, enabled=True), x)
            self.assertEqual(call.call_count, 1)
        malformed = []
        x = copy.deepcopy(action); x["farmer"] = []; malformed.append(x)
        x = copy.deepcopy(action); x["hands"][0] = "WATER"; malformed.append(x)
        x = copy.deepcopy(action); x["market"] = {}; malformed.append(x)
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=AssertionError):
            for x in malformed:
                self.assertIs(adapter.apply_wf1_current(obs, x, CONFIG, enabled=True), x)

    def test_delegate_exception_is_exact_identity(self):
        obs, action = _case()
        with mock.patch.object(adapter._donor, "apply_wheat_fertilize", side_effect=RuntimeError("boom")):
            self.assertIs(adapter.apply_wf1_current(obs, action, CONFIG, enabled=True), action)


    def test_market_budget_zero_through_ten_still_delegates(self):
        for count in range(CONFIG["maxMarketOrdersPerTurn"] + 1):
            obs, action = _case()
            action["market"] = [["PASS"] for _ in range(count)]
            sentinel = {"delegated": count}
            with self.subTest(count=count), mock.patch.object(
                    adapter._donor, "apply_wheat_fertilize", return_value=sentinel) as call:
                self.assertIs(adapter.apply_wf1_current(obs, action, CONFIG, enabled=True), sentinel)
                call.assert_called_once_with(obs, action, enabled=True)

    def test_over_budget_rows_do_not_call_stateful_donor(self):
        for count in (11, 12, 20, 100):
            obs, action = _case()
            action["market"] = [["PASS"] for _ in range(count)]
            with self.subTest(count=count), mock.patch.object(
                    adapter._donor, "apply_wheat_fertilize", return_value=action) as call:
                self.assertIs(adapter.apply_wf1_current(obs, action, CONFIG, enabled=True), action)
                call.assert_not_called()

    def test_eleventh_row_cannot_consume_wheat_credit(self):
        obs, action = _case()
        obs["private"]["shed"]["WHEAT"] = 10
        action["market"] = [["PASS"] for _ in range(10)] + [["SELL", "WHEAT", 1]]
        adapter._donor._STATE[0] = {"last_step": 24, "day": 1, "tiles": {}, "credit": 3}
        before_action = copy.deepcopy(action)
        before_state = copy.deepcopy(adapter._donor._STATE)
        before_report = copy.deepcopy(adapter._donor.REPORT)
        out = adapter.apply_wf1_current(obs, action, CONFIG, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(action, before_action)
        self.assertEqual(adapter._donor._STATE, before_state)
        self.assertEqual(adapter._donor.REPORT, before_report)

    def test_tenth_row_credit_sale_remains_live(self):
        obs, action = _case()
        obs["private"]["shed"]["WHEAT"] = 10
        action["market"] = [["PASS"] for _ in range(9)] + [["SELL", "WHEAT", 1]]
        before_action = copy.deepcopy(action)
        adapter._donor._STATE[0] = {"last_step": 24, "day": 1, "tiles": {}, "credit": 3}
        out = adapter.apply_wf1_current(obs, action, CONFIG, enabled=True)
        self.assertEqual(out["market"][9], ["SELL", "WHEAT", 4])
        self.assertEqual(out["market"][:9], before_action["market"][:9])
        self.assertEqual(action, before_action)
        self.assertEqual(adapter._donor._STATE[0]["credit"], 0)


if __name__ == "__main__":
    unittest.main()
