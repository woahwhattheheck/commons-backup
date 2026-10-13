# SPDX-License-Identifier: Apache-2.0
"""Portable source-authenticated contract and actual official-market tests.

python test_funding_basket.py --package /path/to/unpacked/b567-package
No network access, package install, provider action, or runtime-file mutation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

import funding_basket as basket

SOURCE_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
COUNTS = {"official_market_calls": 0, "official_interpreter_calls": 0,
          "oracle_allocations": 0, "oracle_cases": 0}
TIMINGS = []
FS = ENGINE = LOADER = ROOT = None


def load_package(root):
    global FS, ENGINE, LOADER, ROOT
    ROOT = Path(root).resolve()
    source = (ROOT / "SOURCE.json").read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("SOURCE.json does not identify the tested b567 package")
    for name, pin in json.loads(source)["runtime"].items():
        data = (ROOT / name).read_bytes()
        if len(data) != pin["bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError("runtime input drift: " + name)
    sys.path.insert(0, str(ROOT))
    import frozen_selected
    FS = frozen_selected
    spec = importlib.util.spec_from_file_location(
        "basket_official_loader", ROOT / "checks/reference/evaluator/loader.py")
    LOADER = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(LOADER)
    # All three files were authenticated above: this loader cannot fetch here.
    ENGINE, _ = LOADER.get_engine(ROOT / "checks/reference/engine")


def world(stock=None, cash=0, *, seat=0, config=None, inventory=None, hires=0):
    cfg = LOADER.Struct({k: v.get("default") if isinstance(v, dict) else v
                        for k, v in ENGINE.specification["configuration"].items()})
    cfg.update(config or {})
    cfg.seed = 17
    env = LOADER.Struct(configuration=cfg, done=False, info={})
    state = [LOADER.Struct(observation=LOADER.Struct(), action={},
                          status="ACTIVE", reward=0) for _ in range(2)]
    ENGINE.interpreter(state, env)
    COUNTS["official_interpreter_calls"] += 1
    for s in state:
        s.observation.step = 5
    own = state[seat].observation
    own.farms[seat]["money"] = cash
    own.farms[seat]["hires_today"] = hires
    own.private["shed"].update(stock or {})
    own.market["inventory"].update(inventory or {})
    return state, env


def choose(rows, state, env, seat=0, *, limit=256, rival=None, targets=None):
    own = state[seat].observation
    fn = basket.bind(FS, enabled=True, max_states=limit)
    start = time.perf_counter()
    answer = fn(rows, own.farms[seat], own.private, own.market, [],
                env.configuration, 5, FS.PRODUCTS if targets is None else targets,
                {} if rival is None else rival)
    TIMINGS.append(time.perf_counter() - start)
    return answer


def parent(rows, state, env, seat=0):
    own = state[seat].observation
    return FS.fund_same_turn_acquisition(rows, own.farms[seat], own.private,
               own.market, [], env.configuration, 5, FS.PRODUCTS, {})


def execute(rows, state, env, seat=0, rival=None, *, full=False, farmer=None):
    state, env = copy.deepcopy((state, env))
    state[seat].action = {"farmer": farmer or ["PASS"], "market": rows}
    state[1-seat].action = {"farmer": ["PASS"], "market": rival or []}
    if full:
        ENGINE.interpreter(state, env)
        COUNTS["official_interpreter_calls"] += 1
    else:
        ENGINE._process_market(state, env)
        COUNTS["official_market_calls"] += 1
    return state[seat].observation, state[1-seat].observation


class BasketTests(unittest.TestCase):
    def setUp(self):
        self.rows = [[], [], ["BUY_SEED", "MELON", 1],
                     ["SELL", "EGG", 1], ["SELL", "CARROT", 1]]
        self.state, self.env = world({"EGG": 1, "CARROT": 1})

    def test_disabled_is_literal_native_callable(self):
        self.assertIs(basket.bind(FS), FS.fund_same_turn_acquisition)
        self.assertIs(basket.bind(FS, enabled=False), FS.fund_same_turn_acquisition)

    def test_source_drift_and_double_install_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "native.py"; f.write_text("altered\n")
            fake = types.SimpleNamespace(__file__=str(f),
                        fund_same_turn_acquisition=FS.fund_same_turn_acquisition)
            with self.assertRaisesRegex(ValueError, "source drift"):
                basket.bind(fake, enabled=True)
        fake = types.SimpleNamespace(__file__=FS.__file__,
                        fund_same_turn_acquisition=basket.bind(FS, enabled=True))
        with self.assertRaisesRegex(ValueError, "already installed"):
            basket.bind(fake, enabled=True)

    def test_bad_budgets_rejected(self):
        for bad in (0, -1, True, 4097, "16", None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                basket.bind(FS, enabled=True, max_states=bad)

    def test_native_killer_and_official_both_seats(self):
        for seat in (0, 1):
            state, env = world({"EGG": 1, "CARROT": 1}, seat=seat)
            old, old_info = parent(self.rows, state, env, seat)
            self.assertFalse(old_info["applied"])
            new, info = choose(self.rows, state, env, seat)
            self.assertTrue(info["applied"])
            self.assertEqual(info["moved_quantity"], 2)
            before, _ = execute(old, state, env, seat)
            after, _ = execute(new, state, env, seat)
            self.assertEqual(before.private["seeds"]["MELON"], 0)
            self.assertEqual(after.private["seeds"]["MELON"], 1)
            self.assertEqual((before.farms[seat]["money"], after.farms[seat]["money"]), (85, 5))
            self.assertEqual(before.private["shed"], after.private["shed"])
            self.assertEqual(before.market, after.market)

    def test_inputs_immutable_and_deterministic(self):
        before = copy.deepcopy((self.rows, self.state, self.env))
        a = choose(self.rows, self.state, self.env)
        b = choose(self.rows, self.state, self.env)
        self.assertEqual(a, b)
        self.assertEqual(before, (self.rows, self.state, self.env))
        self.assertEqual(FS.sale_quantities(a[0]), FS.sale_quantities(self.rows))
        self.assertEqual(a[0][2], self.rows[2])
        self.assertEqual(len(a[0]), len(self.rows))

    def test_single_source_choices_and_rank_untouched(self):
        for cash, carrot, wool in itertools.product((0, 2, 20), (1, 2), (1, 2)):
            rows = [[], ["HIRE"], ["SELL", "CARROT", carrot], ["SELL", "WOOL", wool]]
            state, env = world({"CARROT": carrot, "WOOL": wool}, cash,
                               config={"farmHandCostMult": 10})
            self.assertEqual(choose(rows, state, env), parent(rows, state, env))

    def test_previously_funded_and_no_target_unchanged(self):
        state, env = world({"EGG": 1, "CARROT": 1}, 100)
        self.assertEqual(choose(self.rows, state, env), parent(self.rows, state, env))
        for rows in ([], [[], []], [["SELL", "EGG", 1]]):
            self.assertEqual(choose(rows, self.state, self.env), parent(rows, self.state, self.env))

    def test_raw_suffix_never_parsed_moved_or_used(self):
        suffix = [{"opaque": ["BUY_PRODUCT", "WHEAT", 1]}, "bad", ["SELL", "WOOL", 1]]
        rows = self.rows + suffix
        state, env = world({"EGG": 1, "CARROT": 1}, config={"maxMarketOrdersPerTurn": 5})
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        self.assertEqual(out[:5], choose(self.rows, state, env)[0])
        self.assertEqual(out[5:], suffix)
        self.assertIs(out[5], suffix[0])
        state, env = world({"EGG": 1, "CARROT": 1}, config={"maxMarketOrdersPerTurn": 4})
        out, info = choose(rows, state, env)
        self.assertEqual(out, rows)
        self.assertFalse(info["applied"])

    def test_live_buy_product_barrier_including_after_target(self):
        for slot in (0, 2, 5):
            rows = copy.deepcopy(self.rows)
            rows.insert(slot, ["BUY_PRODUCT", "WHEAT", 1])
            out, info = choose(rows, self.state, self.env)
            self.assertEqual(out, rows)
            self.assertFalse(info.get("applied", False))

    def test_downstream_full_and_partial_fills_preserved(self):
        for request in (1, 2):
            rows = self.rows + [["BUY_SEED", "MELON", request]]
            out, info = choose(rows, self.state, self.env)
            self.assertIs(out, rows)
            self.assertFalse(info["applied"])
            obs, _ = execute(out, self.state, self.env)
            self.assertEqual(obs.private["seeds"]["MELON"], 1)

    def test_earlier_acquisition_keeps_exact_slot_and_fill(self):
        rows = [["BUY_SEED", "WHEAT", 1]] + self.rows
        state, env = world({"EGG": 1, "CARROT": 1}, 10)
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        self.assertEqual(out[0], rows[0]); self.assertEqual(out[3], rows[3])
        after, _ = execute(out, state, env)
        self.assertEqual((after.private["seeds"]["WHEAT"], after.private["seeds"]["MELON"]), (1, 1))

    def test_no_destination_does_not_displace_producer(self):
        rows = [[], ["BUY_SEED", "MELON", 1], ["SELL", "EGG", 1], ["SELL", "CARROT", 1]]
        out, info = choose(rows, self.state, self.env)
        self.assertEqual(out, rows)
        self.assertFalse(info["applied"])

    def test_duplicate_later_lots_share_one_destination(self):
        rows = [[], ["BUY_SEED", "MELON", 1], ["SELL", "EGG", 1], ["SELL", "EGG", 1]]
        state, env = world({"EGG": 2})
        self.assertFalse(parent(rows, state, env)[1]["applied"])
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        self.assertEqual(out[0], ["SELL", "EGG", 2])
        after, _ = execute(out, state, env)
        self.assertEqual(after.private["seeds"]["MELON"], 1)

    def test_existing_product_destination_preserved(self):
        rows = [["SELL", "EGG", 0], [], ["BUY_SEED", "MELON", 1],
                ["SELL", "EGG", 1], ["SELL", "CARROT", 1]]
        out, info = choose(rows, self.state, self.env)
        self.assertTrue(info["applied"])
        self.assertEqual(out[0], ["SELL", "EGG", 1])

    def test_three_source_basket_under_standard_prices(self):
        rows = [[], [], [], ["BUY_ANIMAL", "GOOSE", 1],
                ["SELL", "MILK", 1], ["SELL", "STRAWBERRY", 1], ["SELL", "EGG", 1]]
        state, env = world({"MILK": 1, "STRAWBERRY": 1, "EGG": 1})
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        self.assertEqual(info["moved_quantity"], 3)
        self.assertEqual(len(info["moves"]), 3)
        after, _ = execute(out, state, env)
        self.assertEqual(after.private["shed"]["GOOSE"], 1)

    def test_missing_physical_stock_not_finance(self):
        rows = copy.deepcopy(self.rows)
        rows[3][2] = 2  # Existing planned quantity exceeds post-unit stock.
        state, env = world({"EGG": 1, "CARROT": 1})
        out, info = choose(rows, state, env)
        self.assertIs(out, rows)
        self.assertEqual(info["reason"], "sale-exceeds-post-unit-stock")

    def test_budget_exhaustion_discards_unfinished_layer(self):
        rows = [[], [], [], ["BUY_SEED", "STRAWBERRY", 1],
                ["SELL", "EGG", 1], ["SELL", "CARROT", 1], ["SELL", "TOMATO", 1]]
        state, env = world({"EGG": 1, "CARROT": 1, "TOMATO": 1})
        out, info = choose(rows, state, env, limit=2)
        self.assertIs(out, rows)
        self.assertEqual(info["reason"], "search-budget-exhausted")
        self.assertEqual(info["states"], 2)
        self.assertTrue(choose(rows, state, env, limit=3)[1]["applied"])

    def test_native_callback_estimates_frozen_once(self):
        calls = []
        def rival(item):
            calls.append(item)
            return 1
        out, info = choose(self.rows, self.state, self.env, rival=rival)
        self.assertTrue(info["applied"])
        self.assertEqual(calls, list(FS.m.PRODUCTS))
        self.assertEqual(len(calls), len(set(calls)))

    def test_allocation_generator_matches_independent_product(self):
        for caps in itertools.product(range(1, 4), repeat=3):
            for total in range(sum(caps)+1):
                expected = {q for q in itertools.product(*(range(c+1) for c in caps))
                            if sum(q) == total}
                self.assertEqual(set(basket._allocations(caps, total)), expected)

    def test_domain_failclosed(self):
        for bad in ("10", True, 17, 1.5, None):
            state, env = world({"EGG": 1, "CARROT": 1})
            env.configuration.maxMarketOrdersPerTurn = bad
            out, info = choose(self.rows, state, env)
            self.assertIs(out, self.rows)
            self.assertFalse(info["applied"])
        for badrow in (None, {}, ["SELL", "EGG", float('nan')], ["SELL", "EGG", True],
                       ["SELL", "EGG", -1], ["UNKNOWN"], ["HIRE", "junk"]):
            rows = copy.deepcopy(self.rows); rows[0] = badrow
            out, info = choose(rows, self.state, self.env)
            self.assertIs(out, rows)
            self.assertFalse(info["applied"])
        for cap in (0, -1, 1):
            state, env = world({"EGG": 1, "CARROT": 1}, config={"maxMarketOrdersPerTurn": cap})
            self.assertEqual(choose(self.rows, state, env)[0], self.rows)

    def test_target_subset_no_new_operating_stock_sales(self):
        for targets in ([], ["EGG"], ["CARROT"], ["WHEAT", "FERTILIZER"]):
            out, info = choose(self.rows, self.state, self.env, targets=targets)
            self.assertEqual(out, self.rows)
            self.assertFalse(info["applied"])

    def test_fixed_acquisition_types_both_seats_and_rival_stress(self):
        cases = [(["BUY_SEED", "MELON", 1], {"EGG": 1, "CARROT": 1}, 0),
                 (["HIRE"], {"EGG": 1, "TOMATO": 1}, 10),
                 (["BUY_ANIMAL", "GOOSE", 1], {"MILK": 1, "WOOL": 1}, 0),
                 (["BUY_LAND"], {"MELON": 2, "WOOL": 3}, 0)]
        for target, stock, hires in cases:
            items = sorted(stock)
            rows = [[], [], target] + [["SELL", item, stock[item]] for item in items]
            for seat, offset, rival_q in itertools.product((0, 1), (-5, 0, 5), (0, 1, 4)):
                with self.subTest(target=target, seat=seat, offset=offset, rival=rival_q):
                    state, env = world(stock, seat=seat, hires=hires,
                                  inventory={i:10000+offset for i in stock})
                    out, info = choose(rows, state, env, seat, rival={i:rival_q for i in stock})
                    own = state[seat].observation
                    base_model = FS._market_prefix_state(rows, own.farms[seat], own.private,
                                  own.market, [], env.configuration, 5,
                                  {i:rival_q for i in stock}, len(rows)-1)
                    price = base_model["outcomes"][2]["cost_per_unit"]
                    guaranteed = sum(FS._stressed_sale_receipt(item, stock[item],
                                 10000+offset, own.market, [], env.configuration, 5, rival_q)[0]
                                 for item in items)
                    self.assertEqual(info["applied"], guaranteed >= price)
                    if not info["applied"]:
                        self.assertEqual(out, rows)
                        continue
                    rival = [["SELL", item, rival_q] for item in items]
                    state[1-seat].observation.private["shed"].update({i:rival_q for i in stock})
                    after, _ = execute(out, state, env, seat, rival)
                    at = FS._market_prefix_state(out, state[seat].observation.farms[seat],
                            state[seat].observation.private, state[seat].observation.market,
                            [], env.configuration, 5, {i:rival_q for i in stock}, len(out)-1)
                    self.assertGreaterEqual(after.farms[seat]["money"], at["money"])
                    if target[0] == "BUY_SEED": self.assertEqual(after.private["seeds"]["MELON"],1)
                    if target[0] == "BUY_ANIMAL": self.assertEqual(after.private["shed"]["GOOSE"],1)
                    if target[0] == "HIRE": self.assertEqual(after.farms[seat]["hires_today"],hires+1)
                    if target[0] == "BUY_LAND": self.assertEqual(len(after.farms[seat]["unlocked_quadrants"]),2)

    def test_exact_engine_small_exhaustive_minimum_units(self):
        # Independent grid oracle uses actual official market, not native quotes.
        for qa, qb, cash, cost in itertools.product((1, 2, 3), (1, 2, 3), (0, 5, 15), (80, 100, 160)):
            target = ["BUY_SEED", "MELON", cost//80] if cost != 100 else ["BUY_SEED", "STRAWBERRY", 1]
            rows = [[], [], target, ["SELL", "EGG", qa], ["SELL", "CARROT", qb]]
            state, env = world({"EGG": qa, "CARROT": qb}, cash)
            old, old_info = parent(rows, state, env)
            if not old_info or old_info.get("reason") != "no-safe-prefix-sale":
                self.assertEqual(choose(rows, state, env), (old, old_info))
                continue
            feasible = []
            for a, b in itertools.product(range(qa+1), range(qb+1)):
                candidate = [["SELL", "EGG", a] if a else [], ["SELL", "CARROT", b] if b else [],
                             target, ["SELL", "EGG", qa-a] if qa>a else [],
                             ["SELL", "CARROT", qb-b] if qb>b else []]
                after, _ = execute(candidate, state, env)
                COUNTS["oracle_allocations"] += 1
                if after.private["seeds"][target[1]] == target[2]: feasible.append(a+b)
            out, info = choose(rows, state, env, limit=4096)
            COUNTS["oracle_cases"] += 1
            if feasible:
                self.assertTrue(info["applied"])
                self.assertEqual(info["moved_quantity"], min(feasible))
            else:
                self.assertEqual(out, rows)
                self.assertFalse(info["applied"])

    def test_native_selected_transform_binding_and_off_parity(self):
        for seat in (0, 1):
            state, env = world({"EGG": 1, "CARROT": 1}, seat=seat)
            base = {"farmer": ["PASS"], "hands": [], "market": self.rows}
            route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
            route[5] = copy.deepcopy(base)
            outputs = []
            for enabled in (False, True):
                prior = FS.fund_same_turn_acquisition
                try:
                    FS.fund_same_turn_acquisition = basket.bind(FS, enabled=enabled)
                    consumer = FS.FrozenSelected()
                    consumer.controller = types.SimpleNamespace(R=[route], cur=0)
                    outputs.append(consumer.transform(state[seat].observation, env.configuration, base))
                    self.assertEqual(consumer.mode, "candidate")
                    self.assertFalse(any(consumer.pending.values()))
                    self.assertEqual(consumer.diagnostics["same_turn_funding"]["applied"], enabled)
                finally:
                    FS.fund_same_turn_acquisition = prior
            self.assertEqual(outputs[0], base)
            self.assertEqual(outputs[0]["farmer"], outputs[1]["farmer"])
            self.assertEqual(outputs[0]["hands"], outputs[1]["hands"])
            after, _ = execute(outputs[1]["market"], state, env, seat, full=True)
            self.assertEqual(after.private["seeds"]["MELON"], 1)
            self.assertEqual(after.farms[seat]["money"], 5)

    def test_real_unit_drop_then_market_and_eod(self):
        for seat, step in itertools.product((0, 1), (5, 23, 718)):
            state, env = world(seat=seat)
            own = state[seat].observation
            own.private["inventories"][0] = {"EGG": 1, "CARROT": 1}
            for s in state: s.observation.step = step
            # The caller seam supplies an exact post-unit snapshot, not free stock.
            predicted = copy.deepcopy(state)
            po = predicted[seat].observation
            ENGINE._apply_unit_action(po.farms[seat], po.private, 0, ["DROP"], 10,
                                      step//24, 24, 100)
            out, info = choose(self.rows, predicted, env, seat)
            self.assertTrue(info["applied"])
            before, _ = execute(self.rows, state, env, seat, full=True, farmer=["DROP"])
            after, _ = execute(out, state, env, seat, full=True, farmer=["DROP"])
            self.assertEqual(before.private["seeds"]["MELON"], 0)
            self.assertEqual(after.private["seeds"]["MELON"], 1)
            self.assertEqual(after.farms[seat]["money"], 5)

    def test_floor_price_and_shed_capacity_edges(self):
        rows = [[], [], ["BUY_SEED", "WHEAT", 1], ["SELL", "TOMATO", 6], ["SELL", "CARROT", 6]]
        state, env = world({"TOMATO": 6, "CARROT": 6}, inventory={"TOMATO": 100000, "CARROT": 100000})
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        self.assertEqual(info["moved_quantity"], 10)
        after, _ = execute(out, state, env)
        self.assertEqual(after.private["seeds"]["WHEAT"], 1)
        self.assertEqual(after.market["inventory"]["TOMATO"], 100000)
        self.assertEqual(after.market["inventory"]["CARROT"], 100000)
        # Full shed; the two actual sales make room for the goose acquisition.
        rows = [[], [], ["BUY_ANIMAL", "GOOSE", 1], ["SELL", "MILK", 1], ["SELL", "WOOL", 1]]
        state, env = world({"MILK": 1, "WOOL": 1, "WHEAT": 98})
        out, info = choose(rows, state, env)
        self.assertTrue(info["applied"])
        after, _ = execute(out, state, env)
        self.assertEqual(sum(after.private["shed"].values()), 99)
        self.assertEqual(after.private["shed"]["GOOSE"], 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True)
    args, rest = p.parse_known_args()
    try:
        load_package(args.package)
    except (OSError, ValueError, KeyError) as exc:
        print("INPUT_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BasketTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    timings = sorted(TIMINGS)
    print(json.dumps({"tests": result.testsRun, "failures": len(result.failures),
          "errors": len(result.errors), "counts": COUNTS,
          "helper_sha256": hashlib.sha256(Path(basket.__file__).read_bytes()).hexdigest(),
          "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "package_source_sha256": SOURCE_SHA256,
          "adapter_calls": len(timings),
          "max_seconds": max(timings, default=0),
          "median_seconds": timings[len(timings)//2] if timings else 0}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
