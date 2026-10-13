#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import compose_current_native as current


HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1]
LAB = V4.parent.parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def function_from(source: str, name: str, namespace=None):
    start, end = current._span(source, name)
    ns = {} if namespace is None else dict(namespace)
    exec(compile(source[start:end], f"<{name}>", "exec"), ns)
    return ns[name]


def quantities(orders):
    result = {}
    for order in orders:
        if order and len(order) > 2 and order[0] == "SELL":
            result[order[1]] = result.get(order[1], 0) + max(0, int(order[2]))
    return result


class CurrentPrefixCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_scheduler_b = (LAB / "scheduler.py").read_bytes()
        cls.raw_frozen_b = (LAB / "frozen_selected.py").read_bytes()
        cls.raw_scheduler = cls.raw_scheduler_b.decode()
        cls.raw_frozen = cls.raw_frozen_b.decode()
        if current.git_blob(cls.raw_scheduler_b) != current.LEGACY_SCHEDULER_INPUT:
            raise AssertionError("raw scheduler predecessor drift")
        if current.git_blob(cls.raw_frozen_b) != "fc7baf5c179818a55037f6a61d92984d81d1a21c":
            raise AssertionError("raw frozen predecessor drift")

        town = load("prefix_town", V4 / "repairs/performance/funding-replay/apply_town_funding.py")
        unit = load("prefix_unit", V4 / "repairs/runtime/joint-unit-projection/compose.py")
        funding = load("prefix_funding", V4 / "repairs/performance/funding-replay/apply_funding_replay.py")
        cap = load("prefix_cap", V4 / "repairs/performance/funding-replay/compose_funding_capacity.py")
        spindle = load("prefix_spindle", V4 / "repairs/performance/compose_scoped_constructor.py")
        live = load("prefix_live", V4 / "repairs/performance/projection-state-clone/compose.py")
        h3 = load("prefix_h3", V4 / "research/sale-window-engagement/compose_current_h3s420.py")

        scheduler = cls.raw_scheduler
        frozen = town.apply(cls.raw_frozen)
        scheduler, frozen = unit.compose_sources(scheduler, frozen)
        frozen = funding.apply(frozen)
        frozen = cap.apply(frozen)
        if current.git_blob(scheduler.encode()) != "eb289f87adebb7dc7e90046bfbec31a307cb5aaa":
            raise AssertionError("UNITFLOW scheduler postimage drift")
        if current.git_blob(frozen.encode()) != "ef090f6731c2d1ee648e2caaf3e215641b006518":
            raise AssertionError("CAPTRACE frozen postimage drift")

        helper = (LAB.parent / "cloud-quickstep/scoped_method_cache.py").read_bytes()
        scheduler_b, _receipt = spindle.compose(scheduler.encode(), helper)
        if current.git_blob(scheduler_b) != "b29d1e9887f517506c5b3d858baa9bda5848e73f":
            raise AssertionError("SPINDLE scheduler postimage drift")
        early = (LAB / "early_capital.py").read_text()
        frozen, _early = live.compose_sources(frozen, early)
        if current.git_blob(frozen.encode()) != "4a5d3d5f4bed04acf73c7339e41fed56badf34c9":
            raise AssertionError("LIVEPATH frozen postimage drift")

        h3_b = h3.compose(frozen.encode(), enabled=True)
        if current.git_blob(h3_b) != "712f7334288951bdc5b8dd2a1aa1d7f985cd50dc":
            raise AssertionError("H3S420 frozen postimage drift")
        cls.loom_scheduler_b = scheduler_b
        cls.loom_frozen_b = frozen.encode()
        cls.h3_frozen_b = h3_b

    def test_legacy_scheduler_repair_is_byte_exact(self):
        legacy = load("prefix_legacy", HERE / "scheduler_action_prefix.py")
        expected = legacy.transform(self.raw_scheduler_b)
        actual = current._rewrite_scheduler(self.raw_scheduler).encode()
        self.assertEqual(actual, expected)
        self.assertEqual(current.git_blob(actual), current.LEGACY_SCHEDULER_OUTPUT)

    def test_materialize_preserves_nonexecuted_suffix(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        old_fn = function_from(self.raw_frozen, "materialize_sales")
        new_fn = function_from(patched, "materialize_sales")
        orders = [[], ["SELL", "MILK", 4]]
        args = (orders, {"MILK": 0}, {"MILK": 4}, {"MILK"}, 1)
        self.assertEqual(old_fn(*args), [[], []])
        self.assertEqual(new_fn(*args), orders)

    def test_same_turn_funding_ignores_nonexecuted_suffix_target_and_source(self):
        patched = current._rewrite_frozen(self.raw_frozen)

        def prefix_state(orders, _farm, _private, _market, _shops, _config, _now,
                         _rival_quantity, stop):
            outcomes = {}
            money = 0
            for index, order in enumerate(orders[:max(0, int(stop) + 1)]):
                if order != ["HIRE"]:
                    continue
                funded = any(
                    row and len(row) > 2 and row[:2] == ["SELL", "WOOL"]
                    and int(row[2]) > 0
                    for row in orders[:index]
                )
                outcomes[index] = {
                    "required": 1,
                    "completed": int(funded),
                    "cost_per_unit": 10,
                }
                if funded:
                    money = 190
            return {
                "money": money,
                "outcomes": outcomes,
                "unsupported_index": None,
                "sale_stress": [],
            }

        namespace = {
            "copy": copy,
            "_market_prefix_state": prefix_state,
            "sale_quantities": quantities,
        }
        old_fn = function_from(
            self.raw_frozen, "fund_same_turn_acquisition", namespace)
        new_fn = function_from(
            patched, "fund_same_turn_acquisition", namespace)
        farm = {"money": 0}
        private = {"shed": {"WOOL": 1}}
        market = {"inventory": {"WOOL": 10000}}
        config = {"maxMarketOrdersPerTurn": 10}
        targets = {"WOOL": 1}

        # An inert target must not cause an executable sale to be pulled forward.
        tail_target = [[] for _ in range(10)] + [
            ["HIRE"], ["SELL", "WOOL", 1]
        ]
        old_target, old_target_info = old_fn(
            tail_target, farm, private, market, [], config, 0, targets,
            lambda _product: 0)
        new_target, new_target_info = new_fn(
            tail_target, farm, private, market, [], config, 0, targets,
            lambda _product: 0)
        self.assertEqual(old_target_info["target_index"], 10)
        self.assertEqual(old_target[9], ["SELL", "WOOL", 1])
        self.assertEqual(new_target, tail_target)
        self.assertIsNone(new_target_info)

        # An executable target likewise cannot be funded by a suffix-only sale.
        tail_source = [[] for _ in range(9)] + [
            ["HIRE"], ["SELL", "WOOL", 1]
        ]
        old_source, old_source_info = old_fn(
            tail_source, farm, private, market, [], config, 0, targets,
            lambda _product: 0)
        new_source, new_source_info = new_fn(
            tail_source, farm, private, market, [], config, 0, targets,
            lambda _product: 0)
        self.assertEqual(old_source_info["source_index"], 10)
        self.assertEqual(old_source[8], ["SELL", "WOOL", 1])
        self.assertEqual(new_source, tail_source)
        self.assertEqual(new_source_info["reason"], "no-safe-prefix-sale")

    def test_represented_market_ignores_nonexecuted_suffix(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        old_fn = function_from(self.raw_frozen, "apply_represented_market")
        new_fn = function_from(patched, "apply_represented_market")
        farm = {"hands": []}
        old_private = {"shed": {"MILK": 4}}
        new_private = {"shed": {"MILK": 4}}
        orders = [[], ["SELL", "MILK", 4]]
        old_fn(farm, old_private, orders, 10)
        new_fn(farm, new_private, orders, 10, 1)
        self.assertEqual(old_private["shed"]["MILK"], 0)
        self.assertEqual(new_private["shed"]["MILK"], 4)

    def test_represented_market_matches_engine_list_only_normalization(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        new_fn = function_from(patched, "apply_represented_market")
        private = {"shed": {"MILK": 4}}
        # The official interpreter treats tuple/non-list market values as [].
        new_fn({"hands": []}, private, (["SELL", "MILK", 4],), 10, 1)
        self.assertEqual(private["shed"]["MILK"], 4)

    def test_joint_queue_does_not_reject_preserved_raw_suffix_length(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        materialize = function_from(patched, "materialize_sales")
        ns = {
            "PRODUCTS": {"MILK"},
            "sale_quantities": quantities,
            "materialize_sales": materialize,
            "shared_slot_ledger": lambda plans, orders_at, cap: {
                "plans": plans, "cap": cap
            },
        }
        old_fn = function_from(self.raw_frozen, "joint_queue_ledger", ns)
        new_fn = function_from(patched, "joint_queue_ledger", ns)
        orders_at = lambda _t: [[], ["SELL", "MILK", 1]]
        args = (
            {"MILK": [(0, 0)]}, {"MILK": 0}, {}, {"MILK": 1},
            {"stock_upper": {"MILK": 1}}, orders_at, 0, 0, 1,
        )
        self.assertIsNone(old_fn(*args))
        self.assertIsNotNone(new_fn(*args))

    def test_horizon_does_not_treat_suffix_sell_as_executable_slot(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        ns = {
            "parent": SimpleNamespace(DECISIONS=[]),
            "absorption": lambda *args, **kwargs: True,
            "HORIZON": 1,
        }
        old_fn = function_from(self.raw_frozen, "event_aware_horizon", ns)
        new_fn = function_from(patched, "event_aware_horizon", ns)
        route = [{"market": []} for _ in range(6)]
        for step in range(2, 6):
            route[step] = {"market": [["HIRE"], ["SELL", "MILK", 1]]}
        args = (0, 5, route, {"MILK": 1}, [], {"maxMarketOrdersPerTurn": 1})
        old_end, old_report = old_fn(*args)
        new_end, new_report = new_fn(*args)
        self.assertEqual(old_report["service_dates"]["MILK"], 2)
        self.assertEqual(old_end, 2)
        self.assertEqual(new_report["service_dates"], {})
        self.assertEqual(new_end, 1)

    def test_current_loom_and_h3_preimages_compose(self):
        so, fo, loom = current.compose_pair(self.loom_scheduler_b, self.loom_frozen_b)
        so_h3, fo_h3, h3 = current.compose_pair(self.loom_scheduler_b, self.h3_frozen_b)
        self.assertEqual(so, so_h3)
        self.assertNotEqual(fo, fo_h3)
        compile(so, "<scheduler-prefix-output>", "exec")
        compile(fo, "<frozen-prefix-output>", "exec")
        compile(fo_h3, "<frozen-prefix-h3-output>", "exec")
        self.assertEqual(loom["scheduler"]["profile"], "loom4-spindle")
        self.assertEqual(loom["frozen_selected"]["profile"], "loom4-livepath")
        self.assertEqual(h3["frozen_selected"]["profile"], "loom4-livepath+h3s420")
        print("PREFIX_RECEIPT_LOOM=" + json.dumps(loom, sort_keys=True))
        print("PREFIX_RECEIPT_H3=" + json.dumps(h3, sort_keys=True))

    def test_raw_foundation_is_not_a_current_composition_input(self):
        with self.assertRaises(ValueError):
            current.compose_pair(self.raw_scheduler_b, self.raw_frozen_b)

    def test_partial_reapplication_refuses(self):
        patched = current._rewrite_frozen(self.raw_frozen)
        with self.assertRaises(ValueError):
            current._rewrite_frozen(patched)


if __name__ == "__main__":
    unittest.main()
