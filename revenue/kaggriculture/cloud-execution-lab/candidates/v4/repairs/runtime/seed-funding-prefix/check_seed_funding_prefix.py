# SPDX-License-Identifier: Apache-2.0
"""Pinned real-method/budget/funding/native-market regression, no full-game claim."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import textwrap
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

import repair_seed_funding_prefix as repairer

PINS = {
    "seed_budget": "eaa244ba05104535f9922a5f76d623a76c187096",
    "plant_suffix": "95d05ff28aa79074d82bdc08ce4148d3ace1b13d",
    "seed_funding": "3d0c19cdf9f1260f56be3f6a7beb191b37b3d568",
    "mechanics": "044a4f9c0a4a44dde10ada57563238bcaf82075d",
    "kaggriculture": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture_json": "b354d06b742fe48402513792253f1a5c29366b20",
}
COUNTS = {"suffix_vectors": 0, "native_market_calls": 0}
MUTANTS = {
    "uncapped_fast_path": (
        "for o in selected['market'][:maximum]):", "for o in selected['market']):"),
    "uncapped_dependency": (
        "for o in selected['market'][i+1:maximum])", "for o in selected['market'][i+1:])"),
    "unclamped_limit": (
        "maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))",
        "maximum = int(cfg.get('maxMarketOrdersPerTurn', 10))"),
    "drop_live_funding_guard": ("        if not dependent:\n", "        if True:\n"),
    "fixed_budget_cap": ("self.controller.cur, maximum,", "self.controller.cur, 10,"),
}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(name, path):
    data = path.read_bytes()
    if blob(data) != PINS[name]:
        raise ValueError(f"{name}: source pin mismatch")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def deny_seed_resolution(*args, **kwargs):
    raise RuntimeError("initialized native-market fixtures must never resolve an episode seed")


def compile_method(data):
    namespace = {"deepcopy": deepcopy}
    exec(compile(textwrap.dedent(repairer.extract_method(data).decode()),
                 "<pinned TitanAgent._seed_selected>", "exec"), namespace)
    return namespace["_seed_selected"]


def action(market=None, farmer=None):
    return {"farmer": farmer or ["PASS"], "hands": [], "market": deepcopy(market or [])}


def observation(seat=0, money=1000.5):
    farms = [ENGINE._new_farm(10, money), ENGINE._new_farm(10, 10000)]
    farms[seat]["money"] = money
    return {"step": 0, "player": seat, "farms": farms,
            "private": ENGINE._new_private(), "market": ENGINE._new_market()}


def invoke(obs, selected, cfg=None, *, seed=True, funding=False, remaining=2,
           stock=0, snapshot=True, extra=0, method=None):
    """Real SeedBudget and funding; only scheduler's post-unit projection is supplied."""
    routes = {"r": [action()] + [action(farmer=["PLANT", "WHEAT"])
                                 for _ in range(remaining)]}
    budget = BUDGET.SeedBudget(routes)
    farm, private = deepcopy(obs["farms"][obs["player"]]), deepcopy(obs["private"])
    private["seeds"]["WHEAT"] = stock
    calls = {"project": 0, "fund": 0}
    def project(*args):
        calls["project"] += 1
        return farm, private
    def fund(*args):
        calls["fund"] += 1
        return FUNDING.select_seed_queue(*args)
    scheduler = ModuleType("scheduler")
    scheduler.post_units, scheduler.m = project, MECHANICS
    agent = NS(features=NS(seed=seed, funding=funding),
               consumer=NS(selected_post_units=(farm, private) if snapshot else None),
               seed_budget=budget, controller=NS(cur="r"), diagnostics={},
               spatial=NS(future_seed_requests=lambda step: {"WHEAT": extra}) if extra else None,
               funding_module=NS(select_seed_queue=fund))
    with patch.dict(sys.modules, {"scheduler": scheduler}):
        result = (method or METHOD)(agent, obs, cfg or {}, selected)
    return result, agent, calls


def market(obs, own, rival=None, cap=10):
    seat = obs["player"]
    farms, shared = deepcopy(obs["farms"]), deepcopy(obs["market"])
    private = [ENGINE._new_private(), ENGINE._new_private()]
    private[seat] = deepcopy(obs["private"])
    private[1-seat]["shed"]["WOOL"] = 25
    private[1-seat]["shed"]["WHEAT"] = 25
    acts = [action(), action()]
    acts[seat], acts[1-seat] = own, rival or action()
    states = [NS(observation=NS(farms=farms, market=shared, private=private[i]),
                 action=deepcopy(acts[i])) for i in range(2)]
    ENGINE._process_market(states, NS(configuration={"maxMarketOrdersPerTurn": cap,
                                                    "shedCapacity": 100, "farmHandCostMult": 1}))
    COUNTS["native_market_calls"] += 1
    return {"farms": farms, "private": private, "market": shared}


