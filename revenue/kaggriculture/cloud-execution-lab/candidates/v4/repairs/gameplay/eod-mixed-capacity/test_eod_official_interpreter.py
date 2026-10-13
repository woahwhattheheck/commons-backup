# SPDX-License-Identifier: Apache-2.0
"""Hash-bound EOD rescue regression against the *unmodified* official interpreter.

This is a mechanism/transition test, NOT a complete R04 package or game-strength
panel. The lane and H3c dependency are loaded from hash-verified source files.
Only r04_full_router.PRODUCTS is represented by a literal adapter (verified against
router a3e2fe87c717d128e43c9b65bae2265f40d1d76d, PRODUCTS assignment). No router,
materializer, feature installation or production archive is executed.

The engine's unused seed-resolution import is supplied by an explicit raising
shim. All states are initialized using the engine's own constructors; calling
initialization or the seed shim fails, rather than silently substituting logic.
Every transition uses engine.interpreter, including unit work, nonlinear lockstep
market, town processing, plant decay, animal refresh, auto-drop and hand reset.

Example (Python 3.11+; no third-party packages):
  python test_eod_official_interpreter.py --engine kaggriculture.py \
    --lane r04_eod_capacity_rescue.py --h3c h3c_goose_eod_cap_rescue.py \
    --receipt receipt.json
Run the exact command again with python -O and a different receipt filename.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import random
import sys
import unittest
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
LANE_BLOB = "9ad4092453e2332b0914f90ca89791b18f2229c2"
H3C_BLOB = "2044d6cf1e0c51f95027229863f910aa43ac7008"
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")
CONFIG = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
              shedCapacity=100, maxMarketOrdersPerTurn=10)
COUNTS = Counter()
WITNESSES = {}
engine = lane = None


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def checked_source(path: Path, expected: str) -> bytes:
    if len(expected) != 40 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("expected source identity must be a complete lowercase Git blob SHA")
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"source mismatch: {path}: expected {expected}, got {actual}")
    compile(data, str(path), "exec")
    return data


def load_module(name: str, path: Path, data: bytes):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Execute the already-verified bytes, avoiding a second read or stale pycache.
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def forbidden_seed_resolution(*args, **kwargs):
    raise RuntimeError("initialized-state test must not call Kaggle seed resolution")


def validate_router_adapter_use(source: bytes):
    tree = ast.parse(source)
    aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for a in n.names if a.name == "r04_full_router"}
    if aliases != {"r04"}:
        raise ValueError("review router adapter before testing a changed import surface")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in aliases and node.attr != "PRODUCTS":
                raise ValueError("router adapter is only valid for the literal PRODUCTS surface")


def world(shed, inventories, *, player=0, step=119, market_rows=None,
          rival_rows=None, stocks=None, seed=12612, money=10000.0):
    farms = [engine._new_farm(10, money), engine._new_farm(10, money)]
    farms[player]["hands"] = [[4, 3] for _ in inventories[1:]]
    farms[player]["hires_today"] = len(inventories) - 1
    privates = [engine._new_private(), engine._new_private()]
    privates[player]["shed"].update(copy.deepcopy(shed))
    privates[player]["inventories"] = copy.deepcopy(inventories)
    privates[player]["seeds"]["WHEAT"] = 4
    privates[1 - player]["shed"].update({"WHEAT": 40, "CARROT": 40})
    market = engine._new_market()
    if stocks:
        market["inventory"].update(stocks)
    engine._refresh_prices(market)
    town = engine._new_town()
    town["unlocked_shops"] = ["FARMERS_MARKET", "YARN_STORE"]
    parent = {"farmer": ["PASS"], "hands": [["PASS"] for _ in inventories[1:]],
              "market": copy.deepcopy(market_rows or [])}
    rival = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rival_rows or [])}
    actions = [None, None]
    actions[player], actions[1 - player] = parent, rival
    state = [SimpleNamespace(
        observation=SimpleNamespace(step=step, day=step // 24, hour=step % 24,
                                    player=i, farms=farms, private=privates[i],
                                    market=market, town=town),
        action=actions[i], status="ACTIVE", reward=0.0) for i in range(2)]
    env = SimpleNamespace(configuration=SimpleNamespace(**CONFIG), done=False,
                          info={"seed": seed})
    return state, env, parent


def advance(state, env, player, action):
    copied = copy.deepcopy(state)
    copied[player].action = copy.deepcopy(action)
    result = engine.interpreter(copied, copy.deepcopy(env))
    COUNTS["official_interpreter_calls"] += 1
    return result


def farm_without_money(farm):
    return {key: value for key, value in farm.items() if key != "money"}


class OfficialEodContracts(unittest.TestCase):
    def setUp(self):
        lane.telemetry.clear()

    def candidate(self, state, env, player, parent, *, enabled=True):
        obs = copy.deepcopy(vars(state[player].observation))
        before = copy.deepcopy((obs, parent, vars(env.configuration)))
        result = lane.apply_eod_capacity_rescue(parent, obs, env.configuration, enabled=enabled)
        self.assertEqual((obs, parent, vars(env.configuration)), before)
        COUNTS["candidate_calls"] += 1
        return result

    def pair(self, state, env, player, parent, *, expect_active=True):
        result = self.candidate(state, env, player, parent)
        if expect_active:
            self.assertIsNot(result, parent)
            self.assertGreater(len(result["market"]), len(parent["market"]))
        else:
            self.assertIs(result, parent)
        self.assertEqual(result["market"][:len(parent["market"])], parent["market"])
        self.assertEqual(result["farmer"], parent["farmer"])
        self.assertEqual(result["hands"], parent["hands"])
        base = advance(state, env, player, parent)
        changed = advance(state, env, player, result)
        self.assertEqual(changed[player].observation.private, base[player].observation.private)
        for seat in (0, 1):
            self.assertEqual(farm_without_money(changed[0].observation.farms[seat]),
                             farm_without_money(base[0].observation.farms[seat]))
            self.assertEqual((changed[seat].status, changed[seat].reward),
                             (base[seat].status, base[seat].reward))
        self.assertEqual(changed[0].observation.town, base[0].observation.town)
        self.assertEqual(changed[player].observation.private["inventories"], [{}])
        self.assertEqual(changed[0].observation.farms[player]["hands"], [])
        self.assertEqual(changed[0].observation.hour, 0)
        cash = changed[0].observation.farms[player]["money"] - base[0].observation.farms[player]["money"]
        if expect_active:
            self.assertGreater(cash, 0)
        else:
            self.assertEqual(cash, 0)
        COUNTS["paired_transitions"] += 1
        COUNTS["activations" if expect_active else "no_ops"] += 1
        return base, changed, result, cash

    def test_01_engine_identity_and_dependency_boundaries(self):
        self.assertEqual(tuple(engine.PRODUCTS), PRODUCTS)
        self.assertEqual(engine.interpreter.__module__, "eod_official_engine")
        self.assertEqual(engine._drop_inventories_to_shed.__module__, "eod_official_engine")
        self.assertEqual(engine._process_market.__module__, "eod_official_engine")
        with self.assertRaises(RuntimeError):
            forbidden_seed_resolution()
        with self.assertRaises(ValueError):
            validate_router_adapter_use(b"import r04_full_router as r04\nx=r04.install\n")

    def test_02_full_shed_mixed_cargo_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                s, e, a = world({"WHEAT": 50, "CARROT": 50},
                                [{"WHEAT": 2, "CARROT": 1}, {"CARROT": 2}], player=seat)
                _, _, out, _ = self.pair(s, e, seat, a)
                self.assertEqual(out["market"], [["SELL", "CARROT", 3], ["SELL", "WHEAT", 2]])

    def test_03_actor_order_and_mapping_order(self):
        for seat, reverse_actors, reverse_keys in itertools.product((0, 1), repeat=3):
            invs = [{"WHEAT": 2}, {"WHEAT": 1, "CARROT": 3}]
            if reverse_actors:
                invs.reverse()
            if reverse_keys:
                invs = [dict(reversed(tuple(inv.items()))) for inv in invs]
            s, e, a = world({"WHEAT": 50, "CARROT": 48}, invs, player=seat)
            self.pair(s, e, seat, a, expect_active=not reverse_actors)

    def test_04_partial_single_product_before_mixed_tail(self):
        for seat in (0, 1):
            s, e, a = world({"WHEAT": 50, "CARROT": 49},
                            [{"WHEAT": 3}, {"CARROT": 2, "WHEAT": 1}], player=seat)
            _, _, out, _ = self.pair(s, e, seat, a)
            self.assertEqual(out["market"], [["SELL", "CARROT", 2], ["SELL", "WHEAT", 3]])

    def test_05_uncovered_fully_admitted_product_is_not_sold(self):
        s, e, a = world({"CARROT": 97}, [{"WHEAT": 1, "EGG": 2}, {"CARROT": 3}])
        _, _, out, _ = self.pair(s, e, 0, a)
        self.assertEqual(out["market"], [["SELL", "CARROT", 3]])

    def test_06_whole_vector_raw_slot_limit(self):
        for seat in (0, 1):
            for n in (0, 7, 8, 9, 10, 11):
                with self.subTest(seat=seat, raw_rows=n):
                    s, e, a = world({"WHEAT": 50, "CARROT": 50},
                                    [{"WHEAT": 2}, {"CARROT": 3}],
                                    player=seat, market_rows=[[] for _ in range(n)])
                    self.pair(s, e, seat, a, expect_active=n <= 8)

    def test_07_real_neutral_market_actions_and_new_hire_inventory(self):
        prefixes = ([["HIRE"]], [["BUY_SEED", "WHEAT", 2]], [["BUY_LAND"]],
                    [["HIRE"], [], ["BUY_SEED", "WHEAT", 2], ["BUY_LAND"]])
        for seat, prefix in itertools.product((0, 1), prefixes):
            s, e, a = world({"WHEAT": 50, "CARROT": 50},
                            [{"WHEAT": 2}, {"CARROT": 3}], player=seat, market_rows=prefix)
            self.pair(s, e, seat, a)

    def test_08_successful_neutral_unit_commands(self):
        commands = (["PASS"], ["NORTH"], ["SOUTH"], ["EAST"], ["WEST"], ["DIG"],
                    ["BUILD_COOP"], ["BUILD_PASTURE"], ["PLANT", "WHEAT"],
                    ["WATER"], ["CARE"])
        for seat, command in itertools.product((0, 1), commands):
            s, e, a = world({"WHEAT": 50, "CARROT": 50}, [{"WHEAT": 2}], player=seat)
            farm = s[0].observation.farms[seat]
            farm["farmer"] = [3, 3]
            if command[0] == "DIG":
                farm["tiles"][3][3] = {"kind": "WEED"}
            elif command[0] == "WATER":
                farm["tiles"][3][3] = engine._new_plant("WHEAT", 2, 24)
            elif command[0] == "CARE":
                farm["tiles"][3][3] = engine._new_animal("GOOSE", 0)
                farm["tiles"][3][3]["fed_today"] = True
            a["farmer"] = list(command)
            _, changed, _, _ = self.pair(s, e, seat, a)
            post_tile = changed[0].observation.farms[seat]["tiles"][3][3]
            if command[0] == "BUILD_COOP":
                self.assertEqual(post_tile, {"kind": "COOP"})
            elif command[0] == "BUILD_PASTURE":
                self.assertEqual(post_tile, {"kind": "PASTURE"})
            elif command[0] == "PLANT":
                # Fresh planting starts consecutive_unwatered=1; without same-turn
                # WATER the official EOD refresh turns it to WEED. Seeds still debit.
                self.assertEqual(post_tile, {"kind": "WEED"})
                self.assertEqual(changed[seat].observation.private["seeds"]["WHEAT"], 3)
            elif command[0] == "CARE":
                self.assertEqual(post_tile["pending_care_bonus"], 1)
            elif command[0] == "WATER":
                self.assertEqual(post_tile["consecutive_unwatered"], 0)

    def test_09_atomic_plant_seed_demand_survives(self):
        for available in (1, 2):
            s, e, a = world({"WHEAT": 50, "CARROT": 50}, [{"WHEAT": 2}, {"CARROT": 3}])
            s[0].observation.private["seeds"]["WHEAT"] = available
            a["farmer"] = ["PLANT", "WHEAT"]
            a["hands"] = [["PLANT", "WHEAT"]]
            _, changed, _, _ = self.pair(s, e, 0, a)
            self.assertEqual(changed[0].observation.private["seeds"]["WHEAT"],
                             available if available == 1 else 0)

    def test_10_rival_market_rows_both_seats(self):
        rivals = ([["SELL", "WHEAT", 35]], [["SELL", "CARROT", 35]],
                  [["BUY_PRODUCT", "WHEAT", 10]], [["BUY_PRODUCT", "FERTILIZER", 10]],
                  [[], ["SELL", "WHEAT", 35]], [["HIRE"], ["BUY_SEED", "WHEAT", 2]])
        for seat, rival in itertools.product((0, 1), rivals):
            s, e, a = world({"WHEAT": 50, "CARROT": 50},
                            [{"WHEAT": 5}, {"CARROT": 5}], player=seat, rival_rows=rival)
            self.pair(s, e, seat, a)

    def test_11_floor_price_real_engine_supply(self):
        for seat in (0, 1):
            s, e, a = world({"MELON": 100}, [{"MELON": 5}], player=seat,
                            stocks={"MELON": 1_000_000})
            self.assertEqual(s[0].observation.market["prices"]["MELON"], 1)
            base, changed, _, cash = self.pair(s, e, seat, a)
            self.assertEqual(base[0].observation.market, changed[0].observation.market)
            self.assertEqual(cash, 5.0)
            WITNESSES["floor_rescue"] = {"actual_cash_delta": cash, "units": 5,
                                         "public_market_equal": True}

    def test_12_nonlinear_actual_fill_is_not_quoted_cash(self):
        s, e, a = world({"WHEAT": 100}, [{"WHEAT": 20}])
        _, _, _, cash = self.pair(s, e, 0, a)
        quoted = lane.telemetry["quoted_cash"]
        self.assertNotEqual(cash, quoted)
        self.assertGreater(quoted, cash)
        WITNESSES["nonlinear_fill"] = {"quoted_cash": quoted, "actual_cash_delta": cash,
                                       "units": 20}

    def test_13_inventory_order_ambiguity_declines(self):
        for seat in (0, 1):
            for pairs in itertools.permutations((("WHEAT", 5), ("WOOL", 5))):
                s, e, a = world({"WHEAT": 48, "WOOL": 48}, [dict(pairs)], player=seat)
                self.pair(s, e, seat, a, expect_active=False)

    def test_14_whole_vector_stock_coverage_declines(self):
        s, e, a = world({"WHEAT": 100}, [{"WHEAT": 2}, {"CARROT": 3}])
        self.pair(s, e, 0, a, expect_active=False)

    def test_15_guarded_non_neutral_unit_and_market_actions(self):
        for command in (["HARVEST"], ["DROP"], ["PICKUP", "WHEAT", 1],
                        ["PLACE", "WHEAT", 1], ["FEED"], ["FERTILIZE"],
                        ["COLLECT_FERTILIZER"]):
            s, e, a = world({"WHEAT": 100}, [{"WHEAT": 5}])
            a["farmer"] = command
            self.assertIs(self.candidate(s, e, 0, a), a)
        for row in (["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1],
                    ["BUY_ANIMAL", "COW", 1], ["BOGUS"]):
            s, e, a = world({"WHEAT": 100}, [{"WHEAT": 5}], market_rows=[row])
            self.assertIs(self.candidate(s, e, 0, a), a)

    def test_16_last_supported_eod_and_final_day(self):
        for step in (23, 47, 119, 671, 695):
            s, e, a = world({"WHEAT": 100}, [{"WHEAT": 5}], step=step)
            self.pair(s, e, 0, a)
        for step in (0, 22, 118, 696, 718, 719):
            s, e, a = world({"WHEAT": 100}, [{"WHEAT": 5}], step=step)
            self.assertIs(self.candidate(s, e, 0, a), a)

    def test_17_zero_items_and_animals_in_shed(self):
        s, e, a = world({"WHEAT": 3, "CARROT": 3, "COW": 94},
                        [{"WHEAT": 2, "COW": 0}, {}, {"CARROT": 3}])
        self.pair(s, e, 0, a)

    def test_18_disabled_and_strict_admission(self):
        s, e, a = world({"WHEAT": 100}, [{"WHEAT": 5}])
        self.assertIs(self.candidate(s, e, 0, a, enabled=False), a)
        for key, value in (("episodeSteps", True), ("shedCapacity", 99),
                           ("turnsPerDay", 23), ("maxMarketOrdersPerTurn", 9),
                           ("townShopSellInterval", 1), ("townCenterSellInterval", 1)):
            changed_env = copy.deepcopy(e)
            setattr(changed_env.configuration, key, value)
            self.assertIs(self.candidate(s, changed_env, 0, a), a)
        for inventory in ({"WHEAT": True}, {"WHEAT": 1.5}, {"WHEAT": -1}, {"COW": 1}):
            ss, ee, aa = world({"WHEAT": 100}, [inventory])
            self.assertIs(self.candidate(ss, ee, 0, aa), aa)

    def test_19_independent_full_interpreter_matrix(self):
        # Both seats x every product x both floor/normal inventory regimes x
        # room 0..3: 144 full transition pairs with a mixed-product tail.
        checked = 0
        for seat, product, floor, room in itertools.product((0, 1), PRODUCTS, (False, True), range(4)):
            shed = {p: 8 for p in PRODUCTS}
            shed["COW"] = 100 - room - sum(shed.values())
            other = PRODUCTS[(PRODUCTS.index(product) + 1) % len(PRODUCTS)]
            inventories = [{product: room + 2}, {other: 2, product: 1}]
            stocks = {p: 1_000_000 if floor else 10_000 for p in PRODUCTS}
            s, e, a = world(shed, inventories, player=seat, stocks=stocks,
                            rival_rows=[["SELL", "WHEAT", 3]])
            self.pair(s, e, seat, a)
            checked += 1
        self.assertEqual(checked, 144)
        COUNTS["product_seat_stock_room_cells"] = checked

    def test_20_seeded_full_interpreter_worlds(self):
        rng = random.Random(20260911)
        active = 0
        for trial in range(240):
            seat = trial % 2
            room = rng.randrange(5)
            shed = {p: 8 for p in PRODUCTS}
            shed["COW"] = 100 - room - sum(shed.values())
            first = rng.choice(PRODUCTS)
            inventories = [{first: room + rng.randrange(1, 4)}]
            for _ in range(rng.randrange(3)):
                items = rng.sample(PRODUCTS, rng.randrange(1, 4))
                inventories.append({p: rng.randrange(1, 3) for p in items})
            n = rng.randrange(11)
            s, e, a = world(shed, inventories, player=seat, seed=trial,
                            market_rows=[[] for _ in range(n)],
                            stocks={p: rng.randrange(9500, 10501) for p in PRODUCTS},
                            rival_rows=[["SELL", "WHEAT", rng.randrange(40)]])
            # All cargo is provably after a homogeneous capacity boundary;
            # only whole-vector slot exhaustion can veto this bounded matrix.
            vector = lane._discarded_products(inventories, room, PRODUCTS)
            eligible = n + len(vector) <= 10 and n < 10
            self.pair(s, e, seat, a, expect_active=eligible)
            active += eligible
        self.assertGreater(active, 100)
        COUNTS["seeded_worlds"] = 240
        COUNTS["seeded_world_activations"] = active

    def test_21_negative_control_wrong_product_sale_changes_final_shed(self):
        s, e, a = world({"WHEAT": 50, "CARROT": 50}, [{"CARROT": 3}])
        correct = self.candidate(s, e, 0, a)
        bad = copy.deepcopy(correct)
        bad["market"] = [["SELL", "WHEAT", 3]]
        base = advance(s, e, 0, a)
        wrong = advance(s, e, 0, bad)
        self.assertNotEqual(base[0].observation.private, wrong[0].observation.private)
        COUNTS["negative_controls_rejected"] += 1

    def test_22_negative_control_truncated_vector_changes_final_shed(self):
        s, e, a = world({"WHEAT": 50, "CARROT": 50},
                        [{"WHEAT": 2}, {"CARROT": 3}], market_rows=[[] for _ in range(9)])
        self.assertIs(self.candidate(s, e, 0, a), a)
        bad = copy.deepcopy(a)
        bad["market"] += [["SELL", "CARROT", 3], ["SELL", "WHEAT", 2]]
        base = advance(s, e, 0, a)
        wrong = advance(s, e, 0, bad)
        self.assertNotEqual(base[0].observation.private, wrong[0].observation.private)
        COUNTS["negative_controls_rejected"] += 1

    def test_23_negative_control_aggregate_cargo_loses_actor_ownership(self):
        s, e, a = world({"WHEAT": 50, "CARROT": 48}, [{"WHEAT": 2}, {"CARROT": 3}])
        bad = copy.deepcopy(a)
        bad["market"] = [["SELL", "WHEAT", 3]]
        base = advance(s, e, 0, a)
        wrong = advance(s, e, 0, bad)
        self.assertNotEqual(base[0].observation.private, wrong[0].observation.private)
        COUNTS["negative_controls_rejected"] += 1

    def test_24_opponent_cash_effect_is_not_claimed_invariant(self):
        s, e, a = world({"WHEAT": 100}, [{"WHEAT": 20}],
                        rival_rows=[["BUY_PRODUCT", "WHEAT", 20]])
        base, changed, _, own_delta = self.pair(s, e, 0, a)
        rival_delta = changed[0].observation.farms[1]["money"] - base[0].observation.farms[1]["money"]
        self.assertNotEqual(rival_delta, 0)
        WITNESSES["rival_response"] = {"own_cash_delta": own_delta,
                                      "rival_cash_delta": rival_delta,
                                      "one_transition_margin_delta": own_delta - rival_delta}


def main(argv=None):
    global engine, lane
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--lane", type=Path, required=True)
    parser.add_argument("--h3c", type=Path, required=True)
    parser.add_argument("--expected-lane", default=LANE_BLOB)
    parser.add_argument("--expected-h3c", default=H3C_BLOB)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    sources = {"engine": checked_source(args.engine, ENGINE_BLOB),
               "lane": checked_source(args.lane, args.expected_lane),
               "h3c": checked_source(args.h3c, args.expected_h3c)}
    validate_router_adapter_use(sources["lane"])
    kaggle = ModuleType("kaggle_environments")
    utils = ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = forbidden_seed_resolution
    router = ModuleType("r04_full_router")
    router.PRODUCTS = PRODUCTS
    COUNTS.clear()
    WITNESSES.clear()
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"kaggle_environments": kaggle,
                            "kaggle_environments.utils": utils, "r04_full_router": router}))
        engine = load_module("eod_official_engine", args.engine, sources["engine"])
        h3c = load_module("h3c_goose_eod_cap_rescue", args.h3c, sources["h3c"])
        stack.enter_context(patch.dict(sys.modules, {"h3c_goose_eod_cap_rescue": h3c}))
        lane = load_module("eod_lane_under_test", args.lane, sources["lane"])
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(OfficialEodContracts))
    receipt = {"schema": "titan-v4-eod-official-interpreter-v1",
               "passed": result.wasSuccessful(), "optimized": not __debug__,
               "tests_run": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "counts": dict(sorted(COUNTS.items())),
               "sources": {k: {"git_blob": git_blob(v), "bytes": len(v),
                                 "sha256": hashlib.sha256(v).hexdigest()} for k, v in sources.items()},
               "test_git_blob": git_blob(Path(__file__).read_bytes()),
               "witnesses": WITNESSES,
               "scope": "full official interpreter transitions, isolated lane and exact H3c; literal router PRODUCTS adapter",
               "not_claimed": ["R04 materialized package or install ABI", "full-game economic strength", "production promotion"]}
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
