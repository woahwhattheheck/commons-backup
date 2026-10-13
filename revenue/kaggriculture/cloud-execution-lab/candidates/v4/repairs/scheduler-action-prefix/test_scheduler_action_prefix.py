# SPDX-License-Identifier: Apache-2.0
"""Exact-source component regressions, not full engine/economic evaluation.

Executes actual scheduler AST definitions. Only external Arlene/market economics
and mechanics are deterministic test doubles. --predecessor runs the same
mechanism cases on the unrepaired source and must report failures.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

from scheduler_action_prefix import (
    SOURCE_GIT_BLOB, SourceMismatch, git_blob_sha, transform,
)

HERE = Path(__file__).resolve().parent
BEFORE = (HERE / "scheduler_before.py").read_bytes()
AFTER = transform(BEFORE)
TEST_SOURCE = AFTER
PROD_NAMES = {"post_units", "_order_spend", "_engine_market_prefix", "SellScheduler"}


def action(market=None, farmer=None):
    return {"farmer": farmer or ["PASS"], "hands": [],
            "market": [] if market is None else market}


def load_scheduler(source: bytes):
    """Execute production methods unchanged, with explicit external doubles."""
    def unit(farm, private, actor, command, *_):
        if command and command[0] == "DROP":
            cargo = private["inventories"][actor]
            for item, quantity in cargo.items():
                private["shed"][item] = private["shed"].get(item, 0) + quantity
            private["inventories"][actor] = {}

    def eod(private, capacity):
        for actor in range(len(private["inventories"])):
            unit({}, private, actor, ["DROP"])

    mechanics = types.SimpleNamespace(
        ANIMALS={"COW": {"cost": 100, "product": "MILK"}},
        CROPS={"CARROT": {"seed": 3}, "WHEAT": {"seed": 2}},
        LAND_PRICES=[10, 20, 30], LAND_ORDER=["NE", "SW", "SE"],
        _hire_cost=lambda hires, mult: (hires + 1) * 7 * mult,
        market_price=lambda *args: 5,
        _apply_unit_action=unit, _drop_inventories_to_shed=eod,
        _spawn_hand=lambda *args: [4, 4],
    )
    parent = types.SimpleNamespace(
        Agent=lambda: None, DECISIONS=[], PASS=action(),
        _terminal_settlement=lambda shed, prices, orders: orders,
    )
    namespace = {
        "copy": copy, "m": mechanics, "parent": parent,
        "detached_json_value": copy.deepcopy, "PRODUCTS": ("CARROT", "MELON"),
        "HORIZON": 8, "absorption": lambda *args: 1,
    }
    parsed = ast.parse(source.decode("utf-8"))
    nodes = [node for node in parsed.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef))
             and node.name in PROD_NAMES]
    if not {"post_units", "_order_spend", "SellScheduler"}.issubset({n.name for n in nodes}):
        raise RuntimeError("production AST definitions missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<actual-scheduler-methods>", "exec"), namespace)
    return namespace


def fixture(source=None, market=None, *, cap=1, shed=None, step=4, future=None,
            planned=None, mode="candidate", probe_plans=(), selected_plan=None):
    ns = load_scheduler(TEST_SOURCE if source is None else source)
    base = action(market)
    route = [action() for _ in range(24)]
    for t, a in (future or {}).items():
        route[t] = copy.deepcopy(a)
    obs = {"step": step, "player": 0, "farms": [
        {"tiles": [[None]], "hands": [], "money": 10000,
         "hires_today": 0, "unlocked_quadrants": ["NW"]},
        {"tiles": [[None]], "hands": []}],
        "private": {"shed": dict({"CARROT": 5} if shed is None else shed),
                    "seeds": {}, "inventories": [{}]},
        "market": {"inventory": {"CARROT": 0, "MELON": 0, "WHEAT": 0},
                   "prices": {"CARROT": 10, "MELON": 10}, "params": None},
        "town": {"unlocked_shops": []}}
    config = {"shedCapacity": 100}
    if cap is not None:
        config["maxMarketOrdersPerTurn"] = cap
    scheduler = ns["SellScheduler"](mode)
    scheduler.controller = types.SimpleNamespace(R=[route], cur=0, act=lambda _: base)
    scheduler.planned = copy.deepcopy(planned or {})
    calls = []

    def optimizer(**kwargs):
        calls.append({"item": kwargs["item"], "reference": kwargs["reference"],
                      "admissions": [kwargs["capacity_ok"](p) for p in probe_plans]})
        plan = kwargs["reference"] if selected_plan is None else selected_plan
        # An accepted economics result is synthetic; no economic claim is made.
        info = {"item": kwargs["item"], "quantity": kwargs["quantity"],
                "plan": list(plan), "worst_relative_gain": 0 if selected_plan is None else 1,
                "forced_feasibility": False}
        return plan, info

    ns["optimize_lot"] = optimizer
    return types.SimpleNamespace(ns=ns, scheduler=scheduler, base=base, route=route,
                                 obs=obs, config=config, calls=calls)


def run_case(case):
    snapshot = copy.deepcopy((case.obs, case.base, case.route, case.config))
    result = case.scheduler.act(case.obs, case.config)
    if (case.obs, case.base, case.route, case.config) != snapshot:
        raise AssertionError("scheduler mutated observation, parent action, route or config")
    return result


class MechanismTests(unittest.TestCase):
    def test_current_suffix_does_not_enter_baseline(self):
        c = fixture(market=[[], ["SELL", "CARROT", 5]])
        run_case(c)
        self.assertEqual(c.calls[0]["reference"], ((4, 0),))

    def test_future_suffix_does_not_enter_reference(self):
        c = fixture(future={5: action([[], ["SELL", "CARROT", 5]])})
        run_case(c)
        self.assertEqual(c.calls[0]["reference"], ((4, 0),))

    def test_current_suffix_cannot_prove_an_executable_order_slot(self):
        c = fixture(market=[[], ["SELL", "CARROT", 5]], probe_plans=[((4, 1),)])
        run_case(c)
        self.assertEqual(c.calls[0]["admissions"], [False])

    def test_future_suffix_cannot_prove_an_executable_order_slot(self):
        c = fixture(future={5: action([[], ["SELL", "CARROT", 5]])},
                    probe_plans=[((5, 1),)])
        run_case(c)
        self.assertEqual(c.calls[0]["admissions"], [False])

    def test_full_prefix_counts_only_executable_offered_quantity(self):
        c = fixture(market=[["SELL", "CARROT", 1], ["SELL", "CARROT", 99]],
                    probe_plans=[((4, 1),), ((4, 2),)])
        run_case(c)
        self.assertEqual(c.calls[0]["admissions"], [True, False])

    def test_inert_sale_does_not_retire_pending_or_future_plan(self):
        c = fixture(market=[[], ["SELL", "CARROT", 5]], planned={"CARROT": [(6, 5)]})
        result = run_case(c)
        self.assertEqual(c.scheduler.pending["CARROT"], 5)
        self.assertEqual(c.scheduler.planned, {"CARROT": [(6, 5)]})
        self.assertEqual(result["market"], c.base["market"])

    def test_pending_deducts_only_prefix_quantity(self):
        c = fixture(market=[["SELL", "CARROT", 2], ["SELL", "CARROT", 3]],
                    planned={"CARROT": [(6, 3)]})
        run_case(c)
        self.assertEqual(c.scheduler.pending["CARROT"], 3)
        self.assertEqual(c.scheduler.planned, {"CARROT": [(6, 3)]})

    def test_inert_suffix_bytes_survive_selected_deferral(self):
        suffix = [["SELL", "CARROT", 5], ["SELL", "MELON", 80]]
        c = fixture(market=[[]] + suffix, selected_plan=((4, 0), (6, 5)))
        out = run_case(c)
        self.assertEqual(out["market"], [[]] + suffix)
        self.assertEqual(c.scheduler.pending["CARROT"], 5)

    def test_suffix_is_not_parsed(self):
        for raw in (None, 0, {"opaque": [1]}, ["SELL"], ["SELL", "CARROT", "bad"]):
            with self.subTest(raw=raw):
                c = fixture(market=[[], raw])
                out = run_case(c)
                self.assertEqual(out["market"], [[], raw])
                self.assertEqual(c.scheduler.pending["CARROT"], 5)

    def test_raw_slot_fence_at_cap(self):
        for cap in (1, 3, 10):
            for index in (cap - 1, cap, cap + 1):
                with self.subTest(cap=cap, index=index):
                    c = fixture(market=[[] for _ in range(index)] + [["SELL", "CARROT", 5]], cap=cap)
                    out = run_case(c)
                    self.assertEqual(out["market"], c.base["market"])
                    self.assertEqual(c.scheduler.pending["CARROT"], 0 if index < cap else 5)
                    self.assertEqual(dict(c.calls[0]["reference"])[4], 5 if index < cap else 0)

    def test_default_cap_is_ten_raw_slots(self):
        c = fixture(market=[[]] * 10 + [["SELL", "CARROT", 5]], cap=None)
        run_case(c)
        self.assertEqual(c.scheduler.pending["CARROT"], 5)

    def test_nonpositive_cap_allows_one_append(self):
        for cap in (0, -1, -20):
            with self.subTest(cap=cap):
                c = fixture(cap=cap, planned={"CARROT": [(4, 5)]})
                self.assertEqual(run_case(c)["market"], [["SELL", "CARROT", 5]])
                self.assertEqual(c.scheduler.pending["CARROT"], 0)

    def test_nonpositive_cap_rejects_second_raw_slot(self):
        for cap in (0, -1, -20):
            with self.subTest(cap=cap):
                c = fixture(market=[[], ["SELL", "CARROT", 5]], cap=cap)
                run_case(c)
                self.assertEqual(c.scheduler.pending["CARROT"], 5)

    def test_cash_forecast_ignores_current_suffix_spending(self):
        for row in (["HIRE"], ["BUY_SEED", "CARROT", 3], ["BUY_PRODUCT", "WHEAT", 2], ["BUY_LAND"]):
            with self.subTest(row=row):
                c = fixture(market=[[], row])
                snapshot = copy.deepcopy((c.obs, c.base))
                self.assertEqual(c.scheduler.cash_reserve(c.obs, c.config, c.base, 4), 0)
                self.assertEqual((c.obs, c.base), snapshot)

    def test_cash_forecast_ignores_future_suffix_spending(self):
        c = fixture(future={5: action([[], ["HIRE"]])})
        self.assertEqual(c.scheduler.cash_reserve(c.obs, c.config, c.base, 5), 0)

    def test_cash_forecast_keeps_executable_spending(self):
        c = fixture(market=[["HIRE"], ["HIRE"]])
        self.assertEqual(c.scheduler.cash_reserve(c.obs, c.config, c.base, 4), 7)

    def test_receipt_suffix_sell_cannot_invent_room_before_drop(self):
        c = fixture(market=[[], ["SELL", "MELON", 1]], shed={"CARROT": 1, "MELON": 98},
                    future={5: action(farmer=["DROP"])})
        c.obs["private"]["inventories"] = [{"WHEAT": 1}]
        farm, private = c.ns["post_units"](c.obs, c.base, c.config)
        feasible = c.scheduler.receipt_profile(c.obs, c.base, farm, private, 5, "CARROT", c.config)
        self.assertFalse(feasible(((5, 1),)))

    def test_receipt_future_suffix_sell_cannot_invent_room(self):
        c = fixture(shed={"CARROT": 1, "MELON": 98},
                    future={5: action([[], ["SELL", "MELON", 1]]), 6: action(farmer=["DROP"])})
        c.obs["private"]["inventories"] = [{"WHEAT": 1}]
        farm, private = c.ns["post_units"](c.obs, c.base, c.config)
        feasible = c.scheduler.receipt_profile(c.obs, c.base, farm, private, 6, "CARROT", c.config)
        self.assertFalse(feasible(((6, 1),)))

    def test_receipt_suffix_buy_cannot_invent_stock(self):
        c = fixture(market=[[], ["BUY_PRODUCT", "WHEAT", 100]])
        farm, private = c.ns["post_units"](c.obs, c.base, c.config)
        feasible = c.scheduler.receipt_profile(c.obs, c.base, farm, private, 4, "CARROT", c.config)
        self.assertTrue(feasible(((4, 0),)))

    def test_receipt_suffix_hire_cannot_spawn_phantom_actor(self):
        c = fixture(market=[[], ["HIRE"]])
        def forbidden_spawn(*args):
            raise AssertionError("inert suffix reached actor spawning")
        c.ns["m"]._spawn_hand = forbidden_spawn
        farm, private = c.ns["post_units"](c.obs, c.base, c.config)
        self.assertTrue(c.scheduler.receipt_profile(c.obs, c.base, farm, private, 4, "CARROT", c.config)(((4, 0),)))

    def test_prefix_outputs_and_state_match_original_when_cap_does_not_bind(self):
        cases = [[], [[]], [["SELL", "CARROT", 2]],
                 [[], ["SELL", "CARROT", 2]],
                 [["HIRE"], ["SELL", "CARROT", 3]],
                 [["BUY_SEED", "CARROT", 1], ["SELL", "CARROT", 5]]]
        for mode in ("candidate", "naive"):
            for market in cases:
                with self.subTest(mode=mode, market=market):
                    old = fixture(source=BEFORE, market=copy.deepcopy(market), cap=10, mode=mode)
                    new = fixture(market=copy.deepcopy(market), cap=10, mode=mode)
                    self.assertEqual(run_case(new), run_case(old))
                    self.assertEqual(new.scheduler.pending, old.scheduler.pending)
                    self.assertEqual(new.scheduler.planned, old.scheduler.planned)
                    self.assertEqual(new.scheduler.diagnostics, old.scheduler.diagnostics)

    def test_nonmarket_commands_preserved_and_no_aliasing(self):
        c = fixture(market=[[], ["SELL", "CARROT", 5]])
        c.base["farmer"] = ["NORTH"]
        c.base["hands"] = [["PASS"]]
        out = run_case(c)
        self.assertEqual(out["farmer"], c.base["farmer"])
        self.assertEqual(out["hands"], c.base["hands"])
        out["market"][1][2] = 999
        self.assertEqual(c.base["market"][1][2], 5)

    def test_terminal_path_unchanged(self):
        old = fixture(source=BEFORE, market=[[], ["SELL", "CARROT", 5]], step=718)
        new = fixture(market=[[], ["SELL", "CARROT", 5]], step=718)
        self.assertEqual(run_case(new), run_case(old))
        self.assertEqual(new.scheduler.pending, old.scheduler.pending)

    def test_empty_shed_suffix_still_preserved(self):
        c = fixture(market=[[], ["SELL", "CARROT", 5]], shed={})
        self.assertEqual(run_case(c)["market"], c.base["market"])
        self.assertEqual(c.scheduler.pending, {})

    def test_future_executable_sell_remains_in_reference(self):
        c = fixture(future={5: action([["SELL", "CARROT", 2]])})
        run_case(c)
        self.assertEqual(c.calls[0]["reference"], ((4, 0), (5, 2)))

    def test_withheld_prefix_sell_keeps_its_raw_slot(self):
        c = fixture(market=[["SELL", "CARROT", 5], ["HIRE"]],
                    selected_plan=((4, 0), (6, 5)))
        self.assertEqual(run_case(c)["market"], [[], ["HIRE"]])
        self.assertEqual(c.scheduler.pending["CARROT"], 5)


    def test_suffix_equivalence_matrix(self):
        suffixes = [["SELL", "CARROT", 5], ["SELL", "MELON", 100],
                    ["BUY_PRODUCT", "WHEAT", 100], ["HIRE"], None, ["SELL"]]
        count = 0
        for cap in (1, 3, 10):
            for offered in (0, 2, 5):
                prefix = [[] for _ in range(cap)]
                if offered:
                    prefix[-1] = ["SELL", "CARROT", offered]
                for raw in suffixes:
                    for future_only in (False, True):
                        with self.subTest(cap=cap, offered=offered, raw=raw, future=future_only):
                            kwargs = {"cap": cap, "planned": {"CARROT": [(6, 1)]},
                                      "probe_plans": [((4, 1),), ((5, 1),)]}
                            if future_only:
                                short = fixture(future={5: action(copy.deepcopy(prefix))}, **kwargs)
                                extended = fixture(future={5: action(copy.deepcopy(prefix + [raw]))}, **kwargs)
                            else:
                                short = fixture(market=copy.deepcopy(prefix), **kwargs)
                                extended = fixture(market=copy.deepcopy(prefix + [raw]), **kwargs)
                            short_out, long_out = run_case(short), run_case(extended)
                            self.assertEqual(long_out["market"][:cap], short_out["market"][:cap])
                            self.assertEqual(extended.calls, short.calls)
                            self.assertEqual(extended.scheduler.pending, short.scheduler.pending)
                            self.assertEqual(extended.scheduler.planned, short.scheduler.planned)
                            if not future_only:
                                self.assertEqual(long_out["market"][cap:], [raw])
                            count += 1
        self.assertEqual(count, 108)

class TransformerTests(unittest.TestCase):
    def test_exact_predecessor_and_determinism(self):
        self.assertEqual(git_blob_sha(BEFORE), SOURCE_GIT_BLOB)
        self.assertEqual(AFTER, transform(BEFORE))
        self.assertEqual((HERE / "scheduler_before.py").read_bytes(), BEFORE)

    def test_rejects_drift_reapply_and_wrong_type(self):
        for wrong in (BEFORE + b"\n", BEFORE[:-1], AFTER):
            with self.subTest(sha=git_blob_sha(wrong)), self.assertRaises(SourceMismatch):
                transform(wrong)
        with self.assertRaises(TypeError):
            transform(BEFORE.decode())

    def test_one_helper_six_consumers(self):
        tree = ast.parse(AFTER)
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name == "_engine_market_prefix" for n in tree.body), 1)
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "_engine_market_prefix" for n in ast.walk(tree)), 6)

    def test_unrelated_ast_definitions_unchanged(self):
        old = ast.parse(BEFORE)
        new = ast.parse(AFTER)
        before = [ast.dump(n, include_attributes=False) for n in old.body if not isinstance(n, ast.ClassDef) or n.name != "SellScheduler"]
        after = [ast.dump(n, include_attributes=False) for n in new.body
                 if not (isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
                 and not (isinstance(n, ast.FunctionDef) and n.name == "_engine_market_prefix")]
        self.assertEqual(before, after)
        old_class = next(n for n in old.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
        new_class = next(n for n in new.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
        for name in ("__init__", "rival_supply", "observe"):
            self.assertEqual(ast.dump(next(n for n in old_class.body if n.name == name)),
                             ast.dump(next(n for n in new_class.body if n.name == name)))

    def test_shared_helper_normalization_and_cap_clamp(self):
        prefix = load_scheduler(AFTER)["_engine_market_prefix"]
        for bad in (None, "market", ([], ["HIRE"]), {}):
            self.assertEqual(prefix({"market": bad}, {}), [])
        for cap in (-1, 0, 1):
            rows = [[], ["HIRE"]]
            self.assertEqual(prefix({"market": rows}, {"maxMarketOrdersPerTurn": cap}), [[]])
            self.assertEqual(rows, [[], ["HIRE"]])

    def test_cli_readonly_and_bad_source_has_no_stdout(self):
        before = (HERE / "scheduler_before.py").read_bytes()
        for optimized in (False, True):
            command = [sys.executable] + (["-O"] if optimized else []) + [str(HERE / "scheduler_action_prefix.py")]
            good = subprocess.run(command + [str(HERE / "scheduler_before.py")], capture_output=True, timeout=10)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout, AFTER)
            self.assertEqual((HERE / "scheduler_before.py").read_bytes(), before)
            with tempfile.TemporaryDirectory() as temp:
                bad_path = Path(temp) / "wrong.py"
                bad_path.write_bytes(before + b"\n")
                bad = subprocess.run(command + [str(bad_path)], capture_output=True, timeout=10)
                self.assertEqual(bad.returncode, 2)
                self.assertEqual(bad.stdout, b"")
                self.assertEqual(bad_path.read_bytes(), before + b"\n")


if __name__ == "__main__":
    if "--predecessor" in sys.argv:
        sys.argv.remove("--predecessor")
        TEST_SOURCE = BEFORE
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(MechanismTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    unittest.main(verbosity=2)
