"""Cash-trough regression and whole-queue official-interpreter differentials.

T10_SOURCEPACK must name the already-verified pinned source pack. No downloads,
new games, hidden seeds or alteration of the shared engine's globals.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import unittest

import labor_capital as lc

ROOT = Path(os.environ["T10_SOURCEPACK"]).resolve()
BASE = ROOT / "commons/revenue/kaggriculture"
spec = importlib.util.spec_from_file_location(
    "t10_cash_engine_loader", BASE / "cloud-eval/evaluate.py")
ev = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ev
spec.loader.exec_module(ev)
ENGINE, HASHES = ev.get_engine(ROOT / "engine")
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


class PassParent:
    def act(self, obs):
        return copy.deepcopy(PASS)


class CashObservedFarm(dict):
    """Observe genuine engine money writes, without replacing market functions."""
    def __init__(self, farm, samples):
        super().__init__(farm)
        self.samples = samples

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "money":
            self.samples.append(float(value))


def observation(*, step=718, money=100, seat=0, eggs=2):
    farms = [ENGINE._new_farm(10, money) for _ in range(2)]
    own = ENGINE._new_private()
    own["shed"]["EGG"] = eggs
    return lc.View(step=step, day=step // 24, hour=step % 24, player=seat,
                   farms=farms, private=own, market=ENGINE._new_market(),
                   town=ENGINE._new_town())


def actual_whole_turn(obs, action, configuration=None):
    """Run one complete, unchanged official interpreter call and observe cash."""
    cfg = lc._configuration(configuration)
    states, me = lc._own_state(ENGINE, obs)
    samples = [float(states[me].observation.farms[me]["money"])]
    farm = CashObservedFarm(states[me].observation.farms[me], samples)
    states[me].observation.farms[me] = farm
    for state in states:
        state.observation.update(step=obs["step"], day=obs["step"] // cfg.turnsPerDay,
                                 hour=obs["step"] % cfg.turnsPerDay)
    states[me].action = copy.deepcopy(action)
    # The cases stop at decision718, not a random daily refresh. This environment
    # deliberately has no seed or replay information to expose to a policy.
    env = lc.View(configuration=cfg, done=False, info={})
    ENGINE.interpreter(states, env)
    return states, me, samples


class CashTroughTests(unittest.TestCase):
    def projection(self, obs, queue, cfg=None):
        return lc.project_shift(ENGINE, obs, PassParent(),
                                dict(PASS, market=queue), cfg)

    def test_buy_then_sell_retains_lower_intermediate_balance(self):
        result = self.projection(observation(),
            [["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 80)
        self.assertEqual(result.estimated_cash, 179)
        # Existing NET non-hire fields keep their documented meaning.
        self.assertEqual(result.net_nonhire_inflow, 79)
        self.assertEqual(result.net_nonhire_outflow, 0)

    def test_rising_hire_cost_trough_precedes_sale(self):
        obs = observation(money=233)
        obs.farms[0]["hires_today"] = 12
        result = self.projection(obs, [["HIRE"], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 0)
        self.assertEqual(result.hiring_outflow, 233)
        self.assertEqual(result.successful_hires, 1)
        self.assertEqual(result.estimated_cash, 99)

    def test_buy_land_then_sell(self):
        result = self.projection(observation(money=1100),
                                 [["BUY_LAND"], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 100)
        self.assertEqual(result.estimated_cash, 199)
        self.assertIn("NE", result.productive_state["farm"]["unlocked_quadrants"])

    def test_partial_fill_endpoint_is_the_real_trough(self):
        result = self.projection(observation(money=85),
                                 [["BUY_SEED", "CARROT", 9], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 5)
        self.assertEqual(result.productive_state["private"]["seeds"]["CARROT"], 4)
        self.assertEqual(result.estimated_cash, 104)

    def test_sell_before_purchase_is_not_reordered(self):
        result = self.projection(observation(),
                                 [["SELL", "EGG", 2], ["BUY_SEED", "CARROT", 1]])
        self.assertEqual(result.minimum_cash, 100)
        self.assertEqual(result.estimated_cash, 179)

    def test_failed_purchase_has_no_hypothetical_cash_effect(self):
        result = self.projection(observation(money=19),
                                 [["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 19)
        self.assertEqual(result.estimated_cash, 118)

    def test_order_cap_is_applied_before_slot_execution(self):
        queue = [["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2], ["BUY_SEED", "CARROT", 8]]
        result = self.projection(observation(), queue, {"maxMarketOrdersPerTurn": 2})
        self.assertEqual(result.minimum_cash, 80)
        self.assertEqual(result.estimated_cash, 179)
        self.assertEqual(result.productive_state["private"]["seeds"]["CARROT"], 1)

    def test_empty_and_invalid_slots_do_not_shift_the_cap(self):
        queue = [None, ["SELL", "WHEAT", 0], ["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]]
        result = self.projection(observation(), queue, {"maxMarketOrdersPerTurn": 3})
        self.assertEqual(result.minimum_cash, 80)
        self.assertEqual(result.estimated_cash, 80)
        for invalid in (None, "not a list", {"type": "HIRE"}, []):
            with self.subTest(invalid=invalid):
                result = self.projection(observation(), invalid)
                self.assertEqual(result.minimum_cash, 100)
                self.assertEqual(result.estimated_cash, 100)

    def test_other_seat_uses_only_own_cash(self):
        obs = observation(seat=1)
        obs.farms[0]["money"] = 9999
        result = self.projection(obs, [["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 80)
        self.assertEqual(result.estimated_cash, 179)
        self.assertEqual(obs.farms[0]["money"], 9999)

    def test_day_boundary_trough_survives_daily_reset(self):
        obs = observation(step=23)
        result = self.projection(obs, [["HIRE"], ["SELL", "EGG", 2]])
        self.assertEqual(result.minimum_cash, 99)
        self.assertEqual(result.estimated_cash, 198)
        self.assertEqual(result.productive_state["farm"]["hands"], [])
        self.assertEqual(result.productive_state["farm"]["hires_today"], 0)

    def test_minimum_carries_across_later_turns(self):
        class LaterSale:
            def act(self, obs):
                return dict(PASS, market=[["SELL", "EGG", 2]])
        obs = observation(step=717)
        result = lc.project_shift(ENGINE, obs, LaterSale(),
                                  dict(PASS, market=[["BUY_SEED", "CARROT", 1]]))
        self.assertEqual(result.minimum_cash, 80)
        self.assertEqual(result.estimated_cash, 179)

    def test_original_action_restored_on_market_exception(self):
        class FailingMarket:
            def __getattr__(self, name):
                return getattr(ENGINE, name)
            def _process_market(self, states, env):
                self.states = states
                raise RuntimeError("injected market failure")
        engine = FailingMarket()
        action = dict(PASS, market=[["HIRE"], ["SELL", "EGG", 2]])
        with self.assertRaisesRegex(RuntimeError, "injected market"):
            lc.project_shift(engine, observation(), PassParent(), action)
        self.assertEqual(engine.states[0].action, action)

    def test_observation_action_and_engine_globals_remain_unchanged(self):
        obs = observation()
        action = dict(PASS, market=[["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]])
        expected = copy.deepcopy((obs, action))
        function_refs = {k: v for k, v in vars(ENGINE).items() if callable(v)}
        lc.project_shift(ENGINE, obs, PassParent(), action)
        self.assertEqual((obs, action), expected)
        self.assertEqual({k: v for k, v in vars(ENGINE).items() if callable(v)}, function_refs)

    def test_240_generated_queues_match_unsplit_official_interpreter(self):
        # A local fixture generator, not an episode seed or a policy input.
        rng = random.Random(47021)
        order_pool = [["HIRE"], ["BUY_LAND"], ["BUY_SEED", "CARROT", 4],
                      ["BUY_SEED", "WHEAT", 1], ["BUY_ANIMAL", "GOOSE", 2],
                      ["BUY_PRODUCT", "WHEAT", 3], ["BUY_PRODUCT", "FERTILIZER", 2],
                      ["SELL", "EGG", 2], ["SELL", "MILK", 4], ["SELL", "WHEAT", 5],
                      ["SELL", "WHEAT", 0], ["UNKNOWN"], None, []]
        for index in range(240):
            obs = observation(money=rng.choice([0, 19, 85, 100, 233, 1100, 3100]), seat=index % 2)
            obs.private["shed"].update(EGG=rng.randrange(7), MILK=rng.randrange(7), WHEAT=rng.randrange(7))
            obs.private["inventories"][0].update(EGG=3, WHEAT=2)
            obs.farms[index % 2]["hires_today"] = rng.randrange(14)
            obs.market["inventory"]["MILK"] += rng.choice([0, 400])
            ENGINE._refresh_prices(obs.market)
            queue = [copy.deepcopy(rng.choice(order_pool)) for _ in range(rng.randrange(1, 14))]
            action = {"farmer": [rng.choice(["PASS", "DROP", "WEST"])], "hands": [], "market": queue}
            cfg = {"maxMarketOrdersPerTurn": rng.choice([1, 2, 5, 10]),
                   "farmHandCostMult": rng.choice([0, 1, 2]),
                   "shedCapacity": rng.choice([5, 20, 100])}
            with self.subTest(case=index, seat=obs.player):
                result = lc.project_shift(ENGINE, obs, PassParent(), action, cfg)
                states, me, samples = actual_whole_turn(obs, action, cfg)
                farm = states[me].observation.farms[me]
                self.assertEqual(result.minimum_cash, min(samples))
                self.assertEqual(result.estimated_cash, farm["money"])
                self.assertEqual(result.productive_state["farm"],
                                 {k: v for k, v in farm.items() if k != "money"})
                self.assertEqual(result.productive_state["private"], states[me].observation.private)
                self.assertEqual(result.market_inventory, states[me].observation.market["inventory"])
                self.assertEqual(states[me].status, "DONE")


if __name__ == "__main__":
    unittest.main()