class PrefixTests(unittest.TestCase):
    def test_exact_recipe_idempotent_and_other_bytes_preserved(self):
        original, repaired = RUNTIME, repairer.repair(RUNTIME)
        a, b = repairer.method_bounds(original)
        c, d = repairer.method_bounds(repaired)
        self.assertEqual(original[:a], repaired[:c])
        self.assertEqual(original[b:], repaired[d:])
        self.assertIs(repairer.repair(repaired), repaired)

    def test_source_drift_rejected(self):
        for source in (RUNTIME.replace(b"private['seeds']", b"private['bad']", 1),
                       b"class TitanAgent:\n    pass\n",
                       RUNTIME + b"\nclass TitanAgent:\n    pass\n"):
            with self.subTest(source_sha=hashlib.sha256(source).hexdigest()):
                with self.assertRaises(ValueError):
                    repairer.repair(source)

    def test_seed_disabled_does_not_parse_bad_config_or_market(self):
        selected = {"market": None}
        result, _, calls = invoke(observation(), selected, {"maxMarketOrdersPerTurn": None}, seed=False)
        self.assertIs(result, selected)
        self.assertEqual(calls, {"project": 0, "fund": 0})

    def test_only_dead_seed_is_exact_identity_without_projection(self):
        selected = action([[]] * 10 + [["BUY_SEED", "WHEAT", 9]])
        result, _, calls = invoke(observation(), selected, snapshot=False)
        self.assertIs(result, selected)
        self.assertEqual(calls, {"project": 0, "fund": 0})

    def test_raw_placeholder_slots_not_compacted(self):
        selected = action([[]] * 9 + [["BUY_SEED", "WHEAT", 9], ["HIRE"]])
        result, _, calls = invoke(observation(), selected)
        self.assertEqual(result["market"], [[]] * 9 + [["BUY_SEED", "WHEAT", 2], ["HIRE"]])
        self.assertEqual(calls["fund"], 0)

    def test_dead_suffix_independence_both_funding_settings(self):
        tails = [["HIRE"], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 1],
                 ["BUY_ANIMAL", "COW", 1], ["BUY_SEED", "WHEAT", 999],
                 ["SELL", "WOOL", 99], None, [], False, {"ignored": True}]
        for seat in (0, 1):
            for cap in (1, 2, 5, 10):
                for funding in (False, True):
                    for slot in range(cap):
                        prefix = [[] for _ in range(cap)]
                        prefix[slot] = ["BUY_SEED", "WHEAT", 9]
                        expected, _, _ = invoke(observation(seat), action(prefix),
                                                {"maxMarketOrdersPerTurn": cap}, funding=funding)
                        for tail in tails:
                            original = action(prefix + [tail])
                            frozen = deepcopy(original)
                            result, _, calls = invoke(observation(seat), original,
                                {"maxMarketOrdersPerTurn": cap}, funding=funding)
                            self.assertEqual(result["market"][:cap], expected["market"])
                            self.assertEqual(result["market"][cap:], [tail])
                            self.assertEqual(original, frozen)
                            self.assertEqual(calls["fund"], 0)
                            COUNTS["suffix_vectors"] += 1

    def test_live_dependency_remains_protected(self):
        for dependency in (["HIRE"], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 1],
                           ["BUY_ANIMAL", "COW", 1]):
            for seat in (0, 1):
                selected = action([["BUY_SEED", "WHEAT", 9], dependency])
                result, _, _ = invoke(observation(seat), selected)
                self.assertIs(result, selected)

    def test_actual_certificate_accepts_wholly_funded_live_hire(self):
        selected = action([["BUY_SEED", "WHEAT", 9], ["HIRE"]])
        result, agent, calls = invoke(observation(money=1000.0), selected, funding=True)
        self.assertEqual(result["market"][0], ["BUY_SEED", "WHEAT", 2])
        self.assertEqual(calls["fund"], 1)
        self.assertEqual(agent.diagnostics["seed_funding"]["status"], "certified")

    def test_actual_certificate_rejects_live_cash_dependence(self):
        for money in (20.0, 1000.5):
            selected = action([["BUY_SEED", "WHEAT", 9], ["HIRE"]])
            result, agent, calls = invoke(observation(money=money), selected, funding=True)
            self.assertEqual(result, selected)
            self.assertEqual(calls["fund"], 1)
            self.assertEqual(agent.diagnostics["seed_funding"]["status"], "not_certified")

    def test_actual_certificate_retains_product_boundary(self):
        selected = action([["BUY_SEED", "WHEAT", 9], ["BUY_PRODUCT", "WHEAT", 1]])
        result, agent, _ = invoke(observation(money=10000.0), selected, funding=True)
        self.assertEqual(result, selected)
        self.assertIn("paired-flow", agent.diagnostics["seed_funding"]["reason"])

    def test_prior_live_dependency_is_not_a_new_veto(self):
        selected = action([["HIRE"], ["BUY_SEED", "WHEAT", 9]])
        result, _, calls = invoke(observation(), selected)
        self.assertEqual(result["market"], [["HIRE"], ["BUY_SEED", "WHEAT", 2]])
        self.assertEqual(calls["fund"], 0)

    def test_engine_clamped_cap(self):
        for cap in (-10, -1, 0, 1):
            selected = action([["BUY_SEED", "WHEAT", 9], ["HIRE"]])
            result, _, calls = invoke(observation(), selected, {"maxMarketOrdersPerTurn": cap})
            self.assertEqual(result["market"], [["BUY_SEED", "WHEAT", 2], ["HIRE"]])
            self.assertEqual(calls["fund"], 0)
            self.assertEqual(market(observation(), result, cap=cap),
                             market(observation(), result, cap=1))

    def test_nondefault_large_limit_live_dependency_kept(self):
        selected = action([["BUY_SEED", "WHEAT", 9]] + [[]] * 9 + [["HIRE"]])
        result, _, _ = invoke(observation(), selected, {"maxMarketOrdersPerTurn": 11})
        self.assertIs(result, selected)

    def test_post_unit_stock_and_extra_requests_preserved(self):
        for snapshot in (True, False):
            selected = action([["BUY_SEED", "WHEAT", 9]])
            result, _, calls = invoke(observation(), selected, remaining=4, stock=2,
                                      extra=1, snapshot=snapshot)
            self.assertEqual(result["market"], [["BUY_SEED", "WHEAT", 3]])
            self.assertEqual(calls["project"], int(not snapshot))

    def test_zero_remaining_keeps_empty_raw_slot(self):
        result, _, _ = invoke(observation(), action([["BUY_SEED", "WHEAT", 9]]), remaining=0)
        self.assertEqual(result["market"], [[]])

    def test_no_inferred_fulfillment_of_duplicate_seed_buys(self):
        selected = action([["BUY_SEED", "WHEAT", 9], ["BUY_SEED", "WHEAT", 9]])
        result, _, _ = invoke(observation(), selected)
        self.assertEqual(result["market"], [["BUY_SEED", "WHEAT", 2]] * 2)

    def test_native_market_dead_tail_cannot_execute(self):
        for seat in (0, 1):
            for cap in (1, 2, 5, 10):
                for op in (["HIRE"], ["BUY_LAND"], ["BUY_ANIMAL", "COW", 1],
                           ["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WOOL", 10]):
                    obs = observation(seat)
                    prefix = [["BUY_SEED", "WHEAT", 2]] + [[]] * (cap-1)
                    rival = action([["SELL", "WOOL", 2], ["BUY_SEED", "TOMATO", 1]])
                    self.assertEqual(market(obs, action(prefix), rival, cap),
                                     market(obs, action(prefix + [op]), rival, cap))

    def test_native_market_savings_without_other_state_change(self):
        for seat in (0, 1):
            for cap in (1, 2, 5, 10):
                for remaining in (0, 1, 2, 8):
                    for money, funding in ((1000.0, False), (1000.5, False), (1000.5, True)):
                        obs = observation(seat, money)
                        original = action([["BUY_SEED", "WHEAT", 9]] + [[]]*(cap-1) + [["HIRE"]])
                        result, _, _ = invoke(obs, original, {"maxMarketOrdersPerTurn": cap},
                                              funding=funding, remaining=remaining)
                        old_result, _, _ = invoke(obs, original, {"maxMarketOrdersPerTurn": cap},
                            funding=funding, remaining=remaining, method=PREDECESSOR)
                        self.assertEqual(old_result, original)
                        rival = action([["SELL", "WOOL", 3], ["BUY_SEED", "TOMATO", 1]])
                        baseline, repaired = market(obs, old_result, rival, cap), market(obs, result, rival, cap)
                        self.assertEqual(repaired["farms"][seat]["money"] - baseline["farms"][seat]["money"],
                                         (9-remaining)*10)
                        self.assertEqual(baseline["private"][seat]["seeds"]["WHEAT"] -
                                         repaired["private"][seat]["seeds"]["WHEAT"], 9-remaining)
                        baseline["farms"][seat]["money"] = repaired["farms"][seat]["money"]
                        baseline["private"][seat]["seeds"]["WHEAT"] = repaired["private"][seat]["seeds"]["WHEAT"]
                        self.assertEqual(baseline, repaired)

    def test_nonstandard_prefix_keeps_dead_seed_quantity(self):
        selected = action([["BUY_SEED", "WHEAT", 9], ["BUY_SEED", "WHEAT", 99]])
        result, _, _ = invoke(observation(), selected, {"maxMarketOrdersPerTurn": 1})
        self.assertEqual(result["market"], [["BUY_SEED", "WHEAT", 2], ["BUY_SEED", "WHEAT", 99]])

    def test_unaffected_ordinary_seed_reductions_match_predecessor(self):
        for money in (20.0, 1000.0, 1000.5):
            for remaining in (0, 1, 2, 8, 9, 10):
                for stock in (0, 1, 7):
                    selected = action([["BUY_SEED", "WHEAT", 9], ["SELL", "WOOL", 2]])
                    args = dict(remaining=remaining, stock=stock)
                    result, agent, calls = invoke(observation(money=money), selected, **args)
                    old_result, old_agent, old_calls = invoke(observation(money=money), selected,
                                                             method=PREDECESSOR, **args)
                    self.assertEqual(result, old_result)
                    self.assertEqual(agent.seed_budget.events, old_agent.seed_budget.events)
                    self.assertEqual(calls, old_calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", required=True, type=Path,
                        help="directory containing pinned reference files and runtime method source")
    parser.add_argument("--runtime", type=Path,
                        help="default reference-dir/titan_runtime.py; only exact method is executed")
    parser.add_argument("--mutant", choices=sorted(MUTANTS), help="deliberately broken test variant")
    parser.add_argument("--predecessor", action="store_true", help="negative control; regressions must fail")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.predecessor and args.mutant:
        parser.error("choose one negative control")
    global RUNTIME, METHOD, PREDECESSOR, ENGINE, MECHANICS, BUDGET, FUNDING
    try:
        RUNTIME = (args.runtime or args.reference_dir / "titan_runtime.py").read_bytes()
        repaired = repairer.repair(RUNTIME)
        PREDECESSOR = compile_method(RUNTIME)
        variant = repaired
        if args.mutant:
            old, new = (part.encode() for part in MUTANTS[args.mutant])
            start, end = repairer.method_bounds(variant)
            method = variant[start:end]
            if method.count(old) != 1:
                raise ValueError("mutation anchor mismatch")
            variant = variant[:start] + method.replace(old, new, 1) + variant[end:]
        METHOD = compile_method(RUNTIME if args.predecessor else variant)
        load("plant_suffix", args.reference_dir / "plant_suffix.py")
        BUDGET = load("seed_budget", args.reference_dir / "seed_budget.py")
        FUNDING = load("seed_funding", args.reference_dir / "seed_funding.py")
        MECHANICS = load("mechanics", args.reference_dir / "mechanics.py")
        if blob((args.reference_dir / "kaggriculture.json").read_bytes()) != PINS["kaggriculture_json"]:
            raise ValueError("engine JSON source pin mismatch")
        package, utils = ModuleType("kaggle_environments"), ModuleType("kaggle_environments.utils")
        utils.resolve_episode_seed = deny_seed_resolution
        with patch.dict(sys.modules, {"kaggle_environments": package, "kaggle_environments.utils": utils}):
            ENGINE = load("kaggriculture", args.reference_dir / "kaggriculture.py")
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        parser.exit(2, f"source validation failed: {error}\n")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrefixTests))
    report = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "ok": result.wasSuccessful(), "optimized": not __debug__,
              "negative_control": args.predecessor or args.mutant, "ok": result.wasSuccessful(), "optimized": not __debug__,
              "pins": PINS, "counts": COUNTS,
              "runtime_blob": blob(RUNTIME), "method_sha256": hashlib.sha256(repairer.extract_method(RUNTIME)).hexdigest(),
              "repaired_method_sha256": hashlib.sha256(repairer.extract_method(repaired)).hexdigest(),
              "scope": "isolated exact method + real budget/funding + native market, not complete runtime or games"}
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
