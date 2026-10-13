# SPDX-License-Identifier: Apache-2.0
"""Exact-source seam and component checks, NOT a full-package/economics gate.

H3c/router dependencies are explicit test doubles. Unchanged predecessor
semantics are also checked structurally. SELL/drop uses engine excerpts.
"""
from __future__ import annotations

import ast
import copy
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import compose_eod_interval as builder
import eod_interval
from engine_oracle import _commit_unit, _drop_inventories_to_shed

ROOT = Path(__file__).resolve().parent
CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


def deps():
    h = types.ModuleType("h3c_goose_eod_cap_rescue")
    h._MISSING = object()
    h.STANDARD_CONFIG = {k: v for k, v in CONFIG.items() if k != "episodeSteps"}
    h._cfg = lambda cfg, key: cfg.get(key, h._MISSING) if isinstance(cfg, dict) else h._MISSING
    h._standard_configuration = lambda cfg: (isinstance(cfg, dict) and
        all(type(cfg.get(k)) is int and cfg[k] == v for k, v in h.STANDARD_CONFIG.items()))
    h._parent_rows = lambda a: ([a["farmer"], *a["hands"]]
        if isinstance(a, dict) and "farmer" in a and isinstance(a.get("hands"), list) else None)
    h._strict_inventory_total = lambda inv: (sum(inv.values()) if isinstance(inv, dict)
        and all(type(n) is int and n >= 0 for n in inv.values()) else None)
    r = types.ModuleType("r04_full_router")
    r.PRODUCTS = sorted(eod_interval.PRODUCTS)
    return {h.__name__: h, r.__name__: r}


def world():
    farm = {"farmer": [4, 4], "hands": []}
    obs = {"step": 119, "player": 0, "farms": [farm, copy.deepcopy(farm)],
           "private": {"shed": {"WHEAT": 48, "WOOL": 48},
                       "inventories": [{"WHEAT": 5, "WOOL": 5}], "seeds": {}},
           "market": {"prices": {p: 10 for p in eod_interval.PRODUCTS}}}
    return obs, {"farmer": ["PASS"], "hands": [], "market": []}


class ExistingEodSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = (ROOT/"donor_9ad40924.py").read_bytes()
        cls.solver = (ROOT/"eod_interval.py").read_bytes()
        cls.composed = builder.compose(cls.donor, cls.solver)

    def setUp(self):
        self.dependencies = patch.dict(sys.modules, deps())
        self.dependencies.start()
        self.addCleanup(self.dependencies.stop)
        self.original, self.successor = types.ModuleType("predecessor"), types.ModuleType("successor")
        exec(compile(self.donor, "<pinned-EOD-donor>", "exec"), self.original.__dict__)
        exec(compile(self.composed, "<composed-EOD>", "exec"), self.successor.__dict__)

    def test_exact_byte_pins_and_deterministic_output(self):
        self.assertEqual(builder.git_blob(self.donor), builder.DONOR_BLOB)
        self.assertEqual(builder.git_blob(self.solver), builder.SOLVER_BLOB)
        self.assertEqual(builder.compose(self.donor, self.solver), self.composed)
        for a, b in ((self.donor+b"\n", self.solver), (self.donor, self.solver+b"\n")):
            with self.assertRaises(ValueError):
                builder.compose(a, b)

    def test_only_vector_selection_changes_in_existing_executable_body(self):
        old, new = ast.parse(self.donor), ast.parse(self.composed)
        old_funcs = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
        new_funcs = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
        for name, original in old_funcs.items():
            actual = copy.deepcopy(new_funcs[name])
            if name == "apply_eod_capacity_rescue":
                original = copy.deepcopy(original)
                actual.body[0] = copy.deepcopy(original.body[0])  # documentation only
                replaced = 0
                for i, node in enumerate(actual.body):
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "discarded"
                                                           for t in node.targets):
                        actual.body[i] = copy.deepcopy(next(n for n in original.body if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "discarded" for t in n.targets)))
                        replaced += 1
                self.assertEqual(replaced, 1)
            self.assertEqual(ast.dump(actual), ast.dump(original), name)
        old_names = {n.id for node in old.body for n in ast.walk(node)
                     if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        new_globals = {n.id for node in ast.parse(self.solver).body if isinstance(node, ast.Assign)
                       for n in node.targets if isinstance(n, ast.Name)}
        self.assertFalse(old_names & new_globals)

    def test_predecessor_rejects_new_witness_successor_emits_exact_sales(self):
        obs, parent = world()
        before = copy.deepcopy((obs, parent))
        self.assertIs(self.original.apply_eod_capacity_rescue(parent, obs, CONFIG, enabled=True), parent)
        out = self.successor.apply_eod_capacity_rescue(parent, obs, CONFIG, enabled=True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 1], ["SELL", "WOOL", 1]])
        self.assertEqual((obs, parent), before)
        self.assertEqual(self.successor.telemetry["rescued_units"], 2)
        # Re-applying to final action is a no-op: incumbent shed-changing row guard.
        self.assertIs(self.successor.apply_eod_capacity_rescue(out, obs, CONFIG, enabled=True), out)

    def test_full_private_transition_both_seats_and_key_orders(self):
        for seat in (0, 1):
            for reverse in (False, True):
                obs, parent = world()
                obs["player"] = seat
                if reverse:
                    obs["private"]["inventories"][0] = {"WOOL": 5, "WHEAT": 5}
                out = self.successor.apply_eod_capacity_rescue(parent, obs, CONFIG, enabled=True)
                baseline = copy.deepcopy(obs["private"])
                candidate = copy.deepcopy(baseline)
                _drop_inventories_to_shed(baseline, 100)
                market = {"inventory": {p: 10000 for p in eod_interval.PRODUCTS}}
                farm = {"money": 1000}
                for op, p, n in out["market"]:
                    for _ in range(n):
                        self.assertTrue(_commit_unit(op, p, 10, farm, candidate, market))
                _drop_inventories_to_shed(candidate, 100)
                self.assertEqual(candidate, baseline)
                self.assertEqual(farm["money"], 1020)

    def test_disabled_and_failed_guards_keep_exact_parent_identity(self):
        obs, parent = world()
        self.assertIs(self.successor.apply_eod_capacity_rescue(parent, obs, CONFIG), parent)
        for row in (["HARVEST"], ["DROP"], ["FEED"], ["PICKUP", "WHEAT", 1], [{}]):
            bad = copy.deepcopy(parent); bad["farmer"] = row
            self.assertIs(self.successor.apply_eod_capacity_rescue(bad, obs, CONFIG, enabled=True), bad)
        for row in (["SELL", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1], ["BUY_ANIMAL", "COW", 1], ["BOGUS"]):
            bad = copy.deepcopy(parent); bad["market"] = [row]
            self.assertIs(self.successor.apply_eod_capacity_rescue(bad, obs, CONFIG, enabled=True), bad)
        for step in (118, 696, 718, 719, True, "119"):
            bad = copy.deepcopy(obs); bad["step"] = step
            self.assertIs(self.successor.apply_eod_capacity_rescue(parent, bad, CONFIG, enabled=True), parent)
        for key in CONFIG:
            bad_cfg = dict(CONFIG); bad_cfg[key] = True
            self.assertIs(self.successor.apply_eod_capacity_rescue(parent, obs, bad_cfg, enabled=True), parent)
        for value in (True, 1.0, "1", None, 0, -1):
            bad = copy.deepcopy(obs); bad["market"]["prices"]["WOOL"] = value
            self.assertIs(self.successor.apply_eod_capacity_rescue(parent, bad, CONFIG, enabled=True), parent)

    def test_raw_slot_budget_and_non_shed_rows_are_preserved(self):
        obs, parent = world()
        parent["market"] = [["BUY_SEED", "WHEAT", 1]] + [[] for _ in range(7)]
        out = self.successor.apply_eod_capacity_rescue(parent, obs, CONFIG, enabled=True)
        self.assertEqual(out["market"][:8], parent["market"])
        self.assertEqual(len(out["market"]), 10)
        parent["market"].append([])
        self.assertIs(self.successor.apply_eod_capacity_rescue(parent, obs, CONFIG, enabled=True), parent)

    def test_exclusive_output_refuses_donor_or_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/"out.py"
            command = [sys.executable, "-B", str(ROOT/"compose_eod_interval.py"),
                       str(ROOT/"donor_9ad40924.py"), str(target)]
            first = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(target.read_bytes(), self.composed)
            second = subprocess.run(command, capture_output=True, check=False)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(target.read_bytes(), self.composed)
            self.assertEqual((ROOT/"donor_9ad40924.py").read_bytes(), self.donor)


if __name__ == "__main__":
    unittest.main()
