"""Focused execution-scheduler regressions against the pinned official engine.

Synthetic controller actions are explicit fixtures, not policy-strength evidence.
The production scheduler and evaluator sources remain unchanged by these tests.
"""
from __future__ import annotations

import copy
import unittest

import scheduler as s
import test_engine_semantics as semantics


class FixedController:
    """An explicit ordered tape fixture for testing the wrapper's contract."""
    def __init__(self, now, action, future=None):
        self.cur = "fixture"
        self.R = {self.cur: [semantics.pass_agent({}) for _ in range(720)]}
        self.R[self.cur][now] = copy.deepcopy(action)
        for t, a in (future or {}).items():
            self.R[self.cur][t] = copy.deepcopy(a)

    def act(self, obs):
        return copy.deepcopy(self.R[self.cur][int(obs["step"])])

    def future_sells(self, item, step):
        return sum(int(o[2]) for a in self.R[self.cur][step:]
                   for o in a.get("market", []) if o[:2] == ["SELL", item])


class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        semantics.EngineSemantics.setUpClass()
        cls.helper = semantics.EngineSemantics()
        cls.engine = cls.helper.engine

    def fixture(self, **kwargs):
        return self.helper.fixture(**kwargs)

    def scheduler(self, now, action, future=None):
        agent = s.SellScheduler()
        agent.controller = FixedController(now, action, future)
        return agent

    def test_joint_floor_quotes_match_official_order_alignment(self):
        for alignment in ("paired", "before", "after"):
            with self.subTest(alignment=alignment):
                state, env = self.fixture(stock=(2, 2), inventory=10075)
                own = [["SELL", "MILK", 2]]
                rival = [["SELL", "MILK", 2]]
                if alignment == "before":
                    own.insert(0, [])
                elif alignment == "after":
                    rival.insert(0, [])
                self.helper.market(state, env, own, rival)
                path = s.MarketPath("MILK", 10075, None, [], {}, 1, 2)
                model = path.joint(10075, 2, 2, alignment)
                self.assertEqual(list(model[:2]), self.helper.cash(state))
                self.assertEqual(model[2], state[0].observation.market["inventory"]["MILK"])

    def test_relative_objective_rejects_own_cash_only_delay_gain(self):
        shops = ["SMOOTHIE_SHOP", "FARMERS_MARKET", "ICE_CREAM_SHOP",
                 "FARMERS_MARKET", "ICE_CREAM_SHOP"]
        path = s.MarketPath("STRAWBERRY", 10008, None, shops, {}, 625, 629)
        immediate = path.score(((625, 24),), 24, 3, "after")
        delayed = path.score(((629, 24),), 24, 3, "after")
        self.assertEqual(immediate[:3], (1810, 1981, 171))
        self.assertEqual(delayed[:3], (1765, 2074, 309))
        self.assertGreater(delayed[1], immediate[1])
        self.assertLess(delayed[0], immediate[0])
        plan, info = s.optimize_lot(item="STRAWBERRY", quantity=24, inventory=10008,
                                   params=None, shops=shops, config={}, now=625,
                                   dates=[625, 629], reference=((625, 24),),
                                   rival_quantity=3)
        self.assertGreater(dict(plan).get(625, 0), 0)
        for scenario in info["scenarios"].values():
            self.assertGreaterEqual(scenario["relative_value"],
                                    scenario["reference_relative_value"])

    def test_short_horizon_carries_inventory_but_match_end_has_zero_salvage(self):
        path = s.MarketPath("MILK", 10000, None, [], {}, 10, 18)
        carried = path.score((), 5, 0, "paired", terminal=False)
        terminal = path.score((), 5, 0, "paired", terminal=True)
        self.assertEqual(carried[1:], (0, 0, 5))
        self.assertGreater(carried[0], 0)
        self.assertEqual(terminal, (0, 0, 0, 5))

    def test_post_units_projects_pickup_before_later_drop(self):
        state, env = self.fixture(stock=(90, 0), step=1)
        obs = state[0].observation
        obs.private["shed"]["WHEAT"] = 10
        obs.farms[0]["hands"] = [[5, 4]]
        obs.private["inventories"] = [{}, {"MILK": 10}]
        action = {"farmer": ["PICKUP", "WHEAT", 10], "hands": [["DROP"]], "market": []}
        before = copy.deepcopy(obs)
        farm, private = s.post_units(obs, action, env.configuration)
        self.assertEqual(obs, before, "Projection must leave the live observation intact")
        self.assertEqual(private["shed"]["WHEAT"], 0)
        self.assertEqual(private["shed"]["MILK"], 100)
        self.assertEqual(private["inventories"], [{"WHEAT": 10}, {}])
        state[0].action = action
        self.engine.interpreter(state, env)
        self.assertEqual(private, state[0].observation.private)
        self.assertEqual(farm, state[0].observation.farms[0])

    def test_capacity_profile_distinguishes_drop_from_eod_arrival(self):
        base = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 10]]}
        for drop in (False, True):
            with self.subTest(drop=drop):
                state, env = self.fixture(stock=(10, 0), step=22, cash=10000)
                obs = state[0].observation
                obs.private["shed"]["WHEAT"] = 85
                obs.private["inventories"] = [{"MILK": 10}]
                future = {23: {"farmer": ["DROP"] if drop else ["PASS"],
                               "hands": [], "market": []}}
                agent = self.scheduler(22, base, future)
                farm, private = s.post_units(obs, base, env.configuration)
                feasible = agent.receipt_profile(obs, base, farm, private, 23, "MILK", env.configuration)
                self.assertTrue(feasible(((22, 10),)))
                self.assertFalse(feasible(()))
                if drop:
                    self.assertFalse(feasible(((23, 10),)),
                                     "A later market cannot rescue earlier DROP overflow")
                else:
                    self.assertTrue(feasible(((23, 6),)),
                                    "Market space is available to later EOD deposits")

    def test_current_sales_preserve_low_cash_operating_orders(self):
        state, env = self.fixture(stock=(12, 0), inventory=9978, step=195, cash=357)
        obs = state[0].observation
        obs.farms[0]["hires_today"] = 9
        obs.private["shed"]["WHEAT"] = 3
        base = {"farmer": ["PASS"], "hands": [],
                "market": [["SELL", "MILK", 12], ["HIRE"],
                           ["BUY_PRODUCT", "WHEAT", 3],
                           ["BUY_SEED", "STRAWBERRY", 2],
                           ["BUY_ANIMAL", "COW", 1], ["BUY_ANIMAL", "SHEEP", 2]]}
        agent = self.scheduler(195, base)
        out = agent.act(obs, env.configuration)
        self.assertEqual(out["farmer"], base["farmer"])
        self.assertEqual(out["hands"], base["hands"])
        self.assertEqual([o for o in out["market"] if o[0] != "SELL"], base["market"][1:])
        reference = copy.deepcopy(state)
        reference[0].action = base
        state[0].action = out
        self.engine._process_market(reference, copy.deepcopy(env))
        self.engine._process_market(state, env)
        self.assertEqual(state[0].observation.private["shed"]["COW"], 1)
        self.assertEqual(state[0].observation.private["shed"]["SHEEP"], 2)
        self.assertEqual(state[0].observation.private["seeds"], reference[0].observation.private["seeds"])
        self.assertEqual(state[0].observation.farms[0]["hires_today"],
                         reference[0].observation.farms[0]["hires_today"])

    def test_pending_sale_replans_for_capacity_even_without_receipt_gain(self):
        state, env = self.fixture(stock=(10, 0), step=22, cash=10000)
        obs = state[0].observation
        obs.private["shed"]["WHEAT"] = 85
        obs.private["inventories"] = [{"MILK": 10}]
        base = {"farmer": ["PASS"], "hands": [], "market": []}
        future = {23: {"farmer": ["DROP"], "hands": [], "market": []}}
        agent = self.scheduler(22, base, future)
        agent.pending = {"MILK": 10}
        agent.planned = {"MILK": [(23, 10)]}
        farm, private = s.post_units(obs, base, env.configuration)
        feasible = agent.receipt_profile(obs, base, farm, private, 23, "MILK", env.configuration)
        self.assertFalse(feasible(((23, 10),)))
        self.assertTrue(feasible(((22, 6), (23, 4))))
        out = agent.act(obs, env.configuration)
        now_sales = sum(o[2] for o in out["market"] if o and o[:2] == ["SELL", "MILK"])
        self.assertGreaterEqual(now_sales, 6,
                                "An infeasible pending reference cannot outrank a feasible equal-value replan")

    def test_cash_reserve_prices_successive_land_purchases(self):
        state, env = self.fixture(stock=(10, 0), step=4, cash=2500,
                                  shops=["SMOOTHIE_SHOP"] * 4)
        base = {"farmer": ["PASS"], "hands": [],
                "market": [["SELL", "MILK", 10], ["BUY_LAND"], ["BUY_LAND"]]}
        agent = self.scheduler(4, base)
        out = agent.act(state[0].observation, env.configuration)
        reference = copy.deepcopy(state)
        reference[0].action = base
        state[0].action = out
        self.engine._process_market(reference, copy.deepcopy(env))
        self.engine._process_market(state, env)
        self.assertEqual(len(reference[0].observation.farms[0]["unlocked_quadrants"]), 3)
        self.assertEqual(state[0].observation.farms[0]["unlocked_quadrants"],
                         reference[0].observation.farms[0]["unlocked_quadrants"],
                         "Successive BUY_LAND orders cost1000 then2000, not1000 twice")

    def test_duplicate_sell_slots_do_not_prefund_a_previously_unfunded_buy(self):
        state, env = self.fixture(stock=(10, 0), step=13, cash=0)
        base = {"farmer": ["PASS"], "hands": [],
                "market": [["SELL", "MILK", 1], ["BUY_ANIMAL", "COW", 1],
                           ["SELL", "MILK", 9]]}
        agent = self.scheduler(13, base)
        out = agent.act(state[0].observation, env.configuration)
        self.assertLessEqual(sum(o[2] for o in out["market"] if o[:2] == ["SELL", "MILK"]), 10)
        reference = copy.deepcopy(state)
        reference[0].action = base
        state[0].action = out
        self.engine._process_market(reference, copy.deepcopy(env))
        self.engine._process_market(state, env)
        self.assertEqual(reference[0].observation.private["shed"]["COW"], 0)
        self.assertEqual(state[0].observation.private["shed"]["COW"], 0,
                         "Moving a later SELL before the buy changes its cash dependency")

    def test_all_unreserved_saleable_post_unit_stock_is_considered(self):
        state, env = self.fixture(stock=(12, 0), step=601, cash=100000,
                                  shops=["SMOOTHIE_SHOP"])
        base = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        agent = self.scheduler(601, base)
        out = agent.act(state[0].observation, env.configuration)
        evaluated = {entry["item"] for entry in agent.diagnostics["evaluations"]}
        self.assertIn("MILK", evaluated,
                      "Already available, unreserved stock needs consideration without a baseline SELL")
        self.assertEqual([o for o in out["market"] if o[0] != "SELL"], [["HIRE"]])

    def test_withheld_sell_keeps_later_product_buy_at_original_index(self):
        state, env = self.fixture(stock=(10, 0), step=4, cash=10000,
                                  shops=["SMOOTHIE_SHOP"] * 4)
        base = {"farmer": ["PASS"], "hands": [],
                "market": [["SELL", "MILK", 10], ["BUY_PRODUCT", "WHEAT", 1]]}
        state[1].action["market"] = [["BUY_PRODUCT", "WHEAT", 2]]
        agent = self.scheduler(4, base)
        out = agent.act(state[0].observation, env.configuration)
        reference = copy.deepcopy(state)
        reference[0].action = base
        state[0].action = out
        original = self.engine._commit_unit

        def buy_price(game):
            prices = []
            own_farm = game[0].observation.farms[0]

            def record(op, item, price, farm, *args, **kwargs):
                result = original(op, item, price, farm, *args, **kwargs)
                if result and farm is own_farm and (op, item) == ("BUY_PRODUCT", "WHEAT"):
                    prices.append(price)
                return result

            self.engine._commit_unit = record
            try:
                self.engine._process_market(game, copy.deepcopy(env))
            finally:
                self.engine._commit_unit = original
            return prices

        expected = buy_price(reference)
        actual = buy_price(state)
        self.assertEqual(expected, [27])
        self.assertEqual(actual, expected,
                         "Deleting an earlier SELL slot changes the later buy's paired quote")

    def test_terminal_718_sells_exact_post_unit_shed_stock(self):
        state, env = self.fixture(stock=(4, 0), step=718, cash=0)
        obs = state[0].observation
        obs.private["inventories"] = [{"MILK": 3}]
        base = {"farmer": ["DROP"], "hands": [], "market": []}
        agent = self.scheduler(718, base)
        out = agent.act(obs, env.configuration)
        self.assertEqual(out["farmer"], ["DROP"])
        self.assertEqual(sum(o[2] for o in out["market"] if o[:2] == ["SELL", "MILK"]), 7)
        state[0].action = out
        self.engine.interpreter(state, env)
        self.assertEqual(state[0].status, "DONE")
        self.assertEqual(state[0].observation.private["shed"]["MILK"], 0)
        self.assertEqual(state[0].observation.private["inventories"], [{}])
        self.assertGreater(state[0].reward, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
