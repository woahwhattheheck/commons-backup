# SPDX-License-Identifier: Apache-2.0
"""New funding-bound discriminators against the unchanged official market stage.

Supply the already-cached engine file. This runs no initialization, full games,
random draws, network access, or previous peer test suite.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
import unittest

from seed_funding import certify_seed_funding, select_seed_queue

ENGINE_SHA = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
K = None
PAIRS = []


def load_engine(path):
    data = Path(path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != ENGINE_SHA:
        raise ValueError(f"This test targets the pinned market source; got {actual}")
    tree = ast.parse(data, filename=str(path))
    # The only unavailable import belongs to episode initialization, which this
    # test never invokes. Every function body, including _process_market, stays
    # exactly as supplied. No reference-market logic is reimplemented here.
    tree.body = [n for n in tree.body if not (
        isinstance(n, ast.ImportFrom) and n.module == "kaggle_environments.utils")]
    mod = ModuleType("cedar_official_market")
    mod.__file__ = str(Path(path).resolve())
    exec(compile(tree, str(path), "exec"), mod.__dict__)
    return mod


def action(orders):
    return {"farmer": ["PASS"], "hands": [], "market": deepcopy(orders)}


def farm(money, hires=12, unlocked=1):
    quadrants = ["NW", *K.LAND_ORDER[:unlocked - 1]]
    tiles = [[None if K._quadrant_of(x, y, 10) in quadrants else "LOCKED"
              for x in range(10)] for y in range(10)]
    return {"money": money, "hires_today": hires,
            "farmer": list(K._default_spawn(10)),
            "hands": [list(K._default_spawn(10)) for _ in range(hires)],
            "unlocked_quadrants": quadrants, "tiles": tiles}


def private(hires=12, stock=0):
    return {"seeds": {}, "shed": {"WHEAT": stock},
            "inventories": [{} for _ in range(hires + 1)]}


def fixture(money=1000, hires=12, stock=20, unlocked=1, seat=0):
    farms = [farm(5000, 2), farm(5000, 2)]
    privates = [private(2, 35), private(2, 35)]
    farms[seat], privates[seat] = farm(money, hires, unlocked), private(hires, stock)
    market = {"inventory": {p: 10000 for p in K.PRODUCTS}, "prices": {}}
    K._refresh_prices(market)
    return {"farms": farms, "privates": privates, "market": market, "seat": seat}


def observation(state):
    return {"player": state["seat"], "farms": deepcopy(state["farms"]),
            "private": deepcopy(state["privates"][state["seat"]])}


def execute(initial, own, rival, config=None):
    data = deepcopy(initial)
    seat = data["seat"]
    actors = []
    for i in (0, 1):
        obs = SimpleNamespace(farms=data["farms"], market=data["market"],
                              private=data["privates"][i])
        actors.append(SimpleNamespace(observation=obs,
                       action=deepcopy(own if i == seat else rival)))
    K._process_market(actors, SimpleNamespace(configuration=dict(config or {})))
    return data


def without(mapping, key):
    return {k: v for k, v in mapping.items() if k != key}


class FundingTests(unittest.TestCase):
    def setUp(self):
        self.base = action([["BUY_SEED", "WHEAT", 10], ["HIRE"]])
        self.proposal = action([["BUY_SEED", "WHEAT", 3], ["HIRE"]])

    def check_pair(self, label, initial, base, proposal, rival, config=None):
        before = deepcopy((initial, base, proposal, rival, config))
        result = certify_seed_funding(K, observation(initial), base, proposal, config)
        self.assertEqual(result["status"], "certified", result)
        old, new = execute(initial, base, rival, config), execute(initial, proposal, rival, config)
        seat, other = initial["seat"], 1 - initial["seat"]
        self.assertEqual(without(old["farms"][seat], "money"), without(new["farms"][seat], "money"))
        self.assertEqual(without(old["privates"][seat], "seeds"), without(new["privates"][seat], "seeds"))
        self.assertEqual(old["farms"][other], new["farms"][other])
        self.assertEqual(old["privates"][other], new["privates"][other])
        self.assertEqual(old["market"], new["market"])
        delta = new["farms"][seat]["money"] - old["farms"][seat]["money"]
        self.assertEqual(delta, result["paired_current_market_cash_delta"])
        self.assertEqual(before, (initial, base, proposal, rival, config))
        PAIRS.append({"case": label, "seat": seat, "baseline": base["market"],
                      "proposal": proposal["market"], "rival": rival["market"],
                      "configuration": config or {},
                      "original_cash": initial["farms"][seat]["money"],
                      "baseline_final_cash": old["farms"][seat]["money"],
                      "proposed_final_cash": new["farms"][seat]["money"],
                      "cash_delta": delta, "rival_cash_delta": 0,
                      "fixed_cost_upper_bound": result["original_fixed_cost_upper_bound"],
                      "non_seed_state_equal": True, "market_equal": True})
        return result

    def test_funded_hire_executes_in_both_arms(self):
        r = self.check_pair("funded-hire", fixture(), self.base, self.proposal, action([]))
        self.assertEqual(r["paired_current_market_cash_delta"], 70)
        self.assertEqual(r["original_fixed_cost_upper_bound"], 333)

    def test_underfunded_hire_preserves_original(self):
        f = fixture(money=300)
        proposal = action([[], ["HIRE"]])
        selected, result = select_seed_queue(K, observation(f), self.base, proposal)
        self.assertEqual(result["status"], "not_certified")
        self.assertEqual(result["reason"], "original_queue_needs_additional_cash")
        self.assertEqual(selected, self.base)
        old, new = execute(f, self.base, action([])), execute(f, proposal, action([]))
        self.assertEqual(old["farms"][0]["money"], 200)
        self.assertEqual(new["farms"][0]["money"], 67)
        self.assertEqual(len(new["farms"][0]["hands"]), len(old["farms"][0]["hands"]) + 1)
        PAIRS.append({"case": "underfunded-hire-negative", "seat": 0,
                      "baseline_final_cash": 200, "proposed_final_cash": 67,
                      "cash_delta": -133, "non_seed_state_equal": False,
                      "certificate": result["status"], "returned_original": True})

    def test_real_market_grid_both_seats(self):
        rivals = [[], [["SELL", "WHEAT", 30]],
                  [["BUY_PRODUCT", "WHEAT", 11], ["SELL", "WHEAT", 9]],
                  [["BUY_SEED", "CARROT", 7], ["HIRE"], ["SELL", "WHEAT", 20]]]
        tails = {
            "hire": [["HIRE"]], "double-hire": [["HIRE"], ["HIRE"]],
            "land": [["BUY_LAND"]], "animal": [["BUY_ANIMAL", "COW", 2]],
            "sell-hire": [["SELL", "WHEAT", 8], ["HIRE"]],
            "seed-hire": [["BUY_SEED", "CARROT", 4], ["HIRE"]],
            "sell-animal": [["SELL", "WHEAT", 8], ["BUY_ANIMAL", "SHEEP", 2]],
            "land-hire-animal": [["BUY_LAND"], ["HIRE"], ["BUY_ANIMAL", "GOOSE", 1]],
        }
        for label, tail in tails.items():
            for seat in (0, 1):
                for rival in rivals:
                    with self.subTest(label=label, seat=seat, rival=rival):
                        base = action([["BUY_SEED", "WHEAT", 10], *tail])
                        proposal = action([["BUY_SEED", "WHEAT", 3], *tail])
                        self.check_pair(label, fixture(money=10000, seat=seat), base, proposal, action(rival))

    def test_capacity_clipped_animals_are_identical(self):
        for seat in (0, 1):
            base = action([["BUY_SEED", "WHEAT", 10], ["BUY_ANIMAL", "COW", 2]])
            proposal = action([[], ["BUY_ANIMAL", "COW", 2]])
            self.check_pair("clipped-animal", fixture(money=1000, stock=99, seat=seat),
                            base, proposal, action([["SELL", "WHEAT", 5]]))

    def test_custom_multiplier_and_exhausted_land(self):
        base = action([["BUY_SEED", "WHEAT", 10], ["BUY_LAND"], ["HIRE"], ["HIRE"]])
        proposal = action([[], ["BUY_LAND"], ["HIRE"], ["HIRE"]])
        self.check_pair("exhausted-land", fixture(money=10000, unlocked=4), base, proposal,
                        action([]), {"farmHandCostMult": 4})

    def test_truncated_product_order_does_not_block(self):
        base = action([["BUY_SEED", "WHEAT", 10], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 10]])
        proposed = action([[], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 10]])
        self.check_pair("truncated-product", fixture(), base, proposed, action([]),
                        {"maxMarketOrdersPerTurn": 2})

    def test_unknown_product_price_preserves_fallback(self):
        base = action([["BUY_SEED", "WHEAT", 10], ["BUY_PRODUCT", "WHEAT", 2]])
        proposal = action([[], ["BUY_PRODUCT", "WHEAT", 2]])
        chosen, r = select_seed_queue(K, observation(fixture()), base, proposal)
        self.assertEqual(r["status"], "not_certified")
        self.assertIn("paired-flow", r["reason"])
        self.assertEqual(chosen, base)

    def test_sales_are_not_spendable_in_the_bound(self):
        base = action([["BUY_SEED", "WHEAT", 10], ["SELL", "WHEAT", 20], ["HIRE"]])
        proposed = action([[], ["SELL", "WHEAT", 20], ["HIRE"]])
        r = certify_seed_funding(K, observation(fixture(money=200)), base, proposed)
        self.assertEqual(r["status"], "not_certified")
        self.assertEqual(r["original_fixed_cost_upper_bound"], 333)

    def test_changed_units_or_other_fields_not_certified(self):
        for field, value in (("farmer", ["NORTH"]), ("metadata", "changed")):
            altered = deepcopy(self.proposal); altered[field] = value
            r = certify_seed_funding(K, observation(fixture()), self.base, altered)
            self.assertEqual(r["status"], "not_certified")

    def test_changed_nonseed_or_inserted_slot_not_certified(self):
        for orders in ([[], ["BUY_LAND"]], [[], ["HIRE"], []]):
            r = certify_seed_funding(K, observation(fixture()), self.base, action(orders))
            self.assertEqual(r["status"], "not_certified")

    def test_seed_increase_and_product_substitution_not_certified(self):
        for order in (["BUY_SEED", "WHEAT", 11], ["BUY_SEED", "CARROT", 3]):
            r = certify_seed_funding(K, observation(fixture()), self.base, action([order, ["HIRE"]]))
            self.assertEqual(r["status"], "not_certified")

    def test_ignored_edit_is_not_a_cash_saving(self):
        r = certify_seed_funding(K, observation(fixture()), self.base, self.proposal,
                                 {"maxMarketOrdersPerTurn": 1})
        self.assertEqual(r["status"], "certified")
        base = action([[], ["BUY_SEED", "WHEAT", 10]])
        proposal = action([[], []])
        r = certify_seed_funding(K, observation(fixture()), base, proposal,
                                 {"maxMarketOrdersPerTurn": 1})
        self.assertEqual(r["status"], "not_certified")

    def test_repeated_seed_reductions_and_order_positions(self):
        base = action([["BUY_SEED", "WHEAT", 10], [], ["BUY_SEED", "CARROT", 4], ["HIRE"]])
        proposal = action([["BUY_SEED", "WHEAT", 3], [], ["BUY_SEED", "CARROT", 2], ["HIRE"]])
        r = self.check_pair("two-seed-reductions", fixture(), base, proposal,
                            action([["SELL", "WHEAT", 10], [], ["BUY_PRODUCT", "WHEAT", 3]]))
        self.assertEqual(r["edited_slots"], [0, 2])
        self.assertEqual(r["paired_current_market_cash_delta"], 110)

    def test_no_seed_change_and_malformed_input(self):
        r = certify_seed_funding(K, observation(fixture()), self.base, self.base)
        self.assertEqual(r["status"], "no_seed_edit")
        for value in (-1, True, 2.5, "10", 99_999):
            base = action([["BUY_SEED", "WHEAT", value], ["HIRE"]])
            r = certify_seed_funding(K, observation(fixture()), base, action([[], ["HIRE"]]))
            self.assertEqual(r["status"], "not_certified")

    def test_output_is_detached_and_custom_fallback_preserved(self):
        obs = observation(fixture())
        selected, r = select_seed_queue(K, obs, self.base, self.proposal)
        self.assertEqual(r["status"], "certified")
        selected["market"][0][2] = 999
        self.assertEqual(self.proposal["market"][0][2], 3)
        fallback = action([["PASS"]])
        selected, _ = select_seed_queue(K, observation(fixture(money=0)), self.base,
                                        self.proposal, fallback_action=fallback)
        self.assertEqual(selected, fallback)
        selected["market"].append([])
        self.assertEqual(len(fallback["market"]), 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-source", required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    K = load_engine(args.engine_source)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FundingTests))
    report = {"schema": "cedar-seed-funding-v1", "engine_sha256": ENGINE_SHA,
              "source_sha256": hashlib.sha256(Path(__file__).with_name("seed_funding.py").read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "success": result.wasSuccessful(),
              "duration_s": time.perf_counter() - started,
              "official_market_pairs": len(PAIRS), "official_market_calls": 2 * len(PAIRS),
              "full_games": 0, "game_seeds_consumed": 0, "pairs": PAIRS}
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
