# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from growth_patch import attach, build_frozen_selected


def canonical_materialize_sales(orders, current, shed, targets, max_orders):
    market = []
    remaining = dict(current)
    available = dict(shed)
    for raw in orders:
        o = list(raw)
        if o and o[0] == "SELL" and len(o) > 2 and o[1] in targets:
            item = o[1]
            q = min(
                max(0, int(o[2])),
                remaining.get(item, 0),
                max(0, available.get(item, 0)),
            )
            remaining[item] = remaining.get(item, 0) - q
            available[item] = available.get(item, 0) - q
            market.append(["SELL", item, q] if q else [])
        else:
            market.append(o)
    for item in sorted(targets):
        q = min(remaining.get(item, 0), max(0, available.get(item, 0)))
        if q > 0 and len(market) < int(max_orders):
            market.append(["SELL", item, q])
            available[item] = available.get(item, 0) - q
    return market


def canonical_optimize_lot(*, item, quantity, now, reference, capacity_ok, **_kwargs):
    candidate = ((now, quantity),)
    accepted = bool(capacity_ok(candidate))
    return (candidate if accepted else tuple(reference)), {"accepted": accepted}


# These global names are deliberately resolved by BaseFrozen.transform.  The
# candidate must leave them unchanged and give only its cloned code private
# replacements.
materialize_sales = canonical_materialize_sales
optimize_lot = canonical_optimize_lot


class BaseFrozen:
    def __init__(self):
        self.diagnostics = {}

    def transform(self, obs, config, base):
        now = int(obs.get("step", 0))
        item = str(obs.get("item", "CARROT"))
        quantity = int(obs.get("quantity", 5))
        route = [base]
        receipt_feasible = lambda plan: bool(obs.get("receipt_feasible", True))

        def feasible(plan):
            for t, q in plan:
                if q <= 0:
                    continue
                orders = base["market"] if t == now else route[t].get("market", []) if t < len(route) else []
                if len(orders) >= int(config.get("maxMarketOrdersPerTurn", 10)):
                    offered = sum(max(0, int(o[2])) for o in orders if o and o[0] == "SELL" and o[1] == item)
                    if q > offered:
                        return False
            return receipt_feasible(plan)

        inherited = sum(
            max(0, int(row[2]))
            for row in base["market"]
            if row and row[0] == "SELL" and row[1] == item
        )
        reference = ((now, inherited),)
        plan, info = optimize_lot(
            item=item,
            quantity=quantity,
            now=now,
            reference=reference,
            capacity_ok=feasible,
        )
        current = {item: dict(plan).get(now, 0)}
        self.diagnostics = {"optimizer": info}
        return {
            "market": materialize_sales(
                base["market"],
                current,
                {item: int(obs.get("shed", quantity))},
                {item: quantity},
                int(config.get("maxMarketOrdersPerTurn", 10)),
            )
        }


def module():
    return SimpleNamespace(
        FrozenSelected=BaseFrozen,
        materialize_sales=canonical_materialize_sales,
        optimize_lot=canonical_optimize_lot,
    )


def sell(item, quantity):
    return ["SELL", item, quantity]


def full_queue(first):
    return [first] + [["BUY_SEED", "WHEAT", 1] for _ in range(9)]


