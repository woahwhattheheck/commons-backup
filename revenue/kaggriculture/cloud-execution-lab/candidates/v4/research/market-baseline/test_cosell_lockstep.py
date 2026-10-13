#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest

import cosell_lockstep as m


class FakeEngine:
    PRODUCTS = ("WOOL", "WHEAT", "FERTILIZER")

    @staticmethod
    def _new_farm(board_size, money):
        return {"money": float(money)}

    @staticmethod
    def _new_private():
        return {"shed": {}}

    @staticmethod
    def _new_market():
        market = {"inventory": {x: 10000 for x in FakeEngine.PRODUCTS}, "prices": {}}
        FakeEngine._refresh_prices(market)
        return market

    @staticmethod
    def _refresh_prices(market):
        for item in FakeEngine.PRODUCTS:
            market["prices"][item] = max(1, 1000 - market["inventory"][item])

    @staticmethod
    def _parse(row):
        if not isinstance(row, list) or len(row) < 3 or row[0] != "SELL":
            return None
        item, qty = row[1], row[2]
        if item not in FakeEngine.PRODUCTS or type(qty) is not int or qty <= 0:
            return None
        return {"item": item, "remaining": qty}

    @staticmethod
    def _process_market(states, env):
        cap = max(1, int(env.configuration.get("maxMarketOrdersPerTurn", 10)))
        for slot in range(cap):
            orders = []
            for state in states:
                rows = state.action.get("market", [])
                orders.append(FakeEngine._parse(rows[slot]) if slot < len(rows) else None)
            while any(o is not None and o["remaining"] > 0 for o in orders):
                quoted = []
                for player, order in enumerate(orders):
                    if order is None or order["remaining"] <= 0:
                        quoted.append(None)
                        continue
                    item = order["item"]
                    if states[player].observation.private["shed"].get(item, 0) <= 0:
                        quoted.append(None)
                        orders[player] = None
                        continue
                    quoted.append((item, states[0].observation.market["prices"][item]))
                committed = False
                for player, q in enumerate(quoted):
                    if q is None:
                        continue
                    item, price = q
                    private = states[player].observation.private
                    if private["shed"].get(item, 0) <= 0:
                        orders[player] = None
                        continue
                    private["shed"][item] -= 1
                    states[0].observation.farms[player]["money"] += price
                    if price > 1:
                        states[0].observation.market["inventory"][item] += 1
                    orders[player]["remaining"] -= 1
                    committed = True
                if not committed:
                    break
                FakeEngine._refresh_prices(states[0].observation.market)


