"""Exact-engine regressions for TITAN E10 bounded floor-state cycling."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from e10_floor_cycle import (  # noqa: E402
    FloorCycleState,
    choose_robust_pairs,
    floor_cycle_orders,
    screened_floor_cycle,
    state_changing_pair_limit,
)

EVALUATOR = HERE / "reference/evaluator/evaluate.py"
LOADER = HERE / "reference/evaluator/loader.py"
ENGINE_DIR = HERE / "reference/engine"


def pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


class FloorCycleHelperTests(unittest.TestCase):
    def test_orders_are_bounded_alternating_pairs(self):
        self.assertEqual(
            floor_cycle_orders("fertilizer", 2),
            [
                ["BUY_PRODUCT", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 1],
                ["BUY_PRODUCT", "FERTILIZER", 1],
                ["SELL", "FERTILIZER", 1],
            ],
        )
        with self.assertRaises(ValueError):
            floor_cycle_orders("CARROT", 1)
        with self.assertRaises(ValueError):
            floor_cycle_orders("WHEAT", -1)

    def test_value_screen_requires_strict_robust_downstream_gain(self):
        values = {
            0: {"seller": 100.0, "buyer": 100.0, "symmetric": 100.0},
            1: {"seller": 103.0, "buyer": 99.0, "symmetric": 102.0},
            2: {"seller": 102.0, "buyer": 101.0, "symmetric": 101.5},
        }
        decision = choose_robust_pairs(2, values)
        self.assertEqual(decision.pairs, 2)
        self.assertEqual(decision.worst_gain, 1.0)
        self.assertGreater(decision.mean_gain, 1.0)

        # A public-state change with equal downstream value is deliberately a no-op.
        flat = {0: {"terminal": 3000.0}, 1: {"terminal": 3000.0}}
        self.assertEqual(choose_robust_pairs(1, flat).pairs, 0)

        # Missing comparable scenarios cannot silently become evidence.
        incomparable = {0: {"seller": 1.0, "buyer": 1.0}, 1: {"seller": 2.0}}
        self.assertEqual(choose_robust_pairs(1, incomparable).pairs, 0)

    def test_screened_helper_never_emits_more_than_feasible_pairs(self):
        def quote(_item, inventory):
            return 1 if inventory >= 10 else 2

        state = FloorCycleState(
            item="FERTILIZER",
            inventory=12,
            cash=1,
            shed_units=0,
            shed_capacity=100,
            market_orders_used=6,
            max_market_orders=10,
            hard_pair_cap=4,
        )
        values = {
            0: {"a": 0.0, "b": 0.0},
            1: {"a": 1.0, "b": 1.0},
            2: {"a": 3.0, "b": 2.0},
            3: {"a": 100.0, "b": 100.0},  # impossible: only two pairs fit/are floor
        }
        decision, orders = screened_floor_cycle(state, quote, values)
        self.assertEqual(decision.pairs, 2)
        self.assertEqual(len(orders), 4)


class ExactEngineFloorCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("e10_floor_cycle_evaluator", EVALUATOR)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load evaluator at {EVALUATOR}")
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.hashes = cls.ev.get_engine(ENGINE_DIR, LOADER)

        # FERTILIZER has a reachable linear glut-side floor under the pinned engine.
        cls.first_floor = None
        i0 = cls.engine.MARKET_PARAMS["FERTILIZER"]["I0"]
        for inventory in range(i0, i0 + 10000):
            if cls.engine.market_price("FERTILIZER", inventory) == 1:
                cls.first_floor = inventory
                break
        if cls.first_floor is None:
            raise AssertionError("FERTILIZER floor was not found in the bounded search")

    def fixture(self, *, inventory=None, cash=1, step=1):
        e, S = self.engine, self.ev.Struct
        cfg = S({
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in e.specification["configuration"].items()
        })
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        market = e._new_market()
        if inventory is not None:
            market["inventory"]["FERTILIZER"] = inventory
            e._refresh_prices(market)
        town = {"unlocked_shops": []}
        state = []
        for seat in range(2):
            private = e._new_private()
            state.append(S(
                observation=S(
                    player=seat,
                    step=step,
                    day=step // 24,
                    hour=step % 24,
                    farms=farms,
                    private=private,
                    market=market,
                    town=town,
                ),
                action=pass_action(),
                status="ACTIVE",
                reward=0,
            ))
        return state, S(configuration=cfg, done=False, info={"seed": 9600803})

    def run_market(self, state, env, own=(), rival=()):
        state[0].action["market"] = copy.deepcopy(list(own))
        state[1].action["market"] = copy.deepcopy(list(rival))
        self.engine._process_market(state, env)

    def quote(self, item, inventory):
        return self.engine.market_price(item, inventory)

    @staticmethod
    def money(state, seat):
        return state[0].observation.farms[seat]["money"]

    @staticmethod
    def shed(state, seat, item):
        return state[seat].observation.private["shed"].get(item, 0)

    def test_01_exact_fertilizer_floor_boundary_is_pinned(self):
        self.assertEqual(self.first_floor, 10493)
        self.assertEqual(self.quote("FERTILIZER", self.first_floor - 1), 2)
        self.assertEqual(self.quote("FERTILIZER", self.first_floor), 1)

    def test_02_one_floor_pair_restores_own_cash_and_stock_but_reduces_public_inventory(self):
        start = self.first_floor + 1
        state, env = self.fixture(inventory=start, cash=1)
        before_shed = copy.deepcopy(state[0].observation.private["shed"])
        self.run_market(state, env, floor_cycle_orders("FERTILIZER", 1))
        self.assertEqual(self.money(state, 0), 1)
        self.assertEqual(state[0].observation.private["shed"], before_shed)
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], start - 1)

        feasible = state_changing_pair_limit(
            FloorCycleState("FERTILIZER", start, 1, 0, 100, 0, 10),
            self.quote,
        )
        self.assertEqual(feasible, 1)

    def test_03_above_floor_roundtrip_is_not_a_state_changing_candidate(self):
        start = self.first_floor
        state, env = self.fixture(inventory=start, cash=2)
        self.run_market(state, env, floor_cycle_orders("FERTILIZER", 1))
        self.assertEqual(self.money(state, 0), 2)
        self.assertEqual(self.shed(state, 0, "FERTILIZER"), 0)
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], start)
        self.assertEqual(
            state_changing_pair_limit(
                FloorCycleState("FERTILIZER", start, 2, 0, 100, 0, 10),
                self.quote,
            ),
            0,
        )

    def test_04_cash_capacity_slots_and_illegal_product_clip_the_candidate(self):
        start = self.first_floor + 2
        base = dict(
            item="FERTILIZER",
            inventory=start,
            cash=1,
            shed_units=0,
            shed_capacity=100,
            market_orders_used=6,
            max_market_orders=10,
            hard_pair_cap=4,
        )
        self.assertEqual(state_changing_pair_limit(FloorCycleState(**base), self.quote), 2)
        self.assertEqual(
            state_changing_pair_limit(FloorCycleState(**{**base, "market_orders_used": 7}), self.quote),
            1,
        )
        self.assertEqual(
            state_changing_pair_limit(FloorCycleState(**{**base, "market_orders_used": 9}), self.quote),
            0,
        )
        self.assertEqual(
            state_changing_pair_limit(FloorCycleState(**{**base, "cash": 0}), self.quote),
            0,
        )
        self.assertEqual(
            state_changing_pair_limit(FloorCycleState(**{**base, "shed_units": 100}), self.quote),
            0,
        )
        self.assertEqual(
            state_changing_pair_limit(FloorCycleState(**{**base, "item": "CARROT"}), self.quote),
            0,
        )

        # Exact transition receipt for the full-shed rejection.
        full, fenv = self.fixture(inventory=start, cash=1)
        full[0].observation.private["shed"]["WHEAT"] = 100
        self.run_market(full, fenv, floor_cycle_orders("FERTILIZER", 1))
        self.assertEqual(self.money(full, 0), 1)
        self.assertEqual(self.shed(full, 0, "FERTILIZER"), 0)
        self.assertEqual(full[0].observation.market["inventory"]["FERTILIZER"], start)

    def test_05_one_pair_can_change_a_later_rival_buy_without_changing_own_cash(self):
        start = self.first_floor + 1
        rival_orders = [["SELL", "MILK", 1], ["BUY_PRODUCT", "FERTILIZER", 1]]

        baseline, benv = self.fixture(inventory=start, cash=1)
        self.run_market(baseline, benv, (), rival_orders)
        self.assertEqual(self.money(baseline, 1), 0)
        self.assertEqual(self.shed(baseline, 1, "FERTILIZER"), 1)

        cycle, cenv = self.fixture(inventory=start, cash=1)
        self.run_market(cycle, cenv, floor_cycle_orders("FERTILIZER", 1), rival_orders)
        self.assertEqual(self.money(cycle, 0), 1)
        self.assertEqual(self.shed(cycle, 0, "FERTILIZER"), 0)
        self.assertEqual(self.money(cycle, 1), 1)
        self.assertEqual(self.shed(cycle, 1, "FERTILIZER"), 0)
        # Public inventory is the same in both cases: the economic distinction is
        # the rival acquisition, not a proxy reward for moving the market counter.
        self.assertEqual(
            baseline[0].observation.market["inventory"]["FERTILIZER"],
            cycle[0].observation.market["inventory"]["FERTILIZER"],
        )

    def test_06_two_pairs_can_cross_the_downstream_quote_boundary_where_one_pair_cannot(self):
        start = self.first_floor + 2
        rival_orders = [
            ["SELL", "MILK", 1],
            ["SELL", "MILK", 1],
            ["SELL", "MILK", 1],
            ["BUY_PRODUCT", "FERTILIZER", 1],
        ]
        rival_acquired = {}
        for pairs in (0, 1, 2):
            state, env = self.fixture(inventory=start, cash=1)
            self.run_market(state, env, floor_cycle_orders("FERTILIZER", pairs), rival_orders)
            rival_acquired[pairs] = self.shed(state, 1, "FERTILIZER")
            self.assertEqual(self.money(state, 0), 1)
            self.assertEqual(self.shed(state, 0, "FERTILIZER"), 0)
        self.assertEqual(rival_acquired, {0: 1, 1: 1, 2: 0})
        self.assertEqual(
            state_changing_pair_limit(
                FloorCycleState("FERTILIZER", start, 1, 0, 100, 0, 10, 2),
                self.quote,
            ),
            2,
        )

    def test_07_paired_rival_cycles_use_precommit_quotes_and_restore_both_own_states(self):
        start = self.first_floor + 2
        state, env = self.fixture(inventory=start, cash=1)
        orders = floor_cycle_orders("FERTILIZER", 1)
        self.run_market(state, env, orders, orders)
        self.assertEqual([self.money(state, seat) for seat in (0, 1)], [1, 1])
        self.assertEqual([self.shed(state, seat, "FERTILIZER") for seat in (0, 1)], [0, 0])
        self.assertEqual(state[0].observation.market["inventory"]["FERTILIZER"], start - 2)

    def test_08_terminal_public_state_change_has_zero_terminal_cash_value_and_screens_to_noop(self):
        start = self.first_floor + 1
        baseline, benv = self.fixture(inventory=start, cash=1, step=718)
        cycle, cenv = self.fixture(inventory=start, cash=1, step=718)
        cycle[0].action["market"] = floor_cycle_orders("FERTILIZER", 1)
        self.engine.interpreter(baseline, benv)
        self.engine.interpreter(cycle, cenv)
        self.assertEqual([s.status for s in baseline], ["DONE", "DONE"])
        self.assertEqual([s.status for s in cycle], ["DONE", "DONE"])
        self.assertEqual(cycle[0].reward, baseline[0].reward)
        self.assertEqual(self.money(cycle, 0), self.money(baseline, 0))
        self.assertEqual(self.shed(cycle, 0, "FERTILIZER"), self.shed(baseline, 0, "FERTILIZER"))
        self.assertEqual(
            cycle[0].observation.market["inventory"]["FERTILIZER"],
            baseline[0].observation.market["inventory"]["FERTILIZER"] - 1,
        )
        terminal_values = {
            0: {"terminal_cash": float(baseline[0].reward)},
            1: {"terminal_cash": float(cycle[0].reward)},
        }
        self.assertEqual(choose_robust_pairs(1, terminal_values).pairs, 0)


if __name__ == "__main__":
    unittest.main()
