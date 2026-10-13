# SPDX-License-Identifier: Apache-2.0
"""Independent price-window counterexamples; no production forecast ownership.

python [-O] test_price_window_engine_evidence.py --engine kaggriculture.py [-v]
Optional --candidate path loads QUINCE's tomato_price contract for comparison.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import importlib.util
import hashlib
import itertools
import sys
from pathlib import Path
import random
import tempfile
import unittest

from price_window_engine_evidence import load_engine, state_for, natural_snapshot, execute_sale

ENGINE = None
ENGINE_PATH = None
CANDIDATE = None


class EngineEvidenceTests(unittest.TestCase):
    def test_exact_source_required(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wrong.py"
            path.write_text("raise RuntimeError('must not execute')\n")
            with self.assertRaisesRegex(ValueError, "blob mismatch"):
                load_engine(path)

    def test_real_interpreter_market_before_consumption_before_unlock(self):
        tree = ast.parse(ENGINE_PATH.read_bytes())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "interpreter")
        calls = {n.func.id: n.lineno for n in ast.walk(node)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id in ("_process_market", "_town_consume", "_end_of_day")}
        self.assertLess(calls["_process_market"], calls["_town_consume"])
        self.assertLess(calls["_town_consume"], calls["_end_of_day"])

    def test_real_eod_unlock_calendar(self):
        state, env = state_for(ENGINE)
        for day in range(30):
            ENGINE._end_of_day(state, env, day)
            self.assertEqual(len(state[0].observation.town["unlocked_shops"]), min(8, (day + 1) // 3))

    def test_interpreter_first_unlock_after_step71(self):
        state, env = state_for(ENGINE)
        for step in range(72):
            for row in state:
                row.observation.step = step
            ENGINE.interpreter(state, env)
            self.assertEqual(len(state[0].observation.town["unlocked_shops"]), int(step == 71))
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9997)

    def test_real_final_action_718(self):
        state, env = state_for(ENGINE, inventory=9275, quantity=1)
        for row in state:
            row.observation.step = 718
        state[0].action = {"market": [["SELL", "TOMATO", 1]]}
        ENGINE.interpreter(state, env)
        self.assertEqual(state[0].reward, 4470.0)
        self.assertEqual([r.status for r in state], ["DONE", "DONE"])

    def test_step717_is_not_done(self):
        state, env = state_for(ENGINE)
        for row in state:
            row.observation.step = 717
        ENGINE.interpreter(state, env)
        self.assertEqual([r.status for r in state], ["ACTIVE", "ACTIVE"])

    def test_quote1470_inventory_boundary(self):
        self.assertEqual(ENGINE.market_price("TOMATO", 9275), 1470)
        self.assertLess(ENGINE.market_price("TOMATO", 9276), 1470)
        self.assertGreater(ENGINE.market_price("TOMATO", 9274), 1470)

    def test_negative_public_stock_is_legal(self):
        state, env = state_for(ENGINE, ["PIZZA_SHOP"], inventory=0)
        ENGINE._town_consume(env, state, 0)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], -2)
        self.assertGreater(execute_sale(ENGINE, state, env, 25)["minimum_unit_quote"], 1470)

    def test_tomato_buy_is_not_executable(self):
        state, env = state_for(ENGINE, inventory=9275)
        state[0].action = {"market": [["BUY_PRODUCT", "TOMATO", 25]]}
        ENGINE._process_market(state, env)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9275)
        self.assertEqual(state[0].observation.private["shed"]["TOMATO"], 0)
        self.assertEqual(state[0].observation.farms[0]["money"], 3000)

    def test_floor_sale_does_not_create_public_inventory(self):
        state, env = state_for(ENGINE, inventory=100000)
        lot = execute_sale(ENGINE, state, env, 25)
        self.assertEqual(lot["total_revenue"], 25)
        self.assertEqual(lot["inventory_after"], 100000)

    def test_sale_does_not_mutate_supplied_snapshot(self):
        state, env = state_for(ENGINE, inventory=9275, quantity=12)
        old = deepcopy(state)
        execute_sale(ENGINE, state, env, 25, extra=50)
        self.assertEqual(state, old)

    def test_both_seats_same_single_seller_mechanism(self):
        state, env = state_for(ENGINE, inventory=9275)
        self.assertEqual(execute_sale(ENGINE, state, env, 25, seat=0),
                         execute_sale(ENGINE, state, env, 25, seat=1))

    def test_duplicate_pizza_and_market_instances_count(self):
        state, env = state_for(ENGINE, ["PIZZA_SHOP", "PIZZA_SHOP", "FARMERS_MARKET"])
        ENGINE._town_consume(env, state, 0)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9996)

    def test_non_tomato_shops_have_no_tomato_demand(self):
        shops = [s for s, products in ENGINE.SHOPS.items() if "TOMATO" not in products]
        state, env = state_for(ENGINE, shops)
        ENGINE._town_consume(env, state, 4)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 10000)

    def test_custom_consumption_intervals_execute(self):
        state, env = state_for(ENGINE, ["FARMERS_MARKET"],
                               configuration={"townShopSellInterval": 7, "townCenterSellInterval": 11})
        for step in range(80):
            ENGINE._town_consume(env, state, step)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 10000 - 12 - 8)

    def test_one_turn_phase_boundary_can_falsely_pass_threshold(self):
        state, env = state_for(ENGINE, ["FARMERS_MARKET"] * 4, inventory=9279)
        before = ENGINE.market_price("TOMATO", 9279)
        lot = execute_sale(ENGINE, state, env, 1)
        ENGINE._town_consume(env, state, 692)
        self.assertLess(before, 1470)
        self.assertEqual(lot["total_revenue"], before)
        self.assertEqual(state[0].observation.market["prices"]["TOMATO"], 1470)

    def test_no_shops_still_consume30_center_units(self):
        state, env = natural_snapshot(ENGINE, [False] * 8)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9970)

    def test_four_natural_shops_cap_at786_not1470(self):
        state, env = natural_snapshot(ENGINE, [True] * 4 + [False] * 4)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9430)
        lot = execute_sale(ENGINE, state, env, 25)
        self.assertEqual((lot["first_quote"], lot["minimum_unit_quote"], lot["total_revenue"]), (786, 700, 18561))

    def test_six_natural_shops_spot_is_not_lot_floor(self):
        state, env = natural_snapshot(ENGINE, [True] * 6 + [False] * 2)
        lot = execute_sale(ENGINE, state, env, 25)
        self.assertEqual((lot["first_quote"], lot["minimum_unit_quote"], lot["total_revenue"]), (1506, 1384, 36116))
        self.assertEqual(lot["spot_times_quantity_overstatement"], 1534)

    def test_eight_earliest_shops_upper_bound(self):
        state, env = natural_snapshot(ENGINE, [True] * 8)
        self.assertEqual(state[0].observation.market["inventory"]["TOMATO"], 9178)
        lot = execute_sale(ENGINE, state, env, 25)
        self.assertEqual((lot["first_quote"], lot["minimum_unit_quote"]), (2016, 1872))

    def test100_extra_supply_kills_even_maximum_natural_spot(self):
        state, env = natural_snapshot(ENGINE, [True] * 8)
        lot = execute_sale(ENGINE, state, env, 25, extra=100)
        self.assertLess(lot["first_quote"], 1470)
        self.assertLess(lot["minimum_unit_quote"], 1470)

    def test_static_four_spot693_vs_lot717(self):
        state, env = state_for(ENGINE, ["FARMERS_MARKET"] * 4)
        first_spot = first_lot = None
        for step in range(719):
            lot = execute_sale(ENGINE, state, env, 25)
            if first_spot is None and lot["first_quote"] >= 1470:
                first_spot = step
            if first_lot is None and lot["minimum_unit_quote"] >= 1470:
                first_lot = step
            if step < 718:
                ENGINE._town_consume(env, state, step)
        self.assertEqual((first_spot, first_lot), (693, 717))

    def test_executable_prefix_does_not_compact_dead11th_sell(self):
        state, env = state_for(ENGINE, inventory=9275, quantity=25)
        state[0].action = {"market": [["PASS"]] * 10 + [["SELL", "TOMATO", 25]]}
        ENGINE._process_market(state, env)
        self.assertEqual(state[0].observation.farms[0]["money"], 3000)
        self.assertEqual(state[0].observation.private["shed"]["TOMATO"], 25)

    def test_100_real_random_lots_reconcile(self):
        rng = random.Random(9011470)
        for _ in range(100):
            state, env = state_for(ENGINE, inventory=rng.randrange(-1000, 30000))
            lot = execute_sale(ENGINE, state, env, rng.randrange(1, 101), extra=rng.randrange(101))
            self.assertGreaterEqual(lot["first_quote"], lot["minimum_unit_quote"])
            self.assertGreaterEqual(lot["spot_times_quantity_overstatement"], 0)

    def test_optional_existing_candidate_quote_contract(self):
        if CANDIDATE is None:
            self.skipTest("provide --candidate for QUINCE source contract; engine evidence remains separate")
        for inventory in range(-1000, 30001, 7):
            self.assertEqual(CANDIDATE.tomato_price(inventory), ENGINE.market_price("TOMATO", inventory), inventory)


    def candidate(self):
        if CANDIDATE is None:
            self.skipTest("provide --candidate for existing QUINCE forecast contract")
        return CANDIDATE

    @staticmethod
    def public_obs(state):
        obs = state[0].observation
        return dict(step=obs.step, market=deepcopy(obs.market), town=deepcopy(obs.town))

    def test_candidate256_natural_masks_from_known_shop_snapshot(self):
        candidate = self.candidate()
        for mask in itertools.product((False, True), repeat=8):
            state, env = natural_snapshot(ENGINE, mask, stop=600)
            result = candidate.forecast_window(self.public_obs(state), horizon=118, threshold=1470)
            self.assertIsNotNone(result)
            for step in range(600, 718):
                ENGINE._town_consume(env, state, step)
            self.assertEqual(result["projected_inventory"], state[0].observation.market["inventory"]["TOMATO"])
            self.assertEqual(result["projected_price"], state[0].observation.market["prices"]["TOMATO"])
            self.assertEqual(result["horizon_step"], 718)
            self.assertFalse(result["executable_trade"])

    def test_candidate_event_tick_is_not_available_to_same_turn_sale(self):
        candidate = self.candidate()
        state, env = state_for(ENGINE, ["FARMERS_MARKET"] * 4, inventory=9279)
        state[0].observation.step = 692
        obs = self.public_obs(state)
        same_turn = candidate.forecast_window(obs, horizon=0, threshold=1470)
        next_turn = candidate.forecast_window(obs, horizon=1, threshold=1470)
        self.assertIsNone(same_turn["threshold_crossing_step"])
        self.assertEqual(next_turn["threshold_crossing_step"], 693)
        self.assertEqual(next_turn["projected_price"], 1470)
        self.assertEqual(execute_sale(ENGINE, state, env, 1)["total_revenue"], same_turn["current_price"])

    def test_candidate_spot_budget_is_not_25_unit_budget(self):
        candidate = self.candidate()
        state, env = natural_snapshot(ENGINE, [True] * 6 + [False] * 2, stop=600)
        result = candidate.forecast_window(self.public_obs(state), horizon=118, threshold=1470)
        self.assertEqual(result["additional_supply_budget_at_horizon"], 7)
        final, env = natural_snapshot(ENGINE, [True] * 6 + [False] * 2)
        self.assertLess(execute_sale(ENGINE, final, env, 25)["minimum_unit_quote"], 1470)
        self.assertFalse(result["trigger"])  # planting at600 cannot yield before718

    def test_candidate_maximum_natural_supply_boundary_is97_not100(self):
        candidate = self.candidate()
        state, env = natural_snapshot(ENGINE, [True] * 8, stop=600)
        result = candidate.forecast_window(self.public_obs(state), horizon=118, threshold=1470)
        self.assertEqual(result["additional_supply_budget_at_horizon"], 97)
        final, env = natural_snapshot(ENGINE, [True] * 8)
        self.assertEqual(execute_sale(ENGINE, final, env, 1, extra=97)["first_quote"], 1470)
        self.assertLess(execute_sale(ENGINE, final, env, 1, extra=98)["first_quote"], 1470)

    def test_candidate_static_crossing_is_not_a_plant_now_trigger(self):
        candidate = self.candidate()
        state, env = state_for(ENGINE, ["FARMERS_MARKET"] * 4)
        result = candidate.forecast_window(self.public_obs(state), horizon=718, threshold=1470)
        self.assertEqual(result["threshold_crossing_step"], 693)
        self.assertEqual(result["plant_now_first_yield_step"], 192)
        self.assertFalse(result["trigger"])
        self.assertFalse(result["executable_trade"])

    def test_candidate_does_not_backdate_unseen_future_shops(self):
        candidate = self.candidate()
        state, env = natural_snapshot(ENGINE, [True] * 8, stop=71)
        result = candidate.forecast_window(self.public_obs(state), horizon=647, threshold=1470)
        self.assertEqual(result["tomato_shop_instances"], 0)
        self.assertEqual(result["projected_inventory"], 9970)
        self.assertIsNone(result["threshold_crossing_step"])

    def test_candidate_does_not_mutate_public_snapshot(self):
        candidate = self.candidate()
        state, env = natural_snapshot(ENGINE, [True] * 8, stop=600)
        obs = self.public_obs(state)
        old = deepcopy(obs)
        candidate.forecast_window(obs, horizon=118, threshold=1470)
        self.assertEqual(obs, old)


def main():
    global ENGINE, ENGINE_PATH, CANDIDATE
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--expected-candidate-blob", default="df9e770ff4408e8b25131b66850ffbd561778e65")
    args, rest = parser.parse_known_args()
    ENGINE_PATH = args.engine
    ENGINE = load_engine(args.engine)
    if args.candidate:
        raw = args.candidate.read_bytes()
        actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if actual != args.expected_candidate_blob:
            raise ValueError(f"candidate blob mismatch: {actual}")
        spec = importlib.util.spec_from_file_location("quince_tomato_window", args.candidate)
        CANDIDATE = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = CANDIDATE
        spec.loader.exec_module(CANDIDATE)
    unittest.main(argv=[__file__, *rest])


if __name__ == "__main__":
    main()
