"""Focused selected-action interface checks; no games or parent controller calls.

The retained development frame is an interface example, not a policy panel.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_engine_semantics as semantics

HERE = Path(__file__).resolve().parent


def selected(market=()):
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(list(market))}


def projection(now, end=None, events=(), future_market=None):
    return {"observed_step": now, "end_step": now if end is None else end,
            "stock_events": copy.deepcopy(list(events)),
            "future_market": copy.deepcopy(future_market or {})}


def capacity_contract(now, step, phase, pending=10, product="CARROT", *,
                      total=None, incremental=None, realized=0):
    total = pending + realized if total is None else total
    return {"version": 1, "observed_step": now,
            "capacity_events": [{"owner": "focused-example", "errand_id": "committed-1",
                "worker_index": 0, "target": [0, 0], "product": product,
                "step": step, "phase": phase, "pending_capacity_units": pending,
                "units_total": total,
                "units_incremental": total if incremental is None else incremental,
                "contingent": True, "guaranteed_stock_units": 0,
                "no_forced_sale_date": True,
                "first_possible_sale_step": step + int(phase == "after_market"),
                "sale_window_available": True}],
            "realized_carried": ([{"owner": "focused-example", "errand_id": "committed-1",
                "worker_index": 0, "product": product, "units": realized,
                "already_in_observation": True}] if realized else []),
            "aborted": [], "worker_reservations": [], "sale_lots": [],
            "guaranteed_future_output_units": 0}


def sold(action, product):
    return sum(o[2] for o in action.get("market", [])
               if o and o[:2] == ["SELL", product])


def retained_669():
    """A bounded caller projection: only already-observed carried stock at EOD.

    This makes no assertion that all producer unit actions through671 are known.
    Other production opportunities are not committed arrivals in this example.
    """
    frame = json.loads((HERE / "reference/selected-action/claude/envelope-binding-case-669.json").read_text())
    obs, cfg, action = (copy.deepcopy(frame[k]) for k in
                        ("observation", "config", "selected_action"))
    spec = importlib.util.spec_from_file_location("selected_example_arrivals",
            HERE / "reference/selected-action/t08/arrival_contract.py")
    arrivals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arrivals)
    contract = arrivals.build_arrival_contract(obs, cfg, action,
                                               [frame["producer_snapshot"]])
    by_product = {}
    for inv in obs["private"]["inventories"]:
        for item, quantity in inv.items():
            by_product[item] = by_product.get(item, 0) + quantity
    events = [{"step": 671, "phase": "after_market", "product": item,
               "quantity_delta": quantity} for item, quantity in by_product.items()]
    return obs, cfg, action, projection(669, 671, events), contract


class SelectedActionSellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        semantics.EngineSemantics.setUpClass()
        cls.helper = semantics.EngineSemantics()
        from selected_action_sell import SelectedActionSell
        cls.transformer = SelectedActionSell

    def fixture(self, **kwargs):
        return self.helper.fixture(**kwargs)

    def call(self, obs, cfg, action, **kwargs):
        tx = self.transformer()
        result = tx.transform(obs, cfg, action, **kwargs)
        return result, tx

    def test_import_and_transform_do_not_load_parent(self):
        code = '''
import importlib.abc, importlib.util, json, sys
class RejectParent(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(n in fullname.lower() for n in ('arlene', 'scheduler', 'cap_agent')):
            raise AssertionError('parent import: ' + fullname)
sys.meta_path.insert(0, RejectParent())
real_spec = importlib.util.spec_from_file_location
def checked_spec(name, location, *args, **kwargs):
    if any(n in str(location).lower() for n in ('arlene', 'scheduler.py', 'cap_agent')):
        raise AssertionError('parent source load: ' + str(location))
    return real_spec(name, location, *args, **kwargs)
importlib.util.spec_from_file_location = checked_spec
from selected_action_sell import SelectedActionSell
fallback = {'farmer':['PASS'], 'hands':[], 'market':[['HIRE']]}
out = SelectedActionSell().transform({'step':1}, {}, {'market':[]}, fallback_action=fallback)
assert out == fallback
payload = json.load(sys.stdin)
out = SelectedActionSell().transform(payload['obs'], payload['cfg'], payload['action'],
    post_unit_shed=payload['obs']['private']['shed'], projection=payload['projection'])
assert isinstance(out, dict)
'''
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000)
        payload = {"obs": states[0].observation, "cfg": env.configuration,
                   "action": selected([["SELL", "MILK", 12]]), "projection": projection(4, 5)}
        run = subprocess.run([sys.executable, "-c", code], cwd=HERE,
                             capture_output=True, text=True, timeout=5, input=json.dumps(payload))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_missing_projection_returns_supplied_fallback_without_mutation(self):
        states, env = self.fixture(stock=(12, 0), step=4)
        action = selected([["SELL", "MILK", 12]])
        fallback = {"farmer": ["NORTH"], "hands": [["CARE"]],
                    "market": [["HIRE"], ["SELL", "MILK", 2]]}
        snapshot = copy.deepcopy((states[0].observation, action, fallback))
        for kwargs in ({}, {"post_unit_shed": dict(states[0].observation.private["shed"])},
                       {"projection": projection(4, 5)}):
            with self.subTest(kwargs=kwargs):
                out, _ = self.call(states[0].observation, env.configuration, action,
                                   fallback_action=fallback, **kwargs)
                self.assertEqual(out, fallback)
        self.assertEqual((states[0].observation, action, fallback), snapshot)

    def test_no_feasible_plan_returns_supplied_valid_fallback(self):
        states, env = self.fixture(stock=(10, 0), step=4, cash=10000,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        obs = states[0].observation
        obs.private["shed"]["WHEAT"] = 90
        action = selected([["SELL", "MILK", 10]])
        fallback = selected([["SELL", "MILK", 10], ["SELL", "WHEAT", 1]])
        events = [{"step": 5, "phase": "before_market", "product": "CARROT",
                   "quantity_delta": 11}]
        before = copy.deepcopy((obs, action, fallback))
        out, tx = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5, events),
            fallback_action=fallback)
        self.assertEqual(out, fallback,
                         "Ten eligible units cannot make eleven spaces; caller fallback sells its own wheat")
        self.assertEqual(tx.diagnostics["status"], "fallback")
        self.assertEqual((obs, action, fallback), before)

    def test_reserved_sell_slot_is_not_changed_by_stock_normalization(self):
        states, env = self.fixture(stock=(5, 0), step=4, cash=10000)
        obs = states[0].observation
        action = selected([["SELL", "MILK", 12]])
        fallback = selected([["SELL", "MILK", 12], ["HIRE"]])
        out, _ = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5),
            reservations={"stock": {}, "cash": [], "market_slots": {4: [0]}},
            fallback_action=fallback)
        self.assertEqual(out, fallback)
        self.assertEqual(out["market"][0], action["market"][0],
                         "The engine may clamp its fill; the caller owns this exact reserved order")

    def test_malformed_future_market_returns_supplied_fallback(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000)
        obs = states[0].observation
        action = selected([["SELL", "MILK", 12]])
        fallback = selected([["SELL", "MILK", 1]])
        malformed = projection(4, 5)
        malformed["future_market"] = None
        out, tx = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=malformed,
            fallback_action=fallback)
        self.assertEqual(out, fallback)
        self.assertEqual(tx.diagnostics["status"], "fallback")

    def test_future_product_purchase_requires_caller_cost_bound(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        obs = states[0].observation
        action = selected([["SELL", "MILK", 12]])
        fallback = selected([["SELL", "MILK", 1]])
        projected = projection(4, 5, future_market={5: [["BUY_PRODUCT", "WHEAT", 3]]})
        out, _ = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projected,
            fallback_action=fallback)
        self.assertEqual(out, fallback,
                         "Unknown future rival buys cannot be replaced by a solo purchase quote")
        bounded, tx = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projected,
            reservations={"order_cost_bounds": [{"step": 5, "slot": 0, "max_cash_cost": 1000}]},
            fallback_action=fallback)
        self.assertNotEqual(bounded, fallback)
        self.assertEqual(tx.diagnostics["status"], "transformed")

    def test_worker_actions_and_non_sell_slots_survive_transformation(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000,
                                   shops=["SMOOTHIE_SHOP"] * 4)
        obs = states[0].observation
        obs.farms[0]["hands"] = [[5, 4], [5, 4]]
        obs.private["inventories"] = [{}, {}, {}]
        action = {"farmer": ["NORTH"], "hands": [["WATER"], ["PASS"]],
                  "market": [["SELL", "MILK", 12], ["HIRE"],
                             ["BUY_PRODUCT", "WHEAT", 3], [], ["BUY_SEED", "CARROT", 1]]}
        before = copy.deepcopy((obs, action))
        out, _ = self.call(obs, env.configuration, action,
                           post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5))
        self.assertEqual(out["farmer"], action["farmer"])
        self.assertEqual(out["hands"], action["hands"])
        for index in (1, 2, 3, 4):
            self.assertEqual(out["market"][index], action["market"][index])
        self.assertEqual((obs, action), before)

    def test_before_market_and_after_market_arrivals_have_different_sale_windows(self):
        results = {}
        for phase in ("before_market", "after_market"):
            states, env = self.fixture(stock=(12, 0), step=4, cash=10000,
                                       inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
            obs = states[0].observation
            obs.private["shed"]["WHEAT"] = 88
            action = selected([["SELL", "MILK", 12]])
            event = {"step": 5, "phase": phase, "product": "CARROT", "quantity_delta": 10}
            results[phase], _ = self.call(obs, env.configuration, action,
                post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5, [event]))
        self.assertGreaterEqual(sold(results["before_market"], "MILK"), 10)
        self.assertLess(sold(results["after_market"], "MILK"),
                        sold(results["before_market"], "MILK"))

    def test_pending_whole_lot_reserves_capacity_without_becoming_sellable_stock(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        obs = states[0].observation
        obs.private["shed"]["WHEAT"] = 88
        out, _ = self.call(obs, env.configuration, selected(),
            post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5),
            arrival_contract=capacity_contract(4, 5, "before_market", pending=10,
                                                total=10, incremental=2))
        self.assertGreaterEqual(sold(out, "MILK"), 10,
                                "Whole committed10, not incremental2, needs capacity")
        self.assertLessEqual(sold(out, "MILK"), 12)
        self.assertEqual(sold(out, "CARROT"), 0,
                         "A contingent producer commitment is not present shed stock")

    def test_partially_realized_lot_is_counted_once(self):
        results = []
        for realized in (0, 2):
            states, env = self.fixture(stock=(12, 0), step=4, cash=10000,
                                       inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
            obs = states[0].observation
            obs.private["shed"]["WHEAT"] = 85
            events = []
            if realized:
                obs.private["inventories"][0] = {"EGG": realized}
                events = [{"step": 5, "phase": "before_market", "product": "EGG",
                           "quantity_delta": realized}]
            out, _ = self.call(obs, env.configuration, selected(),
                post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5, events),
                arrival_contract=capacity_contract(4, 5, "before_market", pending=4-realized,
                    product="EGG", total=4, incremental=2, realized=realized))
            results.append(out)
            self.assertEqual(sold(out, "EGG"), 0)
        self.assertEqual(results[0], results[1],
                         "Observed2 plus pending2 must equal pending4, not6")
        self.assertEqual(sold(results[0], "MILK"), 1)

    def test_duplicate_sells_share_stock_and_preserve_purchase_dependency(self):
        states, env = self.fixture(stock=(10, 0), step=13, cash=0)
        obs = states[0].observation
        action = selected([["SELL", "MILK", 1], ["BUY_ANIMAL", "COW", 1],
                           ["SELL", "MILK", 20]])
        out, _ = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projection(13, 13))
        self.assertEqual(out["market"][1], action["market"][1])
        self.assertLessEqual(sold(out, "MILK"), 10)
        before = copy.deepcopy(states)
        self.helper.market(before, copy.deepcopy(env), action["market"])
        self.helper.market(states, env, out["market"])
        self.assertEqual(states[0].observation.private["shed"]["COW"],
                         before[0].observation.private["shed"]["COW"])
        self.assertEqual(states[0].observation.private["shed"]["COW"], 0)

    def test_wheat_and_reserved_stock_remain_with_caller(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=10000)
        obs = states[0].observation
        obs.private["shed"]["WHEAT"] = 30
        action = selected([["SELL", "WHEAT", 2], ["SELL", "MILK", 12]])
        out, _ = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5),
            reservations={"stock": {"MILK": 7}, "cash": [], "market_slots": {}})
        self.assertEqual(out["market"][0], action["market"][0])
        self.assertLessEqual(sold(out, "MILK"), 5)

    def test_before_market_cash_reservation_prevents_unfunded_delay(self):
        states, env = self.fixture(stock=(12, 0), step=4, cash=0,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        obs = states[0].observation
        action = selected([["SELL", "MILK", 12]])
        out, _ = self.call(obs, env.configuration, action,
            post_unit_shed=dict(obs.private["shed"]), projection=projection(4, 5),
            reservations={"stock": {}, "market_slots": {},
                          "cash": [{"step": 5, "phase": "before_market", "minimum": 1000}]})
        self.helper.market(states, env, out["market"])
        self.assertGreaterEqual(states[0].observation.farms[0]["money"], 1000,
                                "A sale at5 cannot fund cash required before market5")

    def test_seat_one_uses_absolute_step_when_day_hour_missing(self):
        states, env = self.fixture(stock=(12, 12), step=4, cash=10000,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        one = copy.deepcopy(states[1].observation)
        one.pop("day")
        one.pop("hour")
        action = selected([["SELL", "MILK", 12]])
        first, _ = self.call(states[0].observation, env.configuration, action,
            post_unit_shed=dict(states[0].observation.private["shed"]), projection=projection(4, 5))
        second, _ = self.call(one, env.configuration, action,
            post_unit_shed=dict(one.private["shed"]), projection=projection(4, 5))
        self.assertEqual(first, second)

    def test_seat_one_derives_missing_step_from_day_and_hour(self):
        states, env = self.fixture(stock=(12, 12), step=52, cash=10000,
                                   inventory=10030, shops=["SMOOTHIE_SHOP"] * 4)
        full = states[1].observation
        one = copy.deepcopy(full)
        one.pop("step")
        self.assertEqual((one["day"], one["hour"]), (2, 4))
        action = selected([["SELL", "MILK", 12]])
        first, _ = self.call(full, env.configuration, action,
            post_unit_shed=dict(full.private["shed"]), projection=projection(52, 53))
        second, tx = self.call(one, env.configuration, action,
            post_unit_shed=dict(one.private["shed"]), projection=projection(52, 53))
        self.assertEqual(tx.diagnostics["step"], 52)
        self.assertEqual(first, second)
        self.assertNotEqual(second, action,
                            "Comparison must exercise a transform, not equal fallbacks")

    def test_retained_669_consumes_committed_contract_without_opportunity_envelope(self):
        obs, cfg, action, projected, contract = retained_669()
        self.assertEqual(sum(e["quantity_delta"] for e in projected["stock_events"]), 79)
        self.assertEqual([e["pending_capacity_units"] for e in contract["capacity_events"]], [4])
        self.assertEqual(contract["capacity_events"][0]["phase"], "after_market")
        out, _ = self.call(obs, cfg, action, post_unit_shed=dict(obs["private"]["shed"]),
                           projection=projected, arrival_contract=contract)
        self.assertEqual(out["farmer"], action["farmer"])
        self.assertEqual(out["hands"], action["hands"])
        self.assertEqual(out["market"][0], ["SELL", "WHEAT", 2])
        self.assertEqual(sold(out, "EGG"), 0)
        self.assertEqual(sold(out, "STRAWBERRY"), 0,
                         "Committed4 plus carried79 does not require this immediate sale")


if __name__ == "__main__":
    unittest.main(verbosity=2)