class CosellOracleTests(unittest.TestCase):
    def test_aligned_cosell_beats_sequential_market_only_on_falling_price(self):
        r = m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=10, rival_qty=10)
        self.assertGreater(r["simultaneous_gain_vs_sequential_market_only"], 0)
        self.assertEqual(r["misaligned_gain_vs_sequential_market_only"], 0)
        self.assertTrue(r["same_terminal_state"])
        self.assertEqual(r["terminal_market_inventory"], 920)

    def test_zero_rival_is_no_effect(self):
        r = m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=10, rival_qty=0)
        self.assertEqual(r["simultaneous_gain_vs_sequential_market_only"], 0)
        self.assertEqual(r["misaligned_gain_vs_sequential_market_only"], 0)

    def test_partial_overlap_only_shields_shared_units(self):
        short = m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=10, rival_qty=3)
        full = m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=10, rival_qty=10)
        self.assertGreater(short["simultaneous_gain_vs_sequential_market_only"], 0)
        self.assertLess(short["simultaneous_gain_vs_sequential_market_only"], full["simultaneous_gain_vs_sequential_market_only"])

    def test_same_callback_misalignment_equals_sequential_market_only(self):
        r = m.compare(FakeEngine, item="WHEAT", inventory=910, self_qty=7, rival_qty=5)
        self.assertEqual(r["misaligned_same_callback_self_revenue"], r["sequential_market_only_self_revenue"])

    def test_report_explicitly_disclaims_next_callback_semantics(self):
        r = m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=2, rival_qty=2)
        self.assertTrue(any("not a next-callback simulation" in x for x in r["limits"]))
        self.assertNotIn("wait_behind_self_revenue", r)
        self.assertNotIn("simultaneous_gain_vs_wait", r)
        self.assertNotIn("misaligned_gain_vs_wait", r)

    def test_quantity_type_poison_fails_closed(self):
        for bad in (True, 1.0, "1", -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.compare(FakeEngine, item="WOOL", inventory=900, self_qty=bad, rival_qty=1)

    def test_unknown_item_fails_closed(self):
        with self.assertRaises(ValueError):
            m.compare(FakeEngine, item="NOT_REAL", inventory=900, self_qty=1, rival_qty=1)

    def test_curve_preserves_requested_inventory_points(self):
        rows = m.collision_curve(FakeEngine, item="WOOL", inventories=[900, 910, 920], quantity=2)
        self.assertEqual([x["inventory"] for x in rows], [900, 910, 920])
        self.assertTrue(all(x["simultaneous_gain_vs_sequential_market_only"] > 0 for x in rows))

    def test_floor_transition_refuses_unequal_terminal_counterfactual(self):
        with self.assertRaises(AssertionError):
            m.compare(FakeEngine, item="WOOL", inventory=998, self_qty=1, rival_qty=1)

    def test_engine_snapshot_uses_captured_json_after_path_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            engine_path = root / "kaggriculture.py"
            spec_path = root / "kaggriculture.json"
            source = (
                "from pathlib import Path\n"
                "with open(Path(__file__).with_suffix('.json')) as f:\n"
                "    SPEC = f.read()\n"
            ).encode()
            spec_path.write_text("captured", encoding="utf-8")
            captured = spec_path.read_bytes()
            spec_path.write_text("replacement", encoding="utf-8")
            module = m._exec_captured_engine(engine_path, source, spec_path, captured)
            self.assertEqual(module.SPEC, "captured")
            self.assertEqual(spec_path.read_text(encoding="utf-8"), "replacement")

    def test_engine_snapshot_rejects_undeclared_file_open(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            engine_path = root / "kaggriculture.py"
            spec_path = root / "kaggriculture.json"
            other = root / "other.json"
            spec_path.write_text("captured", encoding="utf-8")
            other.write_text("ambient", encoding="utf-8")
            source = (
                "from pathlib import Path\n"
                "with open(Path(__file__).with_name('other.json')) as f:\n"
                "    VALUE = f.read()\n"
            ).encode()
            with self.assertRaises(ValueError):
                m._exec_captured_engine(engine_path, source, spec_path, spec_path.read_bytes())

    def test_engine_snapshot_fences_ambient_kaggle_seed_import_and_restores_modules(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            engine_path = root / "kaggriculture.py"
            spec_path = root / "kaggriculture.json"
            spec_path.write_text("captured", encoding="utf-8")
            source = (
                "from kaggle_environments.utils import resolve_episode_seed\n"
                "RESOLVER = resolve_episode_seed\n"
            ).encode()
            previous_package = sys.modules.get("kaggle_environments")
            previous_utils = sys.modules.get("kaggle_environments.utils")
            had_package = "kaggle_environments" in sys.modules
            had_utils = "kaggle_environments.utils" in sys.modules
            package = types.ModuleType("kaggle_environments")
            package.__path__ = []
            util = types.ModuleType("kaggle_environments.utils")
            util.resolve_episode_seed = lambda *_a, **_k: "ambient"
            package.utils = util
            sys.modules["kaggle_environments"] = package
            sys.modules["kaggle_environments.utils"] = util
            try:
                module = m._exec_captured_engine(engine_path, source, spec_path, spec_path.read_bytes())
                with self.assertRaises(ValueError):
                    module.RESOLVER(None)
                self.assertIs(sys.modules["kaggle_environments"], package)
                self.assertIs(sys.modules["kaggle_environments.utils"], util)
            finally:
                if had_utils:
                    sys.modules["kaggle_environments.utils"] = previous_utils
                else:
                    sys.modules.pop("kaggle_environments.utils", None)
                if had_package:
                    sys.modules["kaggle_environments"] = previous_package
                else:
                    sys.modules.pop("kaggle_environments", None)

    def test_repository_engine_exact_when_present(self):
        path = m.default_engine_path()
        if not path.is_file():
            self.skipTest("repository engine not mounted in this execution seat")
        engine = m.load_engine(path)
        self.assertEqual(engine._cosell_source_identity["python_git_blob"], m.ENGINE_BLOB)
        self.assertEqual(engine._cosell_source_identity["json_git_blob"], m.ENGINE_JSON_BLOB)
        r = m.compare(engine, item="WOOL", inventory=10000, self_qty=10, rival_qty=10)
        self.assertEqual(r["terminal_market_inventory"], 10020)
        self.assertEqual(r["simultaneous_self_revenue"], 1934)
        self.assertEqual(r["misaligned_same_callback_self_revenue"], 1873)
        self.assertEqual(r["sequential_market_only_self_revenue"], 1873)
        self.assertEqual(r["simultaneous_gain_vs_sequential_market_only"], 61)
        self.assertEqual(r["misaligned_gain_vs_sequential_market_only"], 0)
        with self.assertRaises(AssertionError):
            m.compare(engine, item="WOOL", inventory=10058, self_qty=1, rival_qty=1)

    def test_repository_engine_town_phase_breaks_market_only_equivalence(self):
        path = m.default_engine_path()
        if not path.is_file():
            self.skipTest("repository engine not mounted in this execution seat")
        engine = m.load_engine(path)
        sequential = m.simulate_sequential_market_only(engine, item="WOOL", inventory=10000, self_qty=10, rival_qty=10)
        states, env = m._world(engine, item="WOOL", inventory=10000, self_qty=10, rival_qty=10)
        town = engine._new_town()
        for state in states:
            state.observation.town = town
        m._market_call(engine, states, env, [m._sell("WOOL", 10)], [])
        self.assertEqual(states[0].observation.market["inventory"]["WOOL"], 10010)
        engine._town_consume(env, states, 0)
        self.assertEqual(states[0].observation.market["inventory"]["WOOL"], 10009)
        m._market_call(engine, states, env, [], [m._sell("WOOL", 10)])
        intercallback_revenue = m._money(states, 1) - m.STARTING_MONEY
        self.assertEqual(states[0].observation.market["inventory"]["WOOL"], 10019)
        self.assertGreater(intercallback_revenue, sequential["self_revenue"])
        self.assertNotEqual(intercallback_revenue, sequential["self_revenue"])


if __name__ == "__main__":
    unittest.main()
