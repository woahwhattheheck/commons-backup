# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
sys.path.insert(0, str(LAB)) if str(LAB) not in sys.path else None

import frozen_selected as frozen
from route_reference_echo import RouteEchoGuardedFrozenSelected, normalize_future_plan

ITEM = "CARROT"


def route(step=12, quantity=2):
    value = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(24)]
    value[step]["market"] = [["SELL", ITEM, quantity]]
    return value


class Controller:
    def __init__(self, value):
        self.cur, self.R = 0, [value]


def consumer(cls, value):
    obj = cls.__new__(cls)
    obj.controller = Controller(value)
    obj.mode, obj.pending, obj.planned = "candidate", {}, {}
    obj.previous, obj.observed_harvests, obj.diagnostics = None, {}, {}
    obj.joint_producer_busy = True
    obj.observe = lambda _obs: None
    obj.cash_reserve = lambda *_a, **_k: 0
    obj.receipt_profile = lambda *_a, **_k: (lambda _plan: True)
    obj.rival_supply = lambda *_a, **_k: 0
    return obj


def observation(step):
    return {
        "step": step, "player": 0,
        "farms": [{"tiles": []}, {"tiles": []}], "private": {},
        "town": {"unlocked_shops": []},
        "market": {"inventory": {ITEM: 100}, "params": None, "prices": {}},
    }


def base_action():
    return {"farmer": ["PASS"], "hands": [], "market": [["SELL", ITEM, 1]]}


def post_state():
    farm = {"money": 1000, "hires_today": 0, "unlocked_quadrants": ["NW"], "hands": [], "tiles": []}
    private = {"shed": {ITEM: 5}, "seeds": {}, "inventories": []}
    return farm, private


class NormalizeTests(unittest.TestCase):
    def test_route_floor_is_removed_but_scheduler_excess_survives(self):
        value = route(quantity=2)
        value[12]["market"].append(["SELL", ITEM, 1])
        normalized, report = normalize_future_plan([(10, 1), (12, 5), (13, 4)], value, ITEM, 10, end=13)
        self.assertEqual(normalized, [(12, 2), (13, 4)])
        self.assertEqual((report["removed_quantity"], report["scheduler_owned_quantity"]), (3, 6))

    def test_malformed_and_unrepresentable_inputs_fail_closed(self):
        malformed = route()
        malformed[12]["market"] = [["SELL", ITEM, True]]
        normalized, report = normalize_future_plan([(12, 3)], malformed, ITEM, 10, end=12)
        self.assertIsNone(normalized)
        self.assertEqual(report["status"], "INVALID")
        normalized, report = normalize_future_plan([(13, 2)], route(), ITEM, 10, end=13)
        self.assertIsNone(normalized)
        self.assertEqual((report["status"], report["deficits"]), ("UNREPRESENTABLE_ROUTE_FLOOR", [[12, 2]]))

    def test_duplicate_selected_rows_consume_floor_without_unrelated_reordering(self):
        normalized, report = normalize_future_plan([(12, 1), (12, 4)], route(), ITEM, 10, end=12)
        self.assertEqual(normalized, [(12, 3)])
        self.assertEqual(report["canonical_quantity"], 5)

    def test_no_route_echo_preserves_duplicate_row_shape_and_order(self):
        value = route()
        value[12]["market"] = []
        selected = [(12, 1), (13, 4), (12, 2)]
        normalized, report = normalize_future_plan(selected, value, ITEM, 10, end=13)
        self.assertEqual(normalized, selected)
        self.assertFalse(report["changed"])
        self.assertEqual(report["canonical_future"], [[12, 1], [13, 4], [12, 2]])


class TransformTests(unittest.TestCase):
    def exercise(self, cls):
        value, refs = consumer(cls, route()), []

        def optimize(**kw):
            reference = tuple(kw["reference"])
            refs.append(reference)
            return reference, {
                "item": kw["item"], "quantity": kw["quantity"],
                "plan": list(reference), "reference": list(reference), "horizon_end": 12,
                "worst_relative_gain": 1.0, "forced_feasibility": False,
                "accepted": True, "acceptance_score": 1.0,
                "scenarios": {"w": {"reference_relative_value": 0.0, "relative_value": 1.0}},
            }

        horizon = {"baseline_end": 12, "hard_end": 12, "service_dates": {ITEM: 12},
                   "unit_event": None, "extended": False}
        public = lambda obs: {"step": int(obs["step"]), "player": int(obs["player"]),
                              "farms": [{"tiles": []}, {"tiles": []}]}
        with patch.object(frozen, "post_units", side_effect=lambda *_a: deepcopy(post_state())), \
             patch.object(frozen, "event_aware_horizon", return_value=(12, deepcopy(horizon))), \
             patch.object(frozen, "represented_shed_event", return_value=None), \
             patch.object(frozen, "product_event_dates", side_effect=lambda _i, now, end, _s, _c: [now, end]), \
             patch.object(frozen, "funded_minimum_now", return_value=(0, {"accepted": True})), \
             patch.object(frozen, "optimize_lot", side_effect=optimize), \
             patch.object(frozen, "seller_public_observation", side_effect=public), \
             patch.object(frozen, "fund_same_turn_acquisition", side_effect=lambda orders, *_a, **_k: (orders, None)):
            first = value.transform(observation(10), {}, base_action())
            first_plan = deepcopy(value.planned)
            first_receipt = deepcopy(value.diagnostics.get("route_reference_echo"))
            value.transform(observation(11), {}, base_action())
        return first, first_plan, first_receipt, refs

    def test_exact_predecessor_echo_and_guard(self):
        old = self.exercise(frozen.FrozenSelected)
        new = self.exercise(RouteEchoGuardedFrozenSelected)
        self.assertEqual(old[3], [((10, 1), (12, 2)), ((11, 1), (12, 4))])
        self.assertEqual(old[1], {ITEM: [(12, 2)]})
        self.assertEqual(new[0], old[0])
        self.assertEqual(new[1], {})
        self.assertEqual(new[3], [((10, 1), (12, 2)), ((11, 1), (12, 2))])
        self.assertEqual((new[2]["changed"], new[2]["removed_quantity"]), (True, 2))


class CarrierTests(unittest.TestCase):
    def test_private_canonical_carrier_preserves_final_pressure_and_controller(self):
        import candidate
        features = json.loads((LAB / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        instance = candidate._new_instance(LAB, features)
        self.assertEqual([c.__name__ for c in type(instance).__mro__[:2]],
                         ["RouteEchoFinalPressureAgent", "FinalPressureAgent"])
        instance._initialize()
        self.assertIsInstance(instance.consumer, RouteEchoGuardedFrozenSelected)
        self.assertIs(instance.consumer.controller, instance.controller)
        self.assertIs(frozen.FrozenSelected, candidate.canonical_frozen_selected.FrozenSelected)
        self.assertIsNot(candidate._CANONICAL_MAIN, sys.modules.get("main"))


if __name__ == "__main__":
    unittest.main()