class FullQueueSellGrowthTests(unittest.TestCase):
    def test_predecessor_rejects_but_candidate_resizes_existing_row(self):
        base = {"market": full_queue(sell("CARROT", 1))}
        obs = {"step": 0, "item": "CARROT", "quantity": 5, "shed": 5}
        cfg = {"maxMarketOrdersPerTurn": 10}
        predecessor = BaseFrozen().transform(obs, cfg, copy.deepcopy(base))
        replacement, receipt = build_frozen_selected(module())
        candidate = replacement()
        result = candidate.transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(predecessor["market"][0], sell("CARROT", 1))
        self.assertEqual(result["market"][0], sell("CARROT", 5))
        self.assertEqual(result["market"][1:], base["market"][1:])
        self.assertEqual(len(result["market"]), 10)
        activation = candidate.diagnostics["full_queue_same_product_sell_growth"]
        self.assertEqual(activation["planner_relaxations"], 1)
        self.assertEqual(activation["emitter_expansions"], 1)
        self.assertEqual(activation["extra_units_materialized"], 4)
        self.assertTrue(receipt["canonical_code_object_reused"])

    def test_no_matching_sell_row_remains_rejected(self):
        base = {"market": full_queue(["HIRE"])}
        obs = {"step": 0, "item": "CARROT", "quantity": 5, "shed": 5}
        cfg = {"maxMarketOrdersPerTurn": 10}
        replacement, _ = build_frozen_selected(module())
        candidate = replacement()
        expected = BaseFrozen().transform(obs, cfg, copy.deepcopy(base))
        result = candidate.transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(result, expected)
        self.assertNotIn("full_queue_same_product_sell_growth", candidate.diagnostics)

    def test_below_cap_is_byte_semantically_unchanged(self):
        base = {"market": [sell("CARROT", 1), ["HIRE"]]}
        obs = {"step": 0, "item": "CARROT", "quantity": 5, "shed": 5}
        cfg = {"maxMarketOrdersPerTurn": 10}
        replacement, _ = build_frozen_selected(module())
        expected = BaseFrozen().transform(obs, cfg, copy.deepcopy(base))
        candidate = replacement()
        result = candidate.transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(result, expected)
        self.assertEqual(result["market"], [sell("CARROT", 1), ["HIRE"], sell("CARROT", 4)])
        self.assertNotIn("full_queue_same_product_sell_growth", candidate.diagnostics)

    def test_duplicate_rows_keep_existing_quantities_and_positions(self):
        rows = full_queue(sell("CARROT", 1))
        rows[7] = sell("CARROT", 2)
        rows[4] = ["HIRE"]
        base = {"market": rows}
        obs = {"step": 0, "item": "CARROT", "quantity": 5, "shed": 5}
        cfg = {"maxMarketOrdersPerTurn": 10}
        replacement, _ = build_frozen_selected(module())
        result = replacement().transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(result["market"][0], sell("CARROT", 3))
        self.assertEqual(result["market"][7], sell("CARROT", 2))
        self.assertEqual(result["market"][4], ["HIRE"])
        self.assertEqual(sum(row[2] for row in result["market"] if row and row[0] == "SELL"), 5)

    def test_materializer_never_exceeds_stock(self):
        replacement, _ = build_frozen_selected(module())
        private = replacement._sol_amplifier_private_transform.__globals__["materialize_sales"]
        rows = full_queue(sell("CARROT", 1))
        result = private(rows, {"CARROT": 8}, {"CARROT": 5}, {"CARROT": 8}, 10)
        self.assertEqual(result[0], sell("CARROT", 5))
        self.assertEqual(sum(row[2] for row in result if row and row[0] == "SELL"), 5)

    def test_overlong_queue_is_not_relaxed(self):
        base = {"market": full_queue(sell("CARROT", 1)) + [[]]}
        obs = {"step": 0, "item": "CARROT", "quantity": 5, "shed": 5}
        cfg = {"maxMarketOrdersPerTurn": 10}
        replacement, _ = build_frozen_selected(module())
        candidate = replacement()
        expected = BaseFrozen().transform(obs, cfg, copy.deepcopy(base))
        result = candidate.transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(result, expected)
        self.assertNotIn("full_queue_same_product_sell_growth", candidate.diagnostics)

    def test_receipt_failure_is_never_overturned(self):
        base = {"market": full_queue(sell("CARROT", 1))}
        obs = {
            "step": 0,
            "item": "CARROT",
            "quantity": 5,
            "shed": 5,
            "receipt_feasible": False,
        }
        cfg = {"maxMarketOrdersPerTurn": 10}
        replacement, _ = build_frozen_selected(module())
        candidate = replacement()
        result = candidate.transform(obs, cfg, copy.deepcopy(base))
        self.assertEqual(result["market"][0], sell("CARROT", 1))
        self.assertNotIn("full_queue_same_product_sell_growth", candidate.diagnostics)

    def test_private_globals_do_not_mutate_base_transform_or_module(self):
        fake = module()
        original_code = BaseFrozen.transform.__code__
        original_globals = BaseFrozen.transform.__globals__
        replacement, receipt = build_frozen_selected(fake)
        private = replacement._sol_amplifier_private_transform
        self.assertIs(private.__code__, original_code)
        self.assertIs(BaseFrozen.transform.__globals__, original_globals)
        self.assertIs(fake.FrozenSelected, BaseFrozen)
        self.assertIs(fake.materialize_sales, canonical_materialize_sales)
        self.assertIs(fake.optimize_lot, canonical_optimize_lot)
        self.assertFalse(receipt["global_class_mutation_persistent"])

    def test_attach_uses_private_import_without_mutating_module_binding(self):
        fake = module()

        class Agent:
            def __init__(self):
                self.calls = 0
                self.visible_during_initialize = None

            def _initialize(self):
                from frozen_selected import FrozenSelected

                self.calls += 1
                self.visible_during_initialize = fake.FrozenSelected
                self.consumer = FrozenSelected()

        prior = sys.modules.get("frozen_selected")
        agent = Agent()
        receipt = attach(agent, fake)
        self.assertIs(fake.FrozenSelected, BaseFrozen)
        agent._initialize()
        self.assertIs(fake.FrozenSelected, BaseFrozen)
        self.assertIs(agent.visible_during_initialize, BaseFrozen)
        self.assertIsInstance(agent.consumer, BaseFrozen)
        self.assertIsNot(type(agent.consumer), BaseFrozen)
        self.assertEqual(agent.calls, 1)
        self.assertIs(sys.modules.get("frozen_selected"), prior)
        self.assertTrue(receipt["canonical_initialize_code_object_reused"])
        self.assertFalse(receipt["module_class_binding_mutated"])
        self.assertFalse(receipt["sys_modules_mutated"])
        second = attach(agent, fake)
        self.assertTrue(second["idempotent"])
        self.assertFalse(second["attached"])

    def test_attach_does_not_mutate_module_or_sys_modules_on_exception(self):
        fake = module()

        class Agent:
            def _initialize(self):
                from frozen_selected import FrozenSelected

                _ = FrozenSelected()
                self.visible_during_initialize = fake.FrozenSelected
                raise RuntimeError("boom")

        prior = sys.modules.get("frozen_selected")
        agent = Agent()
        attach(agent, fake)
        with self.assertRaisesRegex(RuntimeError, "boom"):
            agent._initialize()
        self.assertIs(fake.FrozenSelected, BaseFrozen)
        self.assertIs(agent.visible_during_initialize, BaseFrozen)
        self.assertIs(sys.modules.get("frozen_selected"), prior)


