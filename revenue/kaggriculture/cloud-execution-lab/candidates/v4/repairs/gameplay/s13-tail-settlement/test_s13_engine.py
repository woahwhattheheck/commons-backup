# SPDX-License-Identifier: Apache-2.0
"""S13 synthetic transitions using the pinned official engine, not field games.

Only the unavailable framework seed-import is shimmed; every game-transition
function is compiled from the verified original AST without changes. Fixtures
are initialized explicitly, and an attempted seed-resolution call raises.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import itertools
import json
import os
from pathlib import Path
import types
import unittest

import s13_tail_settlement as guard

ENGINE_SHA = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
CONFIG_SHA = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"
RECEIPTS = {"scope": "pinned-engine synthetic transitions, not field economics"}


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
    __setattr__ = dict.__setitem__


def load_engine():
    root = os.environ.get("TITAN_ENGINE_DIR")
    if root is None:
        root = next((p / "reference" / "engine" for p in Path(__file__).resolve().parents
                     if (p / "reference" / "engine" / "kaggriculture.py").is_file()), None)
    if root is None:
        raise RuntimeError("Set TITAN_ENGINE_DIR to the pinned reference/engine directory")
    root = Path(root)
    code = (root / "kaggriculture.py").read_bytes()
    config = (root / "kaggriculture.json").read_bytes()
    if hashlib.sha256(code).hexdigest() != ENGINE_SHA or hashlib.sha256(config).hexdigest() != CONFIG_SHA:
        raise ValueError("official engine/config hash mismatch")
    tree = ast.parse(code)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == "kaggle_environments.utils"]
    if len(imports) != 1 or [alias.name for alias in imports[0].names] != ["resolve_episode_seed"]:
        raise ValueError("unexpected framework import")
    tree.body.remove(imports[0])
    def no_initialize(*args, **kwargs):
        raise AssertionError("fixture must not use framework initialization")
    module = types.ModuleType("_s13_pinned_engine")
    module.__file__ = str(root / "kaggriculture.py")
    module.resolve_episode_seed = no_initialize
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


class S13EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()
        RECEIPTS["engine_sha256"] = ENGINE_SHA
        RECEIPTS["configuration_sha256"] = CONFIG_SHA

    def fixture(self, *, step=717, stock=10, rival_stock=0, inventory=10000,
                shops=(), seat=0, cfg_patch=None, wheat=0):
        e = self.engine
        cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                      for k, v in e.specification["configuration"].items()})
        cfg.update(weedSpawnChance=0)
        cfg.update(cfg_patch or {})
        farms = [e._new_farm(10, 0), e._new_farm(10, 0)]
        market = e._new_market()
        market["inventory"]["MILK"] = inventory
        e._refresh_prices(market)
        town = {"unlocked_shops": list(shops)}
        state = []
        for player in range(2):
            private = e._new_private()
            private["shed"]["MILK"] = stock if player == seat else rival_stock
            private["shed"]["WHEAT"] = wheat if player == seat else 0
            state.append(Struct(observation=Struct(
                player=player, step=step, day=step // cfg.turnsPerDay,
                hour=step % cfg.turnsPerDay, farms=farms, private=private,
                market=market, town=town),
                action={"farmer": ["PASS"], "hands": [], "market": []},
                status="ACTIVE", reward=0))
        return state, Struct(configuration=cfg, done=False, info={"seed": 20260911})

    def project_units(self, obs, selected, cfg):
        """Test-only bounded unit adapter, NOT a current-runtime provider.

        These fixtures intentionally exercise only PASS/DROP/PLACE/PICKUP. For
        those operations there is no atomic PLANT admission to reconstruct.
        The official unit function executes in the official actor order.
        """
        e = self.engine
        farm, private = deepcopy((obs["farms"][obs["player"]], obs["private"]))
        units = [selected.get("farmer", ["PASS"]), *selected.get("hands", [])]
        for idx, work in enumerate(units):
            if not work or work[0] not in {"PASS", "DROP", "PLACE", "PICKUP"}:
                raise ValueError("fixture-only projector received unsupported unit operation")
            e._apply_unit_action(farm, private, idx, work,
                cfg.get("boardSize", 10), obs["step"] // cfg.get("turnsPerDay", 24),
                cfg.get("turnsPerDay", 24), cfg.get("shedCapacity", 100))
        return farm, private

    def compose(self, state, env, *, seat=0, **options):
        return guard.compose_tail_settlement(state[seat].observation, env.configuration,
            state[seat].action, project_units=self.project_units, enabled=True, **options)

    def execute_pair(self, state, env, *, seat=0, **options):
        baseline, be = deepcopy((state, env))
        candidate, ce = deepcopy((state, env))
        selected, report = self.compose(candidate, ce, seat=seat, **options)
        candidate[seat].action = selected
        self.engine.interpreter(baseline, be)
        self.engine.interpreter(candidate, ce)
        return baseline, candidate, report

    def test_engine_and_product_domain(self):
        self.assertEqual(set(self.engine.PRODUCTS), guard.PRODUCTS)
        self.assertEqual(self.engine.specification["configuration"]["episodeSteps"], 720)
        self.assertEqual(self.engine.specification["configuration"]["townShopSellInterval"]["default"], 4)
        with self.assertRaises(AssertionError):
            self.engine.resolve_episode_seed(None)

    def test_both_seats_live_prefix_quantities_and_floor(self):
        cases = 0
        for seat, stock, rival_stock, inventory, cap, suffix in itertools.product(
                (0, 1), (2, 5, 10, 20), (0, 3), (9970, 10000, 10075),
                (1, 2), ([None], [["HIRE"]], [["SELL", "MILK", 999]])):
            state, env = self.fixture(stock=stock, rival_stock=rival_stock,
                                      inventory=inventory, seat=seat,
                                      cfg_patch={"maxMarketOrdersPerTurn": cap})
            rows = [["SELL", "MILK", 1]] if cap == 1 else [["SELL", "MILK", 1], ["SELL", "MILK", 1]]
            state[seat].action["market"] = rows + deepcopy(suffix)
            if rival_stock:
                state[1-seat].action["market"] = [["SELL", "MILK", rival_stock]]
            before = deepcopy(state)
            baseline, candidate, report = self.execute_pair(state, env, seat=seat)
            delta = baseline[seat].observation.private["shed"]["MILK"] - candidate[seat].observation.private["shed"]["MILK"]
            self.assertEqual(delta, stock - cap)
            self.assertEqual(delta, report.get("added_sell_units", {}).get("MILK", 0))
            self.assertEqual(candidate[seat].observation.private["shed"]["MILK"], 0)
            self.assertEqual(candidate[seat].action["market"][cap:], suffix)
            self.assertEqual(candidate[seat].observation.farms[seat]["hands"], [])
            self.assertEqual(state, before)
            cases += 1
        self.assertEqual(cases, 288)
        RECEIPTS["paired_market_cases"] = cases

    def test_exact_drop_pickup_place_and_shared_capacity(self):
        cases = 0
        for seat, operation, shed_milk, shed_wheat, carried in itertools.product(
                (0, 1), ("DROP", "PLACE", "PICKUP"), (5, 10), (0, 89), (1, 4)):
            state, env = self.fixture(stock=shed_milk, wheat=shed_wheat, seat=seat)
            farm, private = state[seat].observation.farms[seat], state[seat].observation.private
            farm["farmer"] = [4, 4]
            private["inventories"] = [{"MILK": carried}]
            work = ["DROP"] if operation == "DROP" else [operation, "MILK", 2]
            state[seat].action = {"farmer": work, "hands": [], "market": [["SELL", "MILK", 1]]}
            projected = self.project_units(state[seat].observation, state[seat].action, env.configuration)[1]["shed"]["MILK"]
            baseline, candidate, report = self.execute_pair(state, env, seat=seat)
            self.assertEqual(candidate[seat].observation.private["shed"]["MILK"], 0)
            self.assertEqual(baseline[seat].observation.private["shed"]["MILK"] -
                             candidate[seat].observation.private["shed"]["MILK"], projected - 1)
            self.assertEqual(candidate[seat].action["farmer"], work)
            self.assertEqual(baseline[seat].observation.private["inventories"],
                             candidate[seat].observation.private["inventories"])
            cases += 1
        self.assertEqual(cases, 48)
        RECEIPTS["unit_capacity_cases"] = cases

    def test_actor_order_pickup_before_hand_drop(self):
        state, env = self.fixture(stock=1, wheat=99)
        farm, private = state[0].observation.farms[0], state[0].observation.private
        farm["farmer"], farm["hands"] = [4, 4], [[5, 4]]
        private["inventories"] = [{}, {"MILK": 3}]
        state[0].action = {"farmer": ["PICKUP", "WHEAT", 3], "hands": [["DROP"]],
                           "market": [["SELL", "MILK", 1]]}
        baseline, candidate, r = self.execute_pair(state, env)
        self.assertEqual(r["added_sell_units"], {"MILK": 3})
        self.assertEqual(candidate[0].observation.private["shed"]["MILK"], 0)
        self.assertEqual(candidate[0].observation.private["shed"]["WHEAT"], 96)
        self.assertEqual(candidate[0].observation.private["inventories"], [{"WHEAT": 3}, {}])

    def test_net_new_and_operational_reserve_with_real_drop(self):
        for net_new, reserve, expected in ((True, None, 4), (False, {"MILK": 4}, 6),
                                            (True, {"MILK": 8}, 2)):
            state, env = self.fixture(stock=7)
            state[0].observation.farms[0]["farmer"] = [4, 4]
            state[0].observation.private["inventories"] = [{"MILK": 3}]
            state[0].action = {"farmer": ["DROP"], "hands": [], "market": [["SELL", "MILK", 1]]}
            baseline, candidate, r = self.execute_pair(state, env, net_new_only=net_new, reserve=reserve)
            self.assertEqual(candidate[0].observation.private["shed"]["MILK"], 10 - expected)
            self.assertEqual(r["added_sell_units"], {"MILK": expected - 1})

    def test_disabled_equals_full_interpreter_parent(self):
        state, env = self.fixture(stock=10, rival_stock=3, step=718)
        state[0].action["market"] = [["SELL", "MILK", 1]]
        candidate, ce = deepcopy((state, env))
        candidate[0].action, r = guard.compose_tail_settlement(None, None,
            candidate[0].action, project_units=lambda *a: self.fail("disabled projection"))
        self.engine.interpreter(state, env)
        self.engine.interpreter(candidate, ce)
        self.assertEqual(state, candidate)
        self.assertEqual(candidate[0].status, "DONE")
        self.assertFalse(r["changed"])

    def test_string_poison_has_real_two_callback_cash_cost(self):
        # Four actual shop copies: restore quotes between callbacks 716 and 717.
        outputs = {}
        for label in ("original_string", "guard_string", "parent"):
            state, env = self.fixture(step=716, stock=12, inventory=10030,
                                      shops=["SMOOTHIE_SHOP"] * 4)
            state[0].action["market"] = [["SELL", "MILK", 6]]
            if label == "original_string":
                state[0].action, _ = guard._donor().compose_tail_settlement(
                    state[0].observation, env.configuration, state[0].action,
                    project_units=self.project_units, shop_consumed="MILK")
            elif label == "guard_string":
                state[0].action, _ = self.compose(state, env, shop_consumed="MILK")
            self.engine.interpreter(state, env)
            for player in state:
                player.observation.step = 717
            state[0].action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 6]]}
            self.engine.interpreter(state, env)
            outputs[label] = {"cash": state[0].observation.farms[0]["money"],
                              "shed": state[0].observation.private["shed"]["MILK"],
                              "inventory": state[0].observation.market["inventory"]["MILK"]}
        self.assertEqual(outputs["original_string"]["cash"], 1026)
        self.assertEqual(outputs["guard_string"]["cash"], 1078)
        self.assertEqual(outputs["parent"], outputs["guard_string"])
        self.assertEqual(outputs["original_string"]["inventory"], outputs["parent"]["inventory"])
        self.assertEqual(outputs["original_string"]["shed"], outputs["parent"]["shed"])
        RECEIPTS["two_callback_poison_witness"] = outputs

    def test_config_and_center_guards_hold_before_actual_pulse(self):
        for step, shop, town in ((717, 3, 24), (700, 24, 4)):
            state, env = self.fixture(step=step, shops=["SMOOTHIE_SHOP"],
                cfg_patch={"townShopSellInterval": shop, "townCenterSellInterval": town})
            state[0].action["market"] = [["SELL", "MILK", 1]]
            out, report = self.compose(state, env)
            self.assertIs(out, state[0].action)
            self.assertFalse(report["changed"])
            before = state[0].observation.market["inventory"]["MILK"]
            self.engine._town_consume(env, state, step)
            self.assertLess(state[0].observation.market["inventory"]["MILK"], before)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    RECEIPTS["tests"] = result.testsRun
    RECEIPTS["failures"] = len(result.failures)
    RECEIPTS["errors"] = len(result.errors)
    path = os.environ.get("S13_ENGINE_RECEIPT")
    if path:
        Path(path).write_text(json.dumps(RECEIPTS, indent=2, sort_keys=True) + "\n")
    raise SystemExit(not result.wasSuccessful())
