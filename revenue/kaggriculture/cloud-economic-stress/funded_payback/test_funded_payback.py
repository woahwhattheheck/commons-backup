# SPDX-License-Identifier: Apache-2.0
"""Official-engine boundary tests for the prospective land-bundle callback.

The positive case is a deliberate engine-valid fixture with a one-tile minimum,
not a naturally reached game and not a full fourth-quadrant strength result.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest

from funded_payback import FundedPaybackAdmission, evaluate_bundle


ENGINE = LOADER = None
RESULTS = []


def action(farmer=None, market=None):
    return {"farmer": list(farmer or ["PASS"]), "hands": [],
            "market": copy.deepcopy(market or [])}


def routes():
    base = [action() for _ in range(720)]
    candidate = copy.deepcopy(base)
    base[528] = action(market=[["BUY_SEED", "WHEAT", 1]])
    candidate[528] = action(market=[["BUY_SEED", "WHEAT", 1],
                                    ["BUY_LAND"], ["BUY_SEED", "CARROT", 1]])
    candidate[529] = action(["PLANT", "CARROT"])
    candidate[530] = action(["WATER"])
    # Daily reset returns the main farmer to (4,4).
    candidate[552] = action(["EAST"])
    candidate[553] = action(["SOUTH"])
    candidate[554] = action(["WATER"])
    candidate[576] = action(["EAST"])
    candidate[577] = action(["SOUTH"])
    candidate[578] = action(["WATER"])
    candidate[579] = action(["HARVEST"])
    candidate[580] = action(["NORTH"])
    candidate[581] = action(["DROP"])
    candidate[582] = action(["WEST"], [["SELL", "CARROT", 2]])
    return base, candidate


def proposal(base, candidate, *, variants=None):
    patches = {step: copy.deepcopy(row) for step, row in enumerate(candidate)
               if row != base[step]}
    return {"crop": "CARROT", "tiles": [(5, 5)], "workers": 1,
            "start": 528, "seed_units": 1, "cost": 4_030,
            "variants": variants or {"base": {
                "patches": patches,
                "receipts": [{"step": 581, "crop": "CARROT", "units": 2, "worker": 0}],
                "costs": [{"step": 528, "cash": 4_030}], "worker_days": []}}}


def fixture(*, seat=0, money=10_000, carrot_price=5_000):
    params = ENGINE._resolve_market_params({"CARROT": {
        "base": carrot_price, "below_target": 0.0, "above_target": 0.0,
    }})
    cfg = LOADER.Struct({key: value.get("default") if isinstance(value, dict) else value
                         for key, value in ENGINE.specification["configuration"].items()})
    cfg.update(episodeSteps=720, turnsPerDay=24, boardSize=10, shedCapacity=100,
               maxMarketOrdersPerTurn=10, townShopUnlockInterval=1_000,
               weedSpawnChance=0.0, marketParams={"CARROT": {
                   "base": carrot_price, "below_target": 0.0, "above_target": 0.0,
               }})
    farms = []
    for _ in range(2):
        farm = ENGINE._new_farm(10, money)
        farm["unlocked_quadrants"] = ["NW", "NE", "SW"]
        for y in range(10):
            for x in range(10):
                farm["tiles"][y][x] = ("LOCKED" if ENGINE._quadrant_of(x, y, 10) == "SE" else None)
        farm["farmer"] = [5, 5]  # Movement onto locked land is engine-valid.
        farms.append(farm)
    obs = LOADER.Struct(step=528, day=22, hour=0, player=seat,
                        farms=farms, private=ENGINE._new_private(),
                        market=ENGINE._new_market(params), town=ENGINE._new_town())
    return obs, cfg


def official(route, obs, cfg, rival_orders=None):
    rival_orders = rival_orders or {}
    env = LOADER.Struct(configuration=copy.deepcopy(cfg), done=False, info={"seed": 991})
    state = [LOADER.Struct(observation=LOADER.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    shared_farms = copy.deepcopy(obs.farms)
    shared_market = copy.deepcopy(obs.market)
    shared_town = copy.deepcopy(obs.town)
    for seat in range(2):
        private = copy.deepcopy(obs.private) if seat == obs.player else ENGINE._new_private()
        if seat != obs.player:
            private["shed"]["CARROT"] = 100
        state[seat].observation = LOADER.Struct(
            step=528, day=22, hour=0, player=seat, farms=shared_farms,
            market=shared_market, town=shared_town,
            private=private)
    for step in range(528, 719):
        for seat in range(2):
            state[seat].observation.step = step
        state[obs.player].action = copy.deepcopy(route[step])
        state[1 - obs.player].action = action(market=rival_orders.get(step, []))
        ENGINE.interpreter(state, env)
    return float(state[obs.player].reward)


class PaybackTests(unittest.TestCase):
    def evaluate(self, *, seat=0, money=10_000, price=5_000, mutate=None,
                 bundle=None, seconds=None):
        obs, cfg = fixture(seat=seat, money=money, carrot_price=price)
        base, candidate = routes()
        if mutate:
            mutate(base, candidate)
        spec = {"route_id": "worked-se", "base_route_id": "base",
                "target_quadrant": "SE", "rejoin_step": 583,
                "minimum_planted_tiles": 1}
        spec.update(bundle or {})
        before = copy.deepcopy((obs, cfg, base, candidate, spec))
        result = evaluate_bundle(obs, cfg, ENGINE, base, candidate, spec, seconds=seconds)
        self.assertEqual((obs, cfg, base, candidate, spec), before)
        RESULTS.append({"test": self.id(), "result": result})
        return result, obs, cfg, base, candidate

    def test_positive_realized_payback_both_seats_matches_official_cash(self):
        for seat in (0, 1):
            result, obs, cfg, base, candidate = self.evaluate(seat=seat)
            self.assertTrue(result["complete"])
            self.assertTrue(result["admitted"])
            self.assertEqual(result["reason"], "strict_realized_payback")
            self.assertEqual(result["planted_tiles"], 1)
            self.assertEqual(result["harvested_units"], 2)
            self.assertEqual(result["realized_target_units"], 2)
            self.assertEqual(result["worst_gain"], 5_980)
            self.assertEqual(result["rows"][0]["base_cash"], official(base, obs, cfg))
            self.assertEqual(result["rows"][0]["candidate_cash"], official(candidate, obs, cfg))
            pressure = {582: [["SELL", "CARROT", 2]]}
            self.assertEqual(result["rows"][1]["base_cash"], official(base, obs, cfg, pressure))
            self.assertEqual(result["rows"][1]["candidate_cash"], official(candidate, obs, cfg, pressure))

    def test_land_and_seed_must_be_funded_after_existing_prefix(self):
        result, *_ = self.evaluate(money=4_010)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "incremental_purchase_not_funded")

    def test_realized_route_must_pay_back_under_every_scenario(self):
        result, *_ = self.evaluate(price=100)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "no_strict_funded_payback")
        self.assertEqual(result["worst_gain"], -3_820)
        self.assertEqual(len(result["rows"]), 1)

    def test_harvest_without_explicit_drop_is_rejected(self):
        def no_drop(_base, candidate):
            candidate[581] = action()
        result, *_ = self.evaluate(mutate=no_drop)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "target_harvest_not_explicitly_dropped")

    def test_immature_harvest_does_not_count(self):
        def immature(_base, candidate):
            candidate[554] = action(["HARVEST"])
            for step in range(576, 583):
                candidate[step] = action()
        result, *_ = self.evaluate(mutate=immature, bundle={"rejoin_step": 583})
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "no_mature_target_harvest")

    def test_baseline_market_prefix_is_immutable(self):
        def displaced(_base, candidate):
            candidate[528] = action(market=[["BUY_LAND"], ["BUY_SEED", "CARROT", 1]])
        result, *_ = self.evaluate(mutate=displaced)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "baseline_market_prefix_changed")

    def test_later_existing_purchase_cannot_be_starved(self):
        def obligation(base, candidate):
            base[540] = action(market=[["BUY_SEED", "WHEAT", 2]])
            candidate[540] = copy.deepcopy(base[540])
        result, *_ = self.evaluate(money=4_049, mutate=obligation)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "existing_obligation_displaced")

    def test_each_target_plant_must_be_watered_before_land_day_close(self):
        def no_first_water(_base, candidate):
            candidate[530] = action()
        result, *_ = self.evaluate(mutate=no_first_water)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "target_not_planted_and_watered_before_day_close")

    def test_worker_position_must_rejoin(self):
        def no_return(_base, candidate):
            candidate[582] = action(market=[["SELL", "CARROT", 2]])
        result, *_ = self.evaluate(mutate=no_return)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "worker_state_does_not_rejoin")

    def test_complete_quadrant_default_rejects_partial_bundle(self):
        result, *_ = self.evaluate(bundle={"minimum_planted_tiles": 25})
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "target_not_productively_saturated")

    def test_deadline_never_admits_partial_vector(self):
        result, *_ = self.evaluate(seconds=0.0)
        self.assertFalse(result["complete"])
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "incomplete_budget")

    def test_route_must_rejoin_exact_authored_suffix(self):
        def diverged(_base, candidate):
            candidate[600] = action(["EAST"])
        result, *_ = self.evaluate(mutate=diverged)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "route_does_not_rejoin")

    def test_widefield_sparse_proposal_adapter_selects_exact_object(self):
        obs, cfg = fixture()
        base, candidate = routes()
        option = proposal(base, candidate)
        admission = FundedPaybackAdmission(seconds=1.0, max_proposals=1)
        selected = admission(ENGINE, obs, cfg, {"base": base}, [option])
        self.assertIs(selected, option)
        self.assertTrue(admission.last_report["complete"])
        self.assertTrue(admission.last_report["admitted"])
        self.assertEqual(admission.last_report["proposals"][0]["tiles"], 1)

    def test_adapter_requires_every_compatible_route_variant(self):
        obs, cfg = fixture()
        base, candidate = routes()
        good = proposal(base, candidate)["variants"]["base"]
        broken = copy.deepcopy(candidate)
        broken[581] = action()
        bad = proposal(base, broken)["variants"]["base"]
        option = proposal(base, candidate, variants={"base": good, "branch": bad})
        admission = FundedPaybackAdmission(seconds=1.0, max_proposals=1)
        self.assertIsNone(admission(ENGINE, obs, cfg,
                                    {"base": base, "branch": base}, [option]))
        self.assertTrue(admission.last_report["complete"])
        self.assertFalse(admission.last_report["admitted"])
        self.assertEqual(admission.last_report["proposals"][0]["reason"],
                         "target_harvest_not_explicitly_dropped")

    def test_first_ranked_complete_payback_returns_without_scanning_later_options(self):
        obs, cfg = fixture()
        base, candidate = routes()
        first = proposal(base, candidate)
        second = copy.deepcopy(first)
        admission = FundedPaybackAdmission(seconds=1.0, max_proposals=24)
        selected = admission(ENGINE, obs, cfg, {"base": base}, [first, second])
        self.assertIs(selected, first)
        self.assertTrue(admission.last_report["complete"])
        self.assertEqual(admission.last_report["evaluated"], 1)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    global ENGINE, LOADER
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    sys.argv = [sys.argv[0], *remaining]
    LOADER = load(args.loader, "payback_official_loader")
    ENGINE, hashes = LOADER.get_engine(args.engine_dir)
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PaybackTests)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"engine_ref": LOADER.ENGINE_REF, "engine_sha256": hashes,
              "tests_run": outcome.testsRun,
              "failures": len(outcome.failures), "errors": len(outcome.errors),
              "elapsed_seconds": time.perf_counter() - started,
              "scope": "deliberate engine-valid fixtures; not natural occurrence or full games",
              "cases": RESULTS}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if outcome.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
