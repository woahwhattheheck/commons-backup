"""Mandatory pinned-engine differential tests; no network, dependencies or skips.

python [-O] test_tomato_window.py --engine /path/to/kaggriculture.py -v
The engine AST is read from exact SHA-verified bytes. Its definitions/constants
are compiled unchanged; only package imports and renderer/specification I/O are
omitted. Tests execute the real interpreter, market, town and EOD functions.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import itertools
import json
import math
from os import path
from pathlib import Path
import random
from types import SimpleNamespace
import unittest

import tomato_window as tw

ENGINE_PATH: Path | None = None
METRICS = {}


def load_engine(file: Path):
    data = file.read_bytes()
    oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if oid != tw.ENGINE_BLOB:
        raise ValueError(f"engine identity mismatch: {oid}")
    source = ast.parse(data, filename=str(file))
    selected = []
    omitted = {"dirpath", "json_path", "agents"}
    for node in source.body:
        if isinstance(node, ast.FunctionDef):
            selected.append(node)
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if not names & omitted:
                selected.append(node)
    namespace = {"math": math, "random": random, "json": json, "path": path}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(file), "exec"), namespace)
    return SimpleNamespace(**namespace)


def fixture(engine, inventory=10000, shops=(), settings=None, params=None, seed=0):
    cfg = settings or tw.Settings()
    config = SimpleNamespace(episodeSteps=cfg.episode_steps, turnsPerDay=cfg.turns_per_day,
        townShopSellInterval=cfg.shop_sell_interval, townCenterSellInterval=cfg.center_sell_interval,
        townShopUnlockInterval=cfg.shop_unlock_interval, weedSpawnChance=0, boardSize=10)
    market = engine._new_market(engine._resolve_market_params({"TOMATO": params}) if params else None)
    market["inventory"]["TOMATO"] = inventory
    engine._refresh_prices(market)
    town = {"unlocked_shops": list(shops)}
    farms = [engine._new_farm(10, 3000) for _ in range(2)]
    state = [SimpleNamespace(observation=SimpleNamespace(market=market, town=town, farms=farms,
        private=engine._new_private(), player=seat, step=0),
        action={"farmer": ["PASS"], "hands": [], "market": []}, status="ACTIVE", reward=0)
        for seat in range(2)]
    env = SimpleNamespace(configuration=config, done=False, info={"seed": seed})
    return state, env


def official_scheduled_path(engine, inventory, shops, start, cfg, params, future):
    state, env = fixture(engine, inventory, shops, cfg, params)
    obs = state[0].observation
    remaining = iter(future)
    points = []
    for step in range(start, cfg.last_callback + 1):
        points.append((step, obs.market["inventory"]["TOMATO"], obs.market["prices"]["TOMATO"],
            sum(s in tw.TOMATO_SHOPS for s in obs.town["unlocked_shops"]), len(obs.town["unlocked_shops"])))
        engine._town_consume(env, state, step)
        if ((step + 1) % cfg.turns_per_day == 0 and
                ((step + 1) // cfg.turns_per_day) % cfg.shop_unlock_interval == 0):
            name = next(remaining, None)
            if name is not None and len(obs.town["unlocked_shops"]) < 8:
                obs.town["unlocked_shops"].append(name)
    return points, obs.market["inventory"]["TOMATO"], obs.market["prices"]["TOMATO"]


class TomatoWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ENGINE_PATH is None:
            raise ValueError("--engine is required; no simulated fallback")
        cls.engine = load_engine(ENGINE_PATH)

    def test_01_exact_1470_threshold(self):
        self.assertEqual(tw.scarcity_inventory_threshold(1470), 9275)
        self.assertEqual(self.engine.market_price("TOMATO", 9275), 1470)
        self.assertEqual(self.engine.market_price("TOMATO", 9276), 1465)
        METRICS["threshold"] = {"inventory": 9275, "deficit": 725, "price": 1470, "previous_price": 1465}

    def test_02_standard_price_curve_and_floor(self):
        for inv in range(8500, 12501):
            self.assertEqual(tw.tomato_price(inv), self.engine.market_price("TOMATO", inv))
        METRICS["standard_price_points"] = 4001

    def test_03_all_shape_pairs_and_sparse_overrides(self):
        checks = 0
        for below, above in itertools.product(sorted(tw.SHAPES), repeat=2):
            patch = {"base": 83.5, "I0": 11111, "T": 137, "below_func": below,
                "above_func": above, "below_target": 0.31, "above_target": 0.77}
            resolved = self.engine._resolve_market_params({"TOMATO": patch})
            for inv in range(10111, 12112, 37):
                self.assertEqual(tw.tomato_price(inv, patch), self.engine.market_price("TOMATO", inv, resolved))
                checks += 1
        METRICS["custom_price_points"] = checks

    def test_04_negative_inventory_is_legal(self):
        self.assertEqual(tw.tomato_price(-50), self.engine.market_price("TOMATO", -50))

    def test_05_inverse_rounding_boundaries(self):
        for target in range(61, 5000, 19):
            threshold = tw.scarcity_inventory_threshold(target)
            self.assertGreaterEqual(tw.tomato_price(threshold), target)
            self.assertLess(tw.tomato_price(threshold + 1), target)

    def test_06_zero_slope_unreachable(self):
        self.assertIsNone(tw.scarcity_inventory_threshold(61, {"below_target": 0}))
        self.assertEqual(tw.scarcity_inventory_threshold(60, {"below_target": 0}), 10000)
        self.assertEqual(tw.scarcity_inventory_threshold(1), 10000)

    def test_07_earliest_shop_envelopes(self):
        expected = {4: (570, 786), 5: (660, 1155), 6: (732, 1506), 7: (786, 1803), 8: (822, 2016)}
        out = {}
        for count, (deficit, price) in expected.items():
            p = tw.project(10000, [], future_shops=["FARMERS_MARKET"] * count)
            self.assertEqual((10000-p.final_inventory, p.summary(1470)["peak_sale_price"]), (deficit, price))
            out[str(count)] = {"deficit": deficit, "peak_sale_price": price, **p.summary(1470)}
        METRICS["earliest_tomato_shop_envelopes"] = out

    def test_08_all_70_four_of_eight_schedules(self):
        peaks = []
        for positions in itertools.combinations(range(8), 4):
            future = ["FARMERS_MARKET" if n in positions else "YARN_STORE" for n in range(8)]
            p = tw.project(10000, [], future_shops=future)
            expected, final_inv, final_price = official_scheduled_path(self.engine, 10000, [], 0,
                tw.Settings(), None, future)
            self.assertEqual([tuple(vars(q).values()) for q in p.quotes], expected)
            self.assertEqual((p.final_inventory, p.final_observed_price), (final_inv, final_price))
            peaks.append(p.summary(1470)["peak_sale_price"])
        self.assertEqual(len(peaks), 70)
        self.assertEqual(max(peaks), 786)
        METRICS["four_of_eight_legal_schedules"] = {"count": 70, "max_peak_sale_price": max(peaks), "min_peak_sale_price": min(peaks)}

    def test_09_pizza_counts_and_duplicates_stay_distinct(self):
        p = tw.project(10000, [], future_shops=["FARMERS_MARKET"]*4 + ["PIZZA_SHOP"]*2)
        self.assertEqual(p.summary(1470)["peak_sale_price"], 1506)
        self.assertIsNotNone(p.summary(1470)["first_target_sale_step"])
        self.assertEqual(p.quotes[-1].tomato_shops, 6)

    def test_10_unlock_is_after_consumption(self):
        p = tw.project(10000, [], 71, future_shops=["FARMERS_MARKET"])
        self.assertEqual((p.quotes[0].step, p.quotes[0].inventory, p.quotes[0].tomato_shops), (71,10000,0))
        self.assertEqual((p.quotes[1].step, p.quotes[1].inventory, p.quotes[1].tomato_shops), (72,10000,1))
        self.assertEqual(p.quotes[2].inventory, 9998)

    def test_11_step_zero_consumes_after_first_quote(self):
        p = tw.project(10000, [])
        self.assertEqual((p.quotes[0].inventory, p.quotes[1].inventory), (10000, 9999))

    def test_12_terminal_post_quote_is_not_revenue(self):
        p = tw.project(9276, [], settings=tw.Settings(episode_steps=2))
        self.assertEqual(p.summary(1470)["peak_sale_price"], 1465)
        self.assertIsNone(p.summary(1470)["first_target_sale_step"])
        self.assertEqual(p.final_observed_price, 1470)
        obs = {"step": 0, "market": {"inventory": {"TOMATO": 9276}}, "town": {"unlocked_shops": []}}
        self.assertEqual(tw.analyze(obs, {"episodeSteps": 2})["disposition"], "IMPOSSIBLE_UNDER_MAXIMUM_TOMATO_DEMAND")

    def test_13_no_callbacks_after_terminal(self):
        p = tw.project(9000, ["YARN_STORE"]*8, start_step=719)
        self.assertEqual(p.quotes, ())
        obs = {"step": 719, "market": {"inventory": {"TOMATO": 9000}}, "town": {"unlocked_shops": ["YARN_STORE"]*8}}
        self.assertEqual(tw.analyze(obs)["disposition"], "NO_SALE_CALLBACKS_REMAIN")

    def test_14_random_cadence_engine_differential(self):
        rng = random.Random(1470725)
        total = 0
        for _ in range(80):
            cfg = tw.Settings(rng.randrange(100, 900), rng.choice([6, 7, 24]),
                rng.choice([1, 4, 5]), rng.choice([7, 24, 31]), rng.choice([2, 3, 5]))
            start = rng.randrange(cfg.last_callback + 1)
            shops = rng.choices(sorted(tw.KNOWN_SHOPS), k=rng.randrange(9))
            future = rng.choices(sorted(tw.KNOWN_SHOPS), k=8-len(shops))
            inventory = rng.randrange(9000, 11000)
            patch = {"base": rng.choice([30,60,120]), "T": rng.choice([100,200,300])}
            p = tw.project(inventory, shops, start, cfg, patch, future)
            expected, final_inv, final_price = official_scheduled_path(self.engine, inventory, shops, start, cfg, patch, future)
            self.assertEqual([tuple(vars(q).values()) for q in p.quotes], expected)
            self.assertEqual((p.final_inventory, p.final_observed_price), (final_inv, final_price))
            total += len(expected)
        METRICS["random_cadence"] = {"scenarios": 80, "callback_points": total}

    def test_15_real_interpreter_seeded_shop_paths(self):
        samples = []
        for seed in range(12):
            state, env = fixture(self.engine, seed=seed)
            obs = state[0].observation
            points = []
            for step in range(719):
                for s in state:
                    s.observation.step = step
                points.append((step, obs.market["inventory"]["TOMATO"], obs.market["prices"]["TOMATO"],
                    sum(shop in tw.TOMATO_SHOPS for shop in obs.town["unlocked_shops"]), len(obs.town["unlocked_shops"])))
                self.engine.interpreter(state, env)
            future = list(obs.town["unlocked_shops"])
            p = tw.project(10000, [], future_shops=future)
            self.assertEqual([tuple(vars(q).values()) for q in p.quotes], points)
            self.assertEqual(p.final_inventory, obs.market["inventory"]["TOMATO"])
            self.assertEqual(state[0].status, "DONE")
            samples.append({"seed": seed, "shops": future, "final_price": p.final_observed_price})
        METRICS["real_interpreter"] = {"episodes": 12, "callback_points": 12*719, "samples": samples}

    def test_16_maximal_ceiling_dominates_real_sales_and_unlocks(self):
        rng = random.Random(7251470)
        for seed in range(8):
            shops = rng.choices(sorted(tw.KNOWN_SHOPS), k=6)
            state, env = fixture(self.engine, inventory=9800, shops=shops, seed=seed)
            for s in state:
                s.observation.private["shed"]["TOMATO"] = 100
            obs = state[0].observation
            upper = tw.project(9800, shops, 480, future_shops=["FARMERS_MARKET"]*2)
            for point in upper.quotes:
                self.assertLessEqual(obs.market["prices"]["TOMATO"], point.price)
                for s in state:
                    s.observation.step = point.step
                    s.action["market"] = [["SELL", "TOMATO", rng.randrange(1,6)]] if rng.random()<0.2 else []
                self.engine.interpreter(state, env)
        METRICS["sale_bound"] = {"midgame_scenarios": 8, "callback_points": 8*239}

    def test_17_public_only_and_nonmutation(self):
        obs = {"step": 0, "market": {"inventory": {"TOMATO": 10000}}, "town": {"unlocked_shops": []}}
        before = copy.deepcopy(obs)
        report = tw.analyze(obs, include_paths=True)
        self.assertEqual(obs, before)
        self.assertTrue(report["research_only"])
        self.assertEqual(len(report["maximal_path"]), 719)
        self.assertEqual(report["all_future_tomato_no_sale_ceiling"]["peak_sale_price"], 2016)
        self.assertEqual(report["known_shops_no_sale_conditional_ceiling"]["peak_sale_price"], 64)

    def test_18_observed_price_parameters(self):
        obs = {"step": 0, "market": {"inventory": {"TOMATO": 10000}, "params": {"TOMATO": {"base": 120}}},
            "town": {"unlocked_shops": []}}
        self.assertEqual(tw.analyze(obs)["current_price"], 120)

    def test_19_reject_impossible_four_shops_at_day_zero(self):
        obs = {"step": 0, "market": {"inventory": {"TOMATO": 10000}},
            "town": {"unlocked_shops": ["FARMERS_MARKET"]*4}}
        with self.assertRaisesRegex(ValueError, "shop count"):
            tw.analyze(obs)
        # Direct project is explicitly a hypothetical schedule facility.
        self.assertEqual(tw.project(10000, ["FARMERS_MARKET"]*4).final_observed_price, 1602)

    def test_20_full_town_has_no_phantom_new_slots(self):
        shops = ["YARN_STORE"]*6 + ["FARMERS_MARKET"]*2
        obs = {"step": 600, "market": {"inventory": {"TOMATO": 9800}}, "town": {"unlocked_shops": shops}}
        r = tw.analyze(obs)
        self.assertEqual(r["known_shops_no_sale_conditional_ceiling"], r["all_future_tomato_no_sale_ceiling"])

    def test_21_invalid_inputs_are_explicit(self):
        for f in (lambda: tw.tomato_price(True), lambda: tw.tomato_price(1, {"base": float("nan")}),
            lambda: tw.tomato_price(1, {"T": 0}), lambda: tw.tomato_price(1, {"below_target": -1}),
            lambda: tw.tomato_price(1, {"below_func": "bad"}), lambda: tw.scarcity_inventory_threshold(True),
            lambda: tw.Settings(turns_per_day=0), lambda: tw.Settings(episode_steps=10**8),
            lambda: tw.project(1, ["UNKNOWN"]), lambda: tw.project(1, ["YARN_STORE"]*9),
            lambda: tw.project(1, [], start_step=720), lambda: tw.project(1, "PIZZA_SHOP")):
            with self.assertRaises(ValueError):
                f()

    def test_22_tampered_engine_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"bad_engine.py"
            p.write_bytes(ENGINE_PATH.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                load_engine(p)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args, rest = parser.parse_known_args()
    ENGINE_PATH = args.engine
    program = unittest.main(argv=[__file__, *rest], exit=False)
    result = program.result
    if args.receipt:
        args.receipt.write_text(json.dumps({"engine_blob": tw.ENGINE_BLOB,
            "tests_run": result.testsRun, "success": result.wasSuccessful(),
            "failures": len(result.failures), "errors": len(result.errors),
            "metrics": METRICS}, indent=2, sort_keys=True)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
