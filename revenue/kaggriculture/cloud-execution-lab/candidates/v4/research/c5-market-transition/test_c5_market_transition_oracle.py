# SPDX-License-Identifier: Apache-2.0
"""Independent contract tests for C5's source-pinned market/town oracle.

Set C5_ORACLE_ENGINE and C5_ORACLE_HELPER to the exact source paths.
The oracle deliberately fails rather than skipping when a dependency is absent.
"""
from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import c5_market_transition_oracle as oracle

HERE = Path(__file__).resolve().parent
ENGINE_PATH = Path(os.environ.get("C5_ORACLE_ENGINE", str(HERE / "reference/engine/kaggriculture.py")))
HELPER_PATH = Path(os.environ.get("C5_ORACLE_HELPER", str(HERE / "r04_c5_wheat_demand.py")))


class C5MarketTransitionOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.helper = oracle.load_sources(ENGINE_PATH, HELPER_PATH)

    def evaluate(self, **kwargs):
        return oracle.evaluate(self.engine, self.helper, oracle.World(**kwargs))

    def test_real_positive_buy_lower_bound_both_seats(self):
        for buyer in (0, 1):
            with self.subTest(buyer=buyer):
                rows = [[], []]
                rows[buyer] = [["BUY_PRODUCT", "WHEAT", 3]]
                result = self.evaluate(label="buy", rows=tuple(rows))
                self.assertEqual(result["buys"][buyer], 3)
                self.assertEqual(result["seats"][1-buyer]["lower_bound"], 3)
                self.assertTrue(result["seats"][1-buyer]["relocated"])
                self.assertEqual(result["seats"][buyer]["lower_bound"], 0)
                self.assertFalse(result["seats"][buyer]["relocated"])

    def test_floor_sale_is_inventory_invisible_not_negative_gross_buy(self):
        result = self.evaluate(label="floor", inventory=10**15,
                               rows=([], [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 3]]))
        self.assertEqual(result["invisible_sales"], 3)
        self.assertEqual(result["inventory_before"]-result["inventory_after"], 3)
        self.assertEqual(result["seats"][0]["lower_bound"], 3)
        self.assertEqual(result["seats"][0]["rival_net_buys"], 0)
        self.assertFalse(result["seats"][0]["relocated"])

    def test_visible_sales_reduce_bound(self):
        result = self.evaluate(label="supply", rows=([["SELL", "WHEAT", 4]],
                                                      [["BUY_PRODUCT", "WHEAT", 3]]))
        self.assertEqual(result["visible_sales"], 4)
        self.assertEqual(result["seats"][0]["lower_bound"], -1)
        self.assertFalse(result["seats"][0]["relocated"])

    def test_actual_partial_fill_is_not_requested_quantity(self):
        cases = [dict(money=(26, 100000)), dict(room=(1, 90))]
        for case in cases:
            with self.subTest(case=case):
                result = self.evaluate(label="partial", rows=([["BUY_PRODUCT", "WHEAT", 7]],
                                                               [["BUY_PRODUCT", "WHEAT", 2]]), **case)
                self.assertEqual(result["buys"][0], 1)
                self.assertEqual(result["seats"][0]["lower_bound"], -4)
                self.assertEqual(result["seats"][1]["lower_bound"], 1)

    def test_failed_buy_does_not_certify_rival_signal(self):
        for case in (dict(money=(0, 0)), dict(room=(0, 0))):
            with self.subTest(case=case):
                result = self.evaluate(label="no-fill", rows=([["BUY_PRODUCT", "WHEAT", 7]],
                                                               [["BUY_PRODUCT", "WHEAT", 2]]), **case)
                self.assertEqual(result["buys"], [0, 0])
                self.assertEqual([s["lower_bound"] for s in result["seats"]], [-7, -2])

    def test_raw_market_cap_precedes_parsing(self):
        for cap in (-2, 0, 1, 2, 10):
            for index in (0, 1, 9, 10, 11):
                with self.subTest(cap=cap, index=index):
                    result = self.evaluate(label="prefix", cap=cap,
                                           rows=([[]]*index+[["BUY_PRODUCT", "WHEAT", 2]], []))
                    self.assertEqual(result["buys"][0], 2 if index < max(1, cap) else 0)
                    self.assertEqual(result["seats"][0]["lower_bound"], 0)

    def test_unknown_and_tuple_orders_remain_engine_inert(self):
        for row in (None, [], ["UNKNOWN", "WHEAT", 3], ("BUY_PRODUCT", "WHEAT", 3)):
            with self.subTest(row=row):
                result = self.evaluate(label="inert", rows=([row], [["BUY_PRODUCT", "WHEAT", 2]]))
                self.assertEqual(result["buys"], [0, 2])
                self.assertEqual(result["seats"][0]["lower_bound"], 2)

    def test_engine_coerced_quantities_fail_closed_in_detector(self):
        for quantity in ("2", 2.5, True, 0, -1):
            for own in (0, 1):
                with self.subTest(quantity=quantity, own=own):
                    rows = [[], []]
                    rows[own] = [["BUY_PRODUCT", "WHEAT", quantity]]
                    result = self.evaluate(label="coercion", rows=tuple(rows))
                    self.assertFalse(result["seats"][own]["record_valid"])
                    self.assertFalse(result["seats"][own]["relocated"])

    def test_all_shop_instances_cadences_and_negative_inventory(self):
        for world in oracle.explicit_worlds():
            with self.subTest(label=world.label):
                result = oracle.evaluate(self.engine, self.helper, world)
                self.assertEqual(len(result["seats"]), 2)
        result = self.evaluate(label="duplicates", inventory=-3, step=24,
                               shops=("BAKERY", "BAKERY", "PIZZA_SHOP", "YARN_STORE"))
        self.assertEqual(result["town_units"], 4)
        self.assertEqual(result["inventory_after"], -7)
        self.assertEqual([s["lower_bound"] for s in result["seats"]], [0, 0])

    def test_observation_instrumentation_is_exactly_neutral(self):
        worlds = list(oracle.explicit_worlds()) + list(oracle.random_worlds(64))
        for world in worlds:
            with self.subTest(label=world.label):
                observed, env1 = oracle.make_state(self.engine, world)
                original, env2 = oracle.make_state(self.engine, world)
                oracle.execute_phases(self.engine, observed, env1, world.step)
                oracle.execute_phases(self.engine, original, env2, world.step, instrument=False)
                self.assertEqual(oracle.result_state(observed), oracle.result_state(original))

    def test_instrumentation_restores_original_even_on_exception(self):
        state, env = oracle.make_state(self.engine, oracle.World("exception"))
        original = self.engine._commit_unit
        with patch.object(self.engine, "_process_market", side_effect=RuntimeError("test")):
            with self.assertRaisesRegex(RuntimeError, "test"):
                oracle.execute_phases(self.engine, state, env, 1)
        self.assertIs(self.engine._commit_unit, original)

    def test_seed_guard_prevents_unreported_game_initialization(self):
        with self.assertRaisesRegex(oracle.OracleFailure, "game initialization"):
            self.engine.resolve_episode_seed(None)

    def test_helper_and_engine_pins_fail_closed(self):
        for path, expected in ((ENGINE_PATH, oracle.ENGINE_BLOB), (HELPER_PATH, oracle.HELPER_BLOB),
                               (ENGINE_PATH.with_name("kaggriculture.json"), oracle.SCHEMA_BLOB)):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                poisoned = Path(temporary) / path.name
                poisoned.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(oracle.OracleFailure, "source pin mismatch"):
                    oracle.pinned_bytes(poisoned, expected)

    def test_omitted_town_subtraction_mutant_is_detected(self):
        with patch.object(self.helper, "_town_wheat_consumption", return_value=0):
            with self.assertRaisesRegex(oracle.OracleFailure, "town consumption mismatch"):
                self.evaluate(label="town-mutant", step=24, shops=("BAKERY",))

    def test_omitted_own_buy_upper_mutant_is_detected(self):
        with patch.object(self.helper, "_own_wheat_buy_upper", return_value=0):
            with self.assertRaisesRegex(oracle.OracleFailure, "own buy upper bound undercounts"):
                self.evaluate(label="self-buy-mutant", rows=([["BUY_PRODUCT", "WHEAT", 2]], []))

    def test_filter_before_cap_mutant_is_detected(self):
        with patch.object(self.helper, "_market_rows", side_effect=lambda a, cap: [r for r in a["market"] if r][:cap]):
            with self.assertRaises((oracle.OracleFailure, IndexError)):
                # Compaction makes the first real SELL disappear from its raw slot.
                obs = {"step": 1, "player": 0,
                       "market": {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}},
                       "town": {"unlocked_shops": []}}
                rider = self.helper.WheatDemandRider(enabled=True)
                rider.apply(obs, {"farmer": ["PASS"], "hands": [], "market": []})
                obs["step"] = 2
                obs["market"]["inventory"]["WHEAT"] = 9999
                parent = {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "WHEAT", 2]]}
                out = rider.apply(obs, parent)
                oracle.require(out["market"] == [[], [], ["SELL", "WHEAT", 2]],
                               "unexpected transformation decision: raw slot lost")

    def test_wrong_transition_sign_mutant_is_detected(self):
        original = self.helper._rival_wheat_buy_lower_bound
        with patch.object(self.helper, "_rival_wheat_buy_lower_bound",
                          side_effect=lambda a, b, c, d: -original(a, b, c, d)):
            with self.assertRaisesRegex(oracle.OracleFailure, "exact gross-flow identity failed"):
                self.evaluate(label="sign-mutant", rows=([], [["BUY_PRODUCT", "WHEAT", 2]]))

    def test_raw_placeholder_positive_and_capped_suffix_identity(self):
        for rows, cap, expected in (
            ([[], ["SELL", "WHEAT", 2]], 10, [[], [], ["SELL", "WHEAT", 2]]),
            ([[], ["SELL", "WHEAT", 2]], 1, None),
            ([["SELL", "WHEAT", 2], [], ["BUY_PRODUCT", "WHEAT", 2]], 2, None),
        ):
            with self.subTest(rows=rows, cap=cap):
                parent = {"market": copy.deepcopy(rows), "farmer": ["PASS"], "hands": []}
                original = copy.deepcopy(parent)
                result, moved = self.helper._relocate_wheat_sell(parent, cap)
                self.assertEqual(parent, original)
                if expected is None:
                    self.assertIs(result, parent)
                    self.assertIsNone(moved)
                else:
                    self.assertEqual(result["market"], expected)
                    self.assertEqual(moved["from_index"], 1)
                    self.assertEqual(moved["to_index"], 2)

    def test_disabled_wrapper_preserves_identity_and_state(self):
        self.helper.reset_state()
        parent = {"market": [["SELL", "WHEAT", 2]]}
        before = copy.deepcopy(self.helper.RIDER.telemetry)
        self.assertIs(self.helper.apply_c5_wheat_demand(None, parent, enabled=False), parent)
        self.assertEqual(self.helper.RIDER.players, {})
        self.assertEqual(self.helper.RIDER.telemetry, before)

    def test_cash_spend_and_raw_suffix_custody(self):
        for player in (0, 1):
            for tail in (["HIRE"], ["BUY_PRODUCT", "FERTILIZER", 1], ["BUY_SEED", "WHEAT", 1],
                         ["BUY_LAND"], ["BUY_ANIMAL", "GOOSE", 1]):
                with self.subTest(player=player, tail=tail):
                    obs = {"step": 1, "player": player,
                           "market": {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}},
                           "town": {"unlocked_shops": []}}
                    rider = self.helper.WheatDemandRider(enabled=True)
                    rider.apply(obs, {"market": []})
                    obs["step"] = 2
                    obs["market"]["inventory"]["WHEAT"] = 9998
                    parent = {"market": [["SELL", "WHEAT", 2], tail]}
                    self.assertIs(rider.apply(obs, parent), parent)

    def test_gap_rewind_and_invalid_callback_invalidate_signal(self):
        for next_step in (1, 3, 0, True, "2"):
            with self.subTest(step=next_step):
                obs = {"step": 1, "player": 0,
                       "market": {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}},
                       "town": {"unlocked_shops": []}}
                rider = self.helper.WheatDemandRider(enabled=True)
                rider.apply(obs, {"market": []})
                obs["step"] = next_step
                obs["market"]["inventory"]["WHEAT"] = 9998
                parent = {"market": [["SELL", "WHEAT", 2]]}
                self.assertIs(rider.apply(obs, parent), parent)

    def test_true_previous_signal_has_two_sided_immediate_cash_outcomes(self):
        result = oracle.paired_sale_timing(self.engine, self.helper)
        self.assertEqual(result["pairs"], 648)
        self.assertEqual((result["positive"], result["negative"], result["zero"]), (64, 76, 508))
        self.assertEqual(result["minimum_delta_cash_margin"], -9)
        self.assertEqual(result["maximum_delta_cash_margin"], 10)
        bad = result["negative_witness"]
        self.assertEqual(bad["prior_rival_buy_lower_bound"], 1)
        self.assertEqual((bad["delta_own_cash"], bad["delta_rival_cash"]), (-5, 4))
        self.assertEqual(bad["next_rival_operation"], "SELL")

    def test_seeded_corpus_is_reproducible(self):
        first = oracle.run(self.engine, self.helper, count=128)
        second = oracle.run(self.engine, self.helper, count=128)
        self.assertEqual(first, second)
        self.assertGreater(first["positive_lower_bounds"], 0)
        self.assertGreater(first["relocation_witnesses"], 0)
        self.assertEqual(first["violations"], 0)


if __name__ == "__main__":
    unittest.main()
