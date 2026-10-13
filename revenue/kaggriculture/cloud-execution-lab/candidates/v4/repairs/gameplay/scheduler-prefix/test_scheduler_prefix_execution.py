# SPDX-License-Identifier: Apache-2.0
"""Execute real current-main methods; mechanics spies isolate prefix contracts.

This is not a full simulator, package-import check or competitive strength gate.
The original scheduler is immutable evidence. Tests generate the repaired bytes
with the pinned transformer, then compile actual AST methods without loading the
large Arlene dependency graph. Run with both normal Python and python -O.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import itertools
from pathlib import Path
import tempfile
import os
import sys
from unittest import mock
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prefix_port", HERE / "materialize_scheduler_prefix.py")
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)
PARENT = (HERE.parents[4] / "scheduler.py").read_bytes()
CANDIDATE = port.transform(PARENT.decode("utf-8")).encode("utf-8")
CAPACITY_ANCHOR = "        f,p=post_units(obs,base,config,shed_capacity=10**6)\n"
POSTIMAGE_BLOB = "1da9934ec45f485a16244bcbc78af26d9109b97e"


class Mechanics:
    LAND_ORDER = ("NE", "SW", "SE")
    LAND_PRICES = (20, 30, 40)
    CROPS = {"CARROT": {"seed": 2}}
    ANIMALS = {"COW": {"cost": 100}}

    def __init__(self):
        self.spawns = []
        self.unit_calls = []
        self.end_drops = []

    @staticmethod
    def _hire_cost(hires, multiplier):
        return (10 + hires) * multiplier

    @staticmethod
    def market_price(item, inventory, params):
        return 3

    def _spawn_hand(self, farm, size):
        self.spawns.append((len(farm["hands"]), size))
        return [0, 0]

    def _apply_unit_action(self, farm, private, actor, action, size, day, turns, capacity):
        self.unit_calls.append((actor, copy.deepcopy(action), capacity))
        if action == ["DROP"]:
            for item, quantity in list(private["inventories"][actor].items()):
                private["shed"][item] = private["shed"].get(item, 0) + quantity
            private["inventories"][actor].clear()

    def _drop_inventories_to_shed(self, private, capacity):
        self.end_drops.append(capacity)
        for inventory in private["inventories"]:
            for item, quantity in inventory.items():
                private["shed"][item] = private["shed"].get(item, 0) + quantity
            inventory.clear()


def action(market=None, farmer=None):
    return {"farmer": farmer or ["PASS"], "hands": [],
            "market": [] if market is None else market}


def fixture(source=CANDIDATE, *, step=0, stock=5, carried=0, route=None):
    mechanics = Mechanics()
    post_calls = []
    obs = {"step": step, "player": 0,
           "farms": [{"unlocked_quadrants": ["NW"], "hires_today": 0,
                      "hands": [], "tiles": [[None]], "money": 100}],
           "private": {"shed": {"WHEAT": stock},
                       "inventories": [{"WHEAT": carried}] if carried else [{}]},
           "market": {"inventory": {"WHEAT": 10}, "params": {}}}

    def post_units(observation, current, config, *, shed_capacity=None):
        post_calls.append(shed_capacity)
        farm = copy.deepcopy(observation["farms"][observation["player"]])
        private = copy.deepcopy(observation["private"])
        return farm, private

    parsed = ast.parse(source.decode())
    selected = [n for n in parsed.body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                and n.name in {"_order_spend", "_engine_market_prefix", "SellScheduler"}]
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    namespace = {"m": mechanics, "copy": copy,
                 "parent": SimpleNamespace(PASS=action()), "post_units": post_units}
    exec(compile(module, "<exact-scheduler-methods>", "exec"), namespace)
    instance = namespace["SellScheduler"].__new__(namespace["SellScheduler"])
    instance.controller = SimpleNamespace(R=[route if route is not None else []], cur=0)
    return SimpleNamespace(agent=instance, obs=obs, mechanics=mechanics,
                           post_calls=post_calls, namespace=namespace)


def cash(fix, base, cap=1, end=None):
    return fix.agent.cash_reserve(fix.obs, {"maxMarketOrdersPerTurn": cap}, base,
                                 fix.obs["step"] if end is None else end)


def receipts(fix, base, *, cap=1, end=None, plan=()):
    config = {"maxMarketOrdersPerTurn": cap, "shedCapacity": 10}
    predicate = fix.agent.receipt_profile(fix.obs, base, {"ignored": True},
                                         {"ignored": True},
                                         fix.obs["step"] if end is None else end,
                                         "CARROT", config)
    return predicate(plan)


class ExactSource(unittest.TestCase):
    def test_parent_and_postimage_blob_identity(self):
        self.assertEqual(port.git_blob_sha(PARENT), port.SOURCE_GIT_BLOB)
        self.assertEqual(port.git_blob_sha(CANDIDATE), POSTIMAGE_BLOB)

    def test_only_two_existing_method_asts_change(self):
        def indexed(source):
            tree = ast.parse(source.decode())
            result = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    for child in node.body:
                        result[node.name + "." + getattr(child, "name", str(child.lineno))] = ast.dump(child)
                else:
                    result[getattr(node, "name", str(node.lineno))] = ast.dump(node)
            return result
        before, after = indexed(PARENT), indexed(CANDIDATE)
        # Line-number keys shift for bottom-level assignments; compare complete
        # top-level AST after removing the helper and replacing the two methods.
        left, right = ast.parse(PARENT), ast.parse(CANDIDATE)
        right.body = [n for n in right.body if getattr(n, "name", None) != "_engine_market_prefix"]
        lc = next(n for n in left.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
        rc = next(n for n in right.body if isinstance(n, ast.ClassDef) and n.name == "SellScheduler")
        targets = {"cash_reserve", "receipt_profile"}
        self.assertEqual({k for k in before if k.startswith("SellScheduler.") and before[k] != after[k]},
                         {"SellScheduler.cash_reserve", "SellScheduler.receipt_profile"})
        rc.body = [next(x for x in lc.body if getattr(x, "name", None) == n.name)
                   if getattr(n, "name", None) in targets else n for n in rc.body]
        self.assertEqual(ast.dump(left), ast.dump(right))

    def test_old_initial_sale_prepass_is_not_resurrected(self):
        self.assertEqual(CANDIDATE.decode().count(CAPACITY_ANCHOR), 1)
        self.assertNotIn("f,p=copy.deepcopy(farm),copy.deepcopy(private)", CANDIDATE.decode())
        self.assertEqual(CANDIDATE.decode().count("_engine_market_prefix("), 3)

    def test_drift_double_apply_and_old_preimage_rejected(self):
        for source in (PARENT + b"\n", CANDIDATE, PARENT.replace(CAPACITY_ANCHOR.encode(), b"")):
            with self.subTest(blob=port.git_blob_sha(source)):
                with self.assertRaises(port.MaterializationError):
                    port.materialize(source, b"not-the-pinned-engine")

    def test_exact_once_guard_rejects_zero_and_two_matches(self):
        for text in ("", "needle needle"):
            with self.assertRaises(port.MaterializationError):
                port._replace_exact(text, "needle", "replacement", "poison")

    def test_transform_double_apply_and_missing_consumers_fail_closed(self):
        for source in (CANDIDATE.decode(),
                       PARENT.decode().replace(port.CALLSITE.format(name="o"), ""),
                       PARENT.decode() + port.CALLSITE.format(name="order")):
            with self.assertRaises(port.MaterializationError):
                port.transform(source)

    def test_existing_self_test_runs(self):
        port.self_test()

    def test_observed_engine_anchor_excerpt_and_ambiguity(self):
        excerpt = "\n".join(port.ENGINE_ANCHORS)
        port.verify_engine(excerpt)
        with self.assertRaises(port.MaterializationError):
            port.verify_engine(excerpt + "\n" + port.ENGINE_ANCHORS[0])


class OutputCustody(unittest.TestCase):
    def invoke(self, root, output):
        source, engine = root / "source.py", root / "engine.py"
        argv = ["materialize_scheduler_prefix.py", str(source), str(output),
                "--engine", str(engine)]
        # The game-source transformation is tested above. This isolated CLI
        # boundary test deliberately replaces only the verified-byte producer.
        with mock.patch.object(port, "materialize", return_value=CANDIDATE), \
             mock.patch.object(sys, "argv", argv):
            return port.main()

    def setup_files(self, root):
        (root / "source.py").write_bytes(PARENT)
        (root / "engine.py").write_bytes(b"engine fixture for isolated I/O test\n")

    def intact(self, root):
        self.assertEqual((root / "source.py").read_bytes(), PARENT)
        self.assertEqual((root / "engine.py").read_bytes(), b"engine fixture for isolated I/O test\n")

    def test_fresh_output_is_byte_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            output = root / "new.py"
            self.assertEqual(self.invoke(root, output), 0)
            self.assertEqual(output.read_bytes(), CANDIDATE)
            self.intact(root)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            output = root / "existing.py"; output.write_bytes(b"keep previous artifact")
            with self.assertRaises(FileExistsError):
                self.invoke(root, output)
            self.assertEqual(output.read_bytes(), b"keep previous artifact")
            self.intact(root)

    def test_engine_path_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            with self.assertRaises(port.MaterializationError):
                self.invoke(root, root / "engine.py")
            self.intact(root)

    def test_source_path_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            with self.assertRaises(port.MaterializationError):
                self.invoke(root, root / "source.py")
            self.intact(root)

    def test_hardlink_to_bound_engine_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            output = root / "engine-link.py"; os.link(root / "engine.py", output)
            with self.assertRaises(FileExistsError):
                self.invoke(root, output)
            self.intact(root)

    def test_symlink_to_bound_engine_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.setup_files(root)
            output = root / "engine-link.py"; output.symlink_to(root / "engine.py")
            with self.assertRaises(port.MaterializationError):
                self.invoke(root, output)
            self.intact(root)


class Prefix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Staticmethod prevents the old donor's accidental self binding.
        cls.prefix = staticmethod(fixture().namespace["_engine_market_prefix"])

    def test_1512_raw_slot_and_cap_combinations(self):
        rows = ([], None, False, ["HIRE"], ["SELL", "CARROT", 2], ("HIRE",))
        cases = 0
        for layout in itertools.product(rows, repeat=3):
            for cap in (-5, -1, 0, 1, 2, 3, 9):
                self.assertEqual(self.prefix({"market": list(layout)}, {"maxMarketOrdersPerTurn": cap}),
                                 list(layout)[:max(1, cap)])
                cases += 1
        self.assertEqual(cases, 1512)

    def test_default_cap_really_has_eleven_rows(self):
        current = {"market": [["SELL", "CARROT", 1] for _ in range(11)]}
        self.assertEqual(len(current["market"]), 11)
        self.assertEqual(len(self.prefix(current, {})), 10)

    def test_non_list_market_normalizes_empty(self):
        for raw in (None, {}, "HIRE", (["HIRE"],), 42):
            self.assertEqual(self.prefix({"market": raw}, {}), [])
        self.assertEqual(self.prefix(object(), {}), [])

    def test_empty_and_invalid_raw_rows_still_occupy_slots(self):
        current = {"market": [None, [], ["HIRE"]]}
        self.assertEqual(self.prefix(current, {"maxMarketOrdersPerTurn": 2}), [None, []])

    def test_cap_coercion_and_minimum_match_engine(self):
        current = {"market": [["HIRE"] for _ in range(4)]}
        for cap in ("2", 2.7, 0, -1, True, False):
            self.assertEqual(len(self.prefix(current, {"maxMarketOrdersPerTurn": cap})), max(1, int(cap)))

    def test_prefix_does_not_mutate_parent_queue(self):
        current = action([[], ["HIRE"]])
        old = copy.deepcopy(current)
        result = self.prefix(current, {"maxMarketOrdersPerTurn": 1})
        result.append(["BUY_LAND"])
        self.assertEqual(current, old)


class CashReserve(unittest.TestCase):
    def test_capped_current_hire_cannot_reserve_cash(self):
        base = action([[], ["HIRE"]])
        self.assertEqual(cash(fixture(), base), 0)
        self.assertEqual(cash(fixture(PARENT), base), 10)

    def test_capped_future_hire_cannot_reserve_cash(self):
        route = [action(), action([[], ["HIRE"]])]
        self.assertEqual(cash(fixture(route=route), action(), end=1), 0)
        self.assertEqual(cash(fixture(PARENT, route=route), action(), end=1), 10)

    def test_valid_prefix_spend_still_counts(self):
        base = action([["HIRE"], ["BUY_SEED", "CARROT", 3]])
        self.assertEqual(cash(fixture(), base, cap=2), 16)

    def test_zero_and_negative_caps_still_execute_first_slot(self):
        for cap in (-3, 0):
            self.assertEqual(cash(fixture(), action([["HIRE"], ["HIRE"]]), cap=cap), 10)

    def test_slot_eleven_poison_never_reaches_spend_parser(self):
        fix = fixture()
        original = fix.namespace["_order_spend"]
        def reject(order, *args):
            if order == ["POISON"]:
                raise AssertionError("inert suffix reached parser")
            return original(order, *args)
        fix.namespace["_order_spend"] = reject
        self.assertEqual(cash(fix, action([[] for _ in range(10)] + [["POISON"]]), cap=10), 0)

    def test_capped_land_does_not_change_future_price(self):
        route = [action(), action([["BUY_LAND"]])]
        base = action([[], ["BUY_LAND"]])
        self.assertEqual(cash(fixture(route=route), base, end=1), 20)
        self.assertEqual(cash(fixture(PARENT, route=route), base, end=1), 50)

    def test_day_boundary_hire_reset_preserved(self):
        route = [action() for _ in range(25)]
        route[24] = action([["HIRE"]])
        self.assertEqual(cash(fixture(step=23, route=route), action([["HIRE"]]), end=24), 20)

    def test_missing_future_route_is_pass(self):
        self.assertEqual(cash(fixture(route=[]), action([["HIRE"]]), end=2), 10)

    def test_cash_inputs_are_not_mutated(self):
        fix = fixture(route=[action(), action([["BUY_LAND"]])])
        base = action([[], ["BUY_LAND"]])
        snapshot = copy.deepcopy((fix.obs, base, fix.agent.controller.R))
        cash(fix, base, end=1)
        self.assertEqual((fix.obs, base, fix.agent.controller.R), snapshot)


class ReceiptProfile(unittest.TestCase):
    def test_inert_current_sell_cannot_manufacture_future_room(self):
        route = [action(), action(farmer=["DROP"])]
        base = action([[], ["SELL", "WHEAT", 3]])
        self.assertFalse(receipts(fixture(stock=9, carried=1, route=route), base, end=1))
        self.assertTrue(receipts(fixture(PARENT, stock=9, carried=1, route=route), base, end=1))

    def test_current_prefix_sale_can_release_future_room(self):
        route = [action(), action(farmer=["DROP"])]
        self.assertTrue(receipts(fixture(stock=9, carried=1, route=route),
                                 action([["SELL", "WHEAT", 3]]), end=1))

    def test_inert_current_buy_cannot_create_false_capacity_failure(self):
        base = action([[], ["BUY_PRODUCT", "WHEAT", 5]])
        self.assertTrue(receipts(fixture(), base))
        self.assertFalse(receipts(fixture(PARENT), base))

    def test_inert_future_buy_cannot_create_false_capacity_failure(self):
        route = [action(), action([[], ["BUY_PRODUCT", "WHEAT", 5]])]
        self.assertTrue(receipts(fixture(route=route), action(), end=1))
        self.assertFalse(receipts(fixture(PARENT, route=route), action(), end=1))

    def test_real_prefix_buy_still_occupies_space(self):
        self.assertFalse(receipts(fixture(), action([["BUY_PRODUCT", "WHEAT", 5]])))

    def test_inert_hire_does_not_spawn_projection_hand(self):
        fix = fixture()
        self.assertTrue(receipts(fix, action([[], ["HIRE"]])))
        self.assertEqual(fix.mechanics.spawns, [])
        old = fixture(PARENT)
        receipts(old, action([[], ["HIRE"]]))
        self.assertEqual(len(old.mechanics.spawns), 1)

    def test_valid_hire_is_not_removed(self):
        fix = fixture()
        receipts(fix, action([["HIRE"]]))
        self.assertEqual(len(fix.mechanics.spawns), 1)

    def test_current_unit_overflow_cannot_be_rescued_by_same_turn_sale(self):
        fix = fixture(stock=11)
        self.assertFalse(receipts(fix, action([["SELL", "WHEAT", 9]]), plan=((0, 9),)))
        self.assertEqual(fix.post_calls, [10**6])

    def test_end_of_day_deposit_cannot_use_inert_sale(self):
        base = action([[], ["SELL", "WHEAT", 2]])
        fix = fixture(step=23, stock=9, carried=1)
        self.assertFalse(receipts(fix, base))
        self.assertEqual(fix.mechanics.end_drops, [10**6])
        self.assertTrue(receipts(fixture(PARENT, step=23, stock=9, carried=1), base))

    def test_projection_inputs_not_mutated_and_uncapped_stage_retained(self):
        route = [action(), action(farmer=["DROP"])]
        fix = fixture(stock=5, carried=1, route=route)
        base = action([["SELL", "WHEAT", 1]])
        snapshot = copy.deepcopy((fix.obs, base, fix.agent.controller.R))
        self.assertTrue(receipts(fix, base, end=1))
        self.assertEqual((fix.obs, base, fix.agent.controller.R), snapshot)
        self.assertEqual(fix.post_calls, [10**6])
        self.assertTrue(all(row[2] == 10**6 for row in fix.mechanics.unit_calls))

    def test_144_below_cap_receipt_cases_preserve_predecessor(self):
        count = 0
        orders = ([], ["SELL", "WHEAT", 2], ["BUY_PRODUCT", "WHEAT", 2], ["HIRE"])
        for stock in (0, 5, 9):
            for first, second in itertools.product(orders, repeat=2):
                for cap in (2, 3, 10):
                    base = action([first, second])
                    self.assertEqual(receipts(fixture(stock=stock), base, cap=cap),
                                     receipts(fixture(PARENT, stock=stock), base, cap=cap))
                    count += 1
        self.assertEqual(count, 144)


if __name__ == "__main__":
    unittest.main(verbosity=2)
