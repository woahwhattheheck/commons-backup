# SPDX-License-Identifier: Apache-2.0
"""Exact-engine regression for the current-runtime terminal fallback repair.

Run with --lab-root pointing at a source checkout or a materialized package.
No network calls, legacy materializer, production edits or submission occur.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import types
import unittest

from repair_terminal_fallback import EXPECTED_POSTIMAGE, EXPECTED_SOURCE, git_blob, repair

ARGS = None
EVIDENCE = {"witnesses": [], "randomized": {}}
ENGINE_PIN = "3c202c7ee921da239356789e266b694635103fc4"
JSON_PIN = "b354d06b742fe48402513792253f1a5c29366b20"
UTILS_PIN = "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_bytes(name, source, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    sys.modules[name] = module
    exec(compile(source, str(filename), "exec"), module.__dict__)
    return module


class TerminalFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = ARGS.lab_root.resolve()
        cls.source_path = root / "reference/titan-current/deadline_adapter.py"
        cls.original = cls.source_path.read_bytes()
        cls.repaired = repair(cls.original)
        cls.before = load_bytes("terminal_fallback_predecessor", cls.original, cls.source_path)
        cls.after = load_bytes("terminal_fallback_candidate", cls.repaired, cls.source_path)
        references = root / "checks/reference"
        if not references.is_dir():
            references = root / "reference"
        cls.engine_root = ARGS.engine_root or (references / "engine")
        for name, wanted in (("kaggriculture.py", ENGINE_PIN), ("kaggriculture.json", JSON_PIN), ("utils.py", UTILS_PIN)):
            actual = git_blob((cls.engine_root / name).read_bytes())
            if actual != wanted:
                raise ValueError(f"Engine source drift: {name}: {actual} != {wanted}")
        # The checked-in offline loader uses the actual upstream seed helper.
        loader = load_file("terminal_fixture_loader", references / "evaluator/loader.py")
        cls.engine, _ = loader.get_engine(cls.engine_root)
        cls.Struct = loader.Struct
        EVIDENCE.update(source_blob=git_blob(cls.original), postimage_blob=git_blob(cls.repaired),
                        engine_blob=ENGINE_PIN, python=sys.version.split()[0], optimized=not __debug__)

    def fixture(self, own_shed=None, *, seat=0, limit=10, hands=(), inventories=None, own_position=(4, 4), capacity=100, prices=None):
        e, S = self.engine, self.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v for k, v in e.specification["configuration"].items()})
        cfg.update(maxMarketOrdersPerTurn=limit, weedSpawnChance=0, shedCapacity=capacity)
        farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
        farms[seat]["farmer"] = list(own_position)
        farms[seat]["hands"] = [list(p) for p in hands]
        market = e._new_market()
        for product, value in (prices or {}).items():
            market["inventory"][product] = value
        e._refresh_prices(market)
        town = e._new_town()
        state = []
        for player in range(2):
            private = e._new_private()
            if player == seat:
                if own_shed is not None:
                    private["shed"] = dict(own_shed)
                private["inventories"] = copy.deepcopy(inventories if inventories is not None else [{} for _ in range(1 + len(hands))])
            obs = S(player=player, step=718, day=29, hour=22, farms=farms,
                    private=private, market=market, town=town)
            state.append(S(observation=obs, action=self.before.legal_pass(obs), status="ACTIVE", reward=0))
        return state, S(configuration=cfg, done=False, info={"seed": 9417})

    def settle(self, module, state, env, seat=0, rival_action=None):
        state, env = copy.deepcopy((state, env))
        untouched = copy.deepcopy(state[seat].observation)
        action = module.terminal_liquidation_fallback(state[seat].observation, env.configuration)
        self.assertEqual(state[seat].observation, untouched, "fallback changed its observation")
        state[seat].action = action
        if rival_action is not None:
            state[1 - seat].action = copy.deepcopy(rival_action)
        self.engine.interpreter(state, env)
        self.assertEqual([s.status for s in state], ["DONE", "DONE"])
        return action, state[seat].reward, state[1 - seat].reward, state

    def test_source_and_postimage_are_exact(self):
        self.assertEqual(git_blob(self.original), EXPECTED_SOURCE)
        self.assertEqual(git_blob(self.repaired), EXPECTED_POSTIMAGE)

    def test_source_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source drift"):
            repair(self.original + b"\n")

    def test_second_application_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source drift"):
            repair(self.repaired)

    def test_non_bytes_source_is_rejected(self):
        with self.assertRaises(TypeError):
            repair(self.original.decode())

    def test_only_terminal_function_changes(self):
        def other(source):
            module = ast.parse(source)
            return [ast.dump(n, include_attributes=False) for n in module.body
                    if not isinstance(n, ast.FunctionDef) or n.name != "terminal_liquidation_fallback"]
        self.assertEqual(other(self.original), other(self.repaired))

    def test_zero_limit_executes_one_legal_sale_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                state, env = self.fixture({"MILK": 1}, seat=seat, limit=0)
                old = self.settle(self.before, state, env, seat)
                new = self.settle(self.after, state, env, seat)
                self.assertEqual(old[1], 0)
                self.assertEqual(new[1], 160)
                self.assertEqual(new[0]["market"], [["SELL", "MILK", 1]])
                EVIDENCE["witnesses"].append({"case": "zero_limit", "seat": seat, "before_cash": old[1], "after_cash": new[1]})

    def test_negative_limits_match_engine_minimum_one(self):
        for value in (-100, -3, -1):
            state, env = self.fixture({"MILK": 1, "WHEAT": 2}, limit=value)
            new = self.settle(self.after, state, env)
            self.assertEqual(new[0]["market"], [["SELL", "MILK", 1]])
            self.assertEqual(new[1], 160)

    def test_numeric_string_and_float_limits_match_engine_int(self):
        for value in ("0", "-3", 0.9, 2.9, "2"):
            state, env = self.fixture({"WHEAT": 1, "MILK": 1, "EGG": 1}, limit=value)
            action = self.after.terminal_liquidation_fallback(state[0].observation, env.configuration)
            self.assertEqual(len(action["market"]), min(3, max(1, int(value))))

    def test_positive_limits_keep_existing_supported_prefix(self):
        for limit in (1, 2, 9, 10, 50):
            state, env = self.fixture({p: 1 for p in self.engine.PRODUCTS}, limit=limit)
            self.assertEqual(self.before.terminal_liquidation_fallback(state[0].observation, env.configuration),
                             self.after.terminal_liquidation_fallback(state[0].observation, env.configuration))

    def test_default_limit_is_ten(self):
        state, _ = self.fixture({p: 1 for p in self.engine.PRODUCTS})
        self.assertEqual(self.before.terminal_liquidation_fallback(state[0].observation),
                         self.after.terminal_liquidation_fallback(state[0].observation))

    def crowded_shed(self):
        return dict([(a, 1) for a in self.engine.ANIMALS] +
                    [(p, 50 if p == "WOOL" else 30 if p == "FERTILIZER" else 1) for p in self.engine.PRODUCTS])

    def test_animal_slots_recover_all_default_limit_product_lots(self):
        for seat in (0, 1):
            state, env = self.fixture(self.crowded_shed(), seat=seat)
            old = self.settle(self.before, state, env, seat)
            new = self.settle(self.after, state, env, seat)
            self.assertEqual(old[1], 700)
            self.assertGreater(new[1], old[1])
            self.assertTrue(all(new[3][seat].observation.private["shed"].get(p, 0) == 0 for p in self.engine.PRODUCTS))
            self.assertEqual(new[0]["market"][0], ["SELL", "WOOL", 50])
            self.assertEqual(new[0]["market"][1], ["SELL", "FERTILIZER", 30])
            self.assertEqual(new[0]["market"][3:], old[0]["market"][3:])
            EVIDENCE["witnesses"].append({"case": "animal_slot_completion", "seat": seat,
                                         "before_cash": old[1], "after_cash": new[1],
                                         "increment": new[1] - old[1], "market": new[0]["market"]})

    def test_already_executable_sells_never_change_raw_index(self):
        for limit in range(1, 13):
            state, env = self.fixture(self.crowded_shed(), limit=limit)
            old = self.before.terminal_liquidation_fallback(state[0].observation, env.configuration)
            new = self.after.terminal_liquidation_fallback(state[0].observation, env.configuration)
            for index, row in enumerate(old["market"]):
                if row[1] in self.engine.PRODUCTS:
                    self.assertEqual(new["market"][index], row)

    def test_no_overflow_is_action_identical_even_with_animals(self):
        state, env = self.fixture({"GOOSE": 1, "MILK": 2, "SHEEP": 1})
        self.assertEqual(self.before.terminal_liquidation_fallback(state[0].observation, env.configuration),
                         self.after.terminal_liquidation_fallback(state[0].observation, env.configuration))

    def test_animal_only_inventory_never_creates_product(self):
        state, env = self.fixture({"GOOSE": 2, "COW": 3, "SHEEP": 4}, limit=1)
        old = self.settle(self.before, state, env)
        new = self.settle(self.after, state, env)
        self.assertEqual(old[:3], new[:3])

    def test_overflow_nonproducts_are_not_used_as_replacements(self):
        state, env = self.fixture({"GOOSE": 1, "COW": 1, "SHEEP": 1, "MILK": 2}, limit=1)
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0]["market"], [["SELL", "MILK", 2]])
        self.assertGreater(new[1], 0)

    def test_scarce_slots_do_not_change_supported_product_priority(self):
        state, env = self.fixture({"WHEAT": 1, "MILK": 8}, limit=1)
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0]["market"], [["SELL", "WHEAT", 1]])

    def test_reachable_drop_is_counted_before_market(self):
        state, env = self.fixture({"GOOSE": 1}, limit=1, inventories=[{"MILK": 4}])
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0]["farmer"], ["DROP"])
        self.assertEqual(new[0]["market"], [["SELL", "MILK", 4]])
        self.assertEqual(new[3][0].observation.private["inventories"], [{}])
        self.assertGreater(new[1], 0)

    def test_remote_cargo_is_not_speculatively_sold(self):
        state, env = self.fixture({"GOOSE": 1}, limit=1, own_position=(0, 0), inventories=[{"MILK": 4}])
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0]["farmer"], ["PASS"])
        self.assertEqual(new[1], 0)
        self.assertEqual(new[3][0].observation.private["inventories"], [{"MILK": 4}])

    def test_shared_capacity_and_actor_order_preserved(self):
        state, env = self.fixture({"GOOSE": 1, "COW": 1, "SHEEP": 1}, limit=2,
                                  hands=((4, 4), (4, 5)), inventories=[{"MILK": 3}, {"WOOL": 3}, {"EGG": 2}], capacity=7)
        old_action = self.before.terminal_liquidation_fallback(state[0].observation, env.configuration)
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0]["farmer"], old_action["farmer"])
        self.assertEqual(new[0]["hands"], old_action["hands"])
        self.assertEqual(new[0]["market"], [["SELL", "MILK", 3], ["SELL", "WOOL", 1]])
        self.assertEqual(new[3][0].observation.private["inventories"], [{}, {}, {}])

    def test_locked_shed_access_remains_usable(self):
        for position in ((4, 5), (5, 4), (5, 5)):
            state, env = self.fixture({"GOOSE": 1}, limit=1, own_position=position, inventories=[{"MILK": 1}])
            new = self.settle(self.after, state, env)
            self.assertEqual(new[1], 160)

    def test_empty_shed_and_cargo_remain_pass(self):
        state, env = self.fixture({})
        new = self.settle(self.after, state, env)
        self.assertEqual(new[0], {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(new[1], 0)

    def test_repeated_calls_do_not_alias_observation(self):
        state, env = self.fixture(self.crowded_shed())
        obs = state[0].observation
        original = copy.deepcopy(obs)
        first = self.after.terminal_liquidation_fallback(obs, env.configuration)
        first["market"][0][2] = 9999
        second = self.after.terminal_liquidation_fallback(obs, env.configuration)
        self.assertEqual(obs, original)
        self.assertNotEqual(first, second)

    def test_nonterminal_pass_unchanged_both_seats(self):
        for seat in (0, 1):
            state, _ = self.fixture({}, seat=seat, hands=((4, 4), (5, 5)))
            state[seat].observation.step = 17
            self.assertEqual(self.before.legal_pass(state[seat].observation), self.after.legal_pass(state[seat].observation))

    def test_randomized_real_engine_default_limit_both_seats(self):
        rng = random.Random(9116401)
        count = improved = identical = 0
        min_delta = float("inf")
        for world in range(256):
            keys = list(self.engine.PRODUCTS) + list(self.engine.ANIMALS)
            rng.shuffle(keys)
            shed = {key: rng.randint(0, 6) for key in keys}
            quotes = {p: rng.choice((9700, 9950, 10000, 10050, 10500)) for p in self.engine.PRODUCTS}
            for seat in (0, 1):
                state, env = self.fixture(shed, seat=seat, prices=quotes)
                # Fixed rival SELL rows exercise actual per-unit lockstep pricing.
                rival_rows = [["SELL", p, rng.randint(1, 5)] for p in rng.sample(self.engine.PRODUCTS, 4)]
                for row in rival_rows:
                    state[1-seat].observation.private["shed"][row[1]] = row[2]
                rival = {"farmer": ["PASS"], "hands": [], "market": rival_rows}
                old = self.settle(self.before, state, env, seat, rival)
                new = self.settle(self.after, state, env, seat, rival)
                self.assertLessEqual(len(new[0]["market"]), 10)
                self.assertTrue(all(new[3][seat].observation.private["shed"].get(p, 0) == 0 for p in self.engine.PRODUCTS))
                for index, row in enumerate(old[0]["market"]):
                    if row[1] in self.engine.PRODUCTS:
                        self.assertEqual(new[0]["market"][index], row)
                self.assertGreaterEqual(new[1], old[1])
                delta = (new[1]-new[2]) - (old[1]-old[2])
                self.assertGreaterEqual(delta, 0)
                min_delta = min(min_delta, delta)
                count += 1
                improved += delta > 0
                identical += new[0] == old[0]
        EVIDENCE["randomized"]["default_limit_fixed_sell_rival"] = {
            "paired_final_state_cells": count, "strict_margin_improvements": improved,
            "identical_actions": identical, "minimum_margin_delta": min_delta,
            "seed": 9116401, "opponent_scope": "fixed SELL-only; not a ladder-strength panel"}

    def test_randomized_limits_full_engine_slot_invariants(self):
        rng = random.Random(9116402)
        count = 0
        for _ in range(192):
            seat = rng.randrange(2)
            keys = list(self.engine.PRODUCTS) + list(self.engine.ANIMALS)
            rng.shuffle(keys)
            shed = {key: rng.randint(0, 5) for key in keys}
            limit = rng.choice((-5, -1, 0, 1, 2, 3, 9, 10, 12))
            state, env = self.fixture(shed, seat=seat, limit=limit)
            new = self.settle(self.after, state, env, seat)
            raw = [["SELL", p, q] for p, q in shed.items() if q > 0]
            bound = max(1, int(limit))
            expected_count = min(bound, sum(p in self.engine.PRODUCTS and q > 0 for p, q in shed.items()))
            self.assertEqual(sum(row[1] in self.engine.PRODUCTS for row in new[0]["market"]), expected_count)
            self.assertLessEqual(len(new[0]["market"]), bound)
            for index, row in enumerate(raw[:bound]):
                if row[1] in self.engine.PRODUCTS:
                    self.assertEqual(new[0]["market"][index], row)
            count += 1
        EVIDENCE["randomized"]["limit_grid"] = {"final_state_cells": count, "seed": 9116402,
                                                 "limits": [-5, -1, 0, 1, 2, 3, 9, 10, 12]}


def main():
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", required=True, type=Path)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--receipt", type=Path)
    ARGS = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TerminalFallbackTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    EVIDENCE.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), success=result.wasSuccessful())
    if ARGS.receipt:
        ARGS.receipt.write_text(json.dumps(EVIDENCE, indent=2, allow_nan=False) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