LAB = Path(__file__).resolve().parents[2]
SOURCE_AVAILABLE = (LAB / "frozen_selected.py").is_file()


@unittest.skipUnless(SOURCE_AVAILABLE, "requires the complete cloud-execution-lab tree")
class ExactSourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(LAB) not in sys.path:
            sys.path.insert(0, str(LAB))

    def test_source_audit_passes_on_exact_checkout(self):
        import audit_change

        report = audit_change.build_report()
        self.assertEqual(report["decision"], "PASS")
        self.assertTrue(all(report["checks"].values()))

    def test_real_frozen_selected_reuses_transform_code_without_global_mutation(self):
        import frozen_selected

        base = frozen_selected.FrozenSelected
        original_optimizer = frozen_selected.optimize_lot
        original_materializer = frozen_selected.materialize_sales
        replacement, receipt = build_frozen_selected(frozen_selected)
        self.assertIs(
            replacement._sol_amplifier_private_transform.__code__,
            base.transform.__code__,
        )
        self.assertIs(frozen_selected.FrozenSelected, base)
        self.assertIs(frozen_selected.optimize_lot, original_optimizer)
        self.assertIs(frozen_selected.materialize_sales, original_materializer)
        self.assertTrue(receipt["canonical_code_object_reused"])

    def test_candidate_attaches_before_real_lazy_initialization(self):
        import candidate
        import frozen_selected

        config = json.loads((LAB / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        original_class = frozen_selected.FrozenSelected
        instance = candidate._candidate_new_instance(LAB, config)
        receipt = dict(candidate._LAST_INSTALL_RECEIPT or {})
        self.assertTrue(receipt["attached"])
        self.assertTrue(receipt["canonical_initialize_code_object_reused"])
        self.assertFalse(receipt["module_class_binding_mutated"])
        self.assertIs(frozen_selected.FrozenSelected, original_class)
        instance._initialize()
        self.assertIs(frozen_selected.FrozenSelected, original_class)
        self.assertIsInstance(instance.consumer, original_class)
        self.assertIsNot(type(instance.consumer), original_class)


if __name__ == "__main__":
    unittest.main()
