# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
PATCH = HERE / "executable_sell_custody.py"


def load_patch():
    spec = importlib.util.spec_from_file_location("_sell_custody_under_test", PATCH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


P = load_patch()


class FakeController:
    def __init__(self, route, *, mapping=False, route_id="7015cc00acfa4922"):
        if mapping:
            self.R = {route_id: route}
            self.cur = route_id
        else:
            self.R = [route]
            self.cur = 0
        self.tag = "preserved"


class FakeFrozen:
    def __init__(self, route, *, mapping=False, route_id="7015cc00acfa4922"):
        self.controller = FakeController(route, mapping=mapping, route_id=route_id)
        self.pending = {}
        self.planned = {}
        self.diagnostics = {}
        self.seen = None
        self.received_config = None

    def cash_reserve(self, *_args, **_kwargs):
        return 0

    def transform(self, obs, config, selected):
        # Deliberately model the exact predecessor defect: every represented
        # SELL row, even an engine-inactive suffix, retires pending stock.
        self.received_config = copy.deepcopy(config)
        if isinstance(self.controller.R, dict):
            cur = self.controller.cur
            route_markets = [copy.deepcopy(a["market"]) for a in self.controller.R[cur]]
        else:
            route_markets = [copy.deepcopy(a["market"]) for a in self.controller.R[0]]
        own_market = copy.deepcopy(selected["market"])
        sold = sum(
            max(0, int(row[2]))
            for row in own_market
            if row and len(row) > 2 and row[0] == "SELL" and row[1] == "CARROT"
        )
        self.pending["CARROT"] = max(0, 3 - sold)
        self.seen = {"selected": own_market, "route": route_markets}
        self.diagnostics = {"predecessor": True}
        return copy.deepcopy(selected)


def installed_class(route, *, frozen_blob=None, scheduler_blob=None, mapping=False):
    module = SimpleNamespace(FrozenSelected=FakeFrozen, __file__=__file__)
    blob = P.git_blob_sha1(__file__)
    P.install(
        module,
        expected_frozen_blob=frozen_blob or blob,
        expected_scheduler_blob=scheduler_blob or blob,
    )
    agent = module.FrozenSelected(route, mapping=mapping)
    return agent, module


class SellCustodyTests(unittest.TestCase):
    def test_exact_suffix_counterexample_is_not_admitted_or_retired(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["SELL", "CARROT", 3]],
        }
        route = [copy.deepcopy(action), copy.deepcopy(action)]
        agent, _ = installed_class(route)
        original = copy.deepcopy(action)
        controller = agent.controller

        out = agent.transform({"step": 0}, {"maxMarketOrdersPerTurn": 1}, action)

        self.assertEqual(agent.seen["selected"], [[]])
        self.assertEqual(agent.pending["CARROT"], 3)
        self.assertEqual(out, original)
        self.assertEqual(action, original)
        self.assertIs(agent.controller, controller)
        self.assertEqual(
            agent.diagnostics["executable_sell_custody"]["inert_suffix_rows"], 1
        )

    def test_active_prefix_sale_still_retires_stock(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "CARROT", 3], []],
        }
        agent, _ = installed_class([copy.deepcopy(action)])
        out = agent.transform({}, {"maxMarketOrdersPerTurn": 1}, action)
        self.assertEqual(agent.seen["selected"], [["SELL", "CARROT", 3]])
        self.assertEqual(agent.pending["CARROT"], 0)
        self.assertEqual(out, action)

    def test_future_route_suffixes_are_hidden_without_mutation(self):
        route = [
            {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "CARROT", 3]]},
            {"farmer": ["PASS"], "hands": [], "market": [["SELL", "CARROT", 1], ["HIRE"]]},
        ]
        action = copy.deepcopy(route[0])
        route_before = copy.deepcopy(route)
        agent, _ = installed_class(route)
        agent.transform({}, {"maxMarketOrdersPerTurn": 1}, action)
        self.assertEqual(agent.seen["route"], [[[]], [["SELL", "CARROT", 1]]])
        self.assertEqual(agent.controller.R[0], route_before)

    def test_market_limit_is_normalized_to_one(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "CARROT", 3]]}
        agent, _ = installed_class([copy.deepcopy(action)])
        agent.transform({}, {"maxMarketOrdersPerTurn": 0}, action)
        self.assertEqual(agent.seen["selected"], [[]])

    def test_delegated_config_limit_is_normalized_for_zero_and_negative(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "CARROT", 3]]}
        for configured in (0, -3):
            with self.subTest(configured=configured):
                caller_config = {"maxMarketOrdersPerTurn": configured, "other": "keep"}
                agent, _ = installed_class([copy.deepcopy(action)])
                agent.transform({}, caller_config, action)
                self.assertEqual(agent.received_config["maxMarketOrdersPerTurn"], 1)
                self.assertEqual(agent.received_config["other"], "keep")
                self.assertEqual(caller_config["maxMarketOrdersPerTurn"], configured)
                self.assertEqual(agent.seen["selected"], [[]])

    def test_mapping_route_bank_string_cur_is_preserved(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["SELL", "CARROT", 3]],
        }
        route = [copy.deepcopy(action)]
        agent, _ = installed_class(route, mapping=True)
        original_R = agent.controller.R
        original_cur = agent.controller.cur
        out = agent.transform({}, {"maxMarketOrdersPerTurn": 1}, action)
        self.assertEqual(agent.seen["selected"], [[]])
        self.assertEqual(agent.pending["CARROT"], 3)
        self.assertIs(agent.controller.R, original_R)
        self.assertEqual(agent.controller.cur, original_cur)
        self.assertIsInstance(agent.controller.R, dict)
        self.assertEqual(out["market"][1], ["SELL", "CARROT", 3])

    def test_no_suffix_path_is_active_prefix_parity(self):
        action = {"farmer": ["PASS"], "hands": [["WAIT"]], "market": [["SELL", "CARROT", 2]]}
        agent, _ = installed_class([copy.deepcopy(action)])
        out = agent.transform({}, {"maxMarketOrdersPerTurn": 10}, action)
        self.assertEqual(agent.seen["selected"], action["market"])
        self.assertEqual(out, action)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["WAIT"]])

    def test_original_suffix_objects_are_not_aliased(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "CARROT", 3]]}
        agent, _ = installed_class([copy.deepcopy(action)])
        out = agent.transform({}, {"maxMarketOrdersPerTurn": 1}, action)
        out["market"][1][2] = 99
        self.assertEqual(action["market"][1][2], 3)

    def test_exception_restores_original_controller(self):
        class Exploding(FakeFrozen):
            def transform(self, *_args):
                raise ValueError("boom")

        module = SimpleNamespace(FrozenSelected=Exploding, __file__=__file__)
        blob = P.git_blob_sha1(__file__)
        P.install(module, expected_frozen_blob=blob, expected_scheduler_blob=blob)
        agent = module.FrozenSelected(
            [{"farmer": ["PASS"], "hands": [], "market": [[]]}]
        )
        controller = agent.controller
        with self.assertRaisesRegex(ValueError, "boom"):
            agent.transform({}, {"maxMarketOrdersPerTurn": 1}, {
                "farmer": ["PASS"], "hands": [], "market": [[]]
            })
        self.assertIs(agent.controller, controller)

    def test_install_is_idempotent_for_identical_sources(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [[]]}
        agent, module = installed_class([copy.deepcopy(action)])
        blob = P.git_blob_sha1(__file__)
        receipt = P.install(
            module, expected_frozen_blob=blob, expected_scheduler_blob=blob
        )
        self.assertFalse(receipt["installed"])
        self.assertTrue(receipt["idempotent"])
        self.assertIs(module.FrozenSelected, type(agent))

    def test_source_drift_fails_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": [[]]}
        with self.assertRaisesRegex(RuntimeError, "frozen_selected source drift"):
            installed_class(
                [copy.deepcopy(action)],
                frozen_blob="0" * 40,
                scheduler_blob=P.git_blob_sha1(__file__),
            )

    def test_invalid_market_shape_fails_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": "not-a-list"}
        agent, _ = installed_class(
            [{"farmer": ["PASS"], "hands": [], "market": [[]]}]
        )
        with self.assertRaisesRegex(RuntimeError, "market queue must be a list"):
            agent.transform({}, {}, action)

    def test_reattach_rejects_prefix_cardinality_drift(self):
        original = {"market": [[], ["SELL", "CARROT", 3]]}
        transformed = {"market": []}
        with self.assertRaisesRegex(RuntimeError, "prefix cardinality"):
            P.reattach_inert_suffix(original, transformed, 1)

    def test_current_repository_sources_remain_exactly_pinned(self):
        lab = HERE.parents[1]
        frozen = lab / "frozen_selected.py"
        scheduler = lab / "scheduler.py"
        if frozen.is_file() and scheduler.is_file():
            self.assertEqual(
                P.git_blob_sha1(frozen), P.EXPECTED_FROZEN_SELECTED_GIT_BLOB
            )
            self.assertEqual(
                P.git_blob_sha1(scheduler), P.EXPECTED_SCHEDULER_GIT_BLOB
            )


if __name__ == "__main__":
    unittest.main()
