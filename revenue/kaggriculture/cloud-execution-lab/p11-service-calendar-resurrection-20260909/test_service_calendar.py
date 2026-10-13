# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from service_calendar import (
    CalendarInputError,
    CalendarState,
    Obligation,
    admit_bundle,
    admit_payload,
    recurring_obligations,
)


class ServiceCalendarTests(unittest.TestCase):
    def state(self, **overrides):
        value = {
            "current_turn": 10,
            "terminal_turn": 18,
            "cash": 12,
            "inventory": {"seed": 0, "water": 2},
            "room_used": {"plot": 0, "shed": 0},
            "room_capacity": {"plot": 1, "shed": 3},
            "actor_capacity": {"farmer": 1, "system": 2},
            "machine_capacity": {"well": 1},
            "actor_reservations": [],
            "machine_reservations": [],
            "completed": [],
        }
        value.update(overrides)
        return value

    def chain(self):
        return [
            {
                "key": "buy-seed",
                "kind": "purchase",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "buy",
                "actor_demand": {"system": 1},
                "cash_delta": -4,
                "inventory_delta": {"seed": 1},
            },
            {
                "key": "place-seed",
                "kind": "place",
                "earliest_turn": 10,
                "latest_turn": 11,
                "phase": "place",
                "depends_on": ["buy-seed"],
                "actor_demand": {"farmer": 1},
                "inventory_delta": {"seed": -1},
                "room_delta": {"plot": 1},
            },
            {
                "key": "water-crop",
                "kind": "service",
                "earliest_turn": 11,
                "latest_turn": 12,
                "phase": "service",
                "depends_on": ["place-seed"],
                "actor_demand": {"farmer": 1},
                "machine_demand": {"well": 1},
                "inventory_delta": {"water": -1},
            },
            {
                "key": "harvest-crop",
                "kind": "harvest",
                "earliest_turn": 12,
                "latest_turn": 15,
                "phase": "harvest",
                "depends_on": ["water-crop"],
                "actor_demand": {"farmer": 1},
                "inventory_delta": {"wheat": 2},
                "room_delta": {"plot": -1},
            },
            {
                "key": "drop-crop",
                "kind": "drop",
                "earliest_turn": 12,
                "latest_turn": 16,
                "phase": "drop",
                "depends_on": ["harvest-crop"],
                "actor_demand": {"farmer": 1},
                "inventory_delta": {"wheat": -2},
                "room_delta": {"shed": 2},
            },
            {
                "key": "sell-crop",
                "kind": "sell",
                "earliest_turn": 12,
                "latest_turn": 17,
                "phase": "sell",
                "depends_on": ["drop-crop"],
                "actor_demand": {"system": 1},
                "cash_delta": 9,
                "room_delta": {"shed": -2},
                "settlement_lag": 1,
            },
        ]

    def test_feasible_purchase_service_harvest_drop_sell_chain(self):
        result = admit_payload({"state": self.state(), "obligations": self.chain()})
        self.assertTrue(result["admitted"])
        self.assertEqual([], result["structural_conflicts"])
        self.assertEqual("buy", result["schedule"]["buy-seed"]["phase"])
        self.assertLessEqual(result["schedule"]["sell-crop"]["settles_turn"], 18)
        self.assertEqual(64, len(result["source_hash"]))
        self.assertEqual(64, len(result["certificate_hash"]))

    def test_actor_double_booking_is_rejected_before_search(self):
        obligations = [
            {
                "key": key,
                "kind": "service",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "service",
                "actor_demand": {"farmer": 1},
            }
            for key in ("a", "b")
        ]
        result = admit_payload({"state": self.state(), "obligations": obligations})
        self.assertFalse(result["admitted"])
        self.assertIn("actor_window_overload", {row["code"] for row in result["structural_conflicts"]})
        self.assertEqual(0, result["search_nodes"])

    def test_existing_route_reservation_blocks_candidate(self):
        state = self.state(actor_reservations=[{"turn": 10, "resource": "farmer", "units": 1}])
        obligation = {
            "key": "water",
            "kind": "service",
            "earliest_turn": 10,
            "latest_turn": 10,
            "phase": "service",
            "actor_demand": {"farmer": 1},
        }
        result = admit_payload({"state": state, "obligations": [obligation]})
        self.assertFalse(result["admitted"])
        self.assertEqual([], result["ready"])
        self.assertIn("actor_window_overload", {row["code"] for row in result["structural_conflicts"]})

    def test_dependency_cycle_is_rejected(self):
        obligations = [
            {
                "key": "a",
                "kind": "service",
                "earliest_turn": 10,
                "latest_turn": 12,
                "phase": "service",
                "depends_on": ["b"],
            },
            {
                "key": "b",
                "kind": "service",
                "earliest_turn": 10,
                "latest_turn": 12,
                "phase": "service",
                "depends_on": ["a"],
            },
        ]
        result = admit_payload({"state": self.state(), "obligations": obligations})
        self.assertFalse(result["admitted"])
        self.assertEqual({"dependency_cycle"}, {row["code"] for row in result["structural_conflicts"]})

    def test_missing_dependency_is_rejected(self):
        obligation = {
            "key": "harvest",
            "kind": "harvest",
            "earliest_turn": 10,
            "latest_turn": 12,
            "phase": "harvest",
            "depends_on": ["unobserved-water"],
        }
        result = admit_payload({"state": self.state(), "obligations": [obligation]})
        self.assertFalse(result["admitted"])
        self.assertEqual("missing_dependency", result["structural_conflicts"][0]["code"])

    def test_same_phase_output_cannot_fund_same_phase_consumption(self):
        obligations = [
            {
                "key": "a-sale",
                "kind": "sell",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "sell",
                "cash_delta": 5,
            },
            {
                "key": "b-buy",
                "kind": "purchase",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "sell",
                "cash_delta": -5,
            },
        ]
        result = admit_payload({"state": self.state(cash=0), "obligations": obligations})
        self.assertFalse(result["admitted"])
        self.assertEqual("cash_shortfall", result["structural_conflicts"][0]["code"])

    def test_earlier_sale_can_fund_later_phase_purchase_when_explicitly_ordered(self):
        state = self.state(cash=0, phase_order=["sell", "buy", "post"])
        obligations = [
            {
                "key": "sale",
                "kind": "sell",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "sell",
                "cash_delta": 5,
            },
            {
                "key": "buy",
                "kind": "purchase",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "buy",
                "depends_on": ["sale"],
                "cash_delta": -5,
            },
        ]
        result = admit_payload({"state": state, "obligations": obligations})
        self.assertTrue(result["admitted"])

    def test_terminal_settlement_lag_rejects_late_sale(self):
        obligation = {
            "key": "late-sale",
            "kind": "sell",
            "earliest_turn": 18,
            "latest_turn": 18,
            "phase": "sell",
            "cash_delta": 4,
            "settlement_lag": 1,
        }
        result = admit_payload({"state": self.state(), "obligations": [obligation]})
        self.assertFalse(result["admitted"])
        self.assertIn("terminal_unsettled", {row["code"] for row in result["structural_conflicts"]})

    def test_room_overflow_rejected_even_if_same_phase_release_exists(self):
        state = self.state(room_used={"plot": 0, "shed": 3})
        obligations = [
            {
                "key": "a-release",
                "kind": "sell",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "sell",
                "room_delta": {"shed": -2},
            },
            {
                "key": "b-drop",
                "kind": "drop",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "sell",
                "room_delta": {"shed": 2},
            },
        ]
        result = admit_payload({"state": state, "obligations": obligations})
        self.assertFalse(result["admitted"])
        self.assertEqual("room_overflow", result["structural_conflicts"][0]["code"])

    def test_inventory_shortfall_is_rejected(self):
        obligation = {
            "key": "water-twice",
            "kind": "service",
            "earliest_turn": 10,
            "latest_turn": 10,
            "phase": "service",
            "inventory_delta": {"water": -3},
        }
        result = admit_payload({"state": self.state(), "obligations": [obligation]})
        self.assertFalse(result["admitted"])
        self.assertEqual("inventory_shortfall", result["structural_conflicts"][0]["code"])

    def test_overdue_is_separate_and_fails_admission(self):
        obligation = {
            "key": "missed-water",
            "kind": "service",
            "earliest_turn": 6,
            "latest_turn": 9,
            "phase": "service",
        }
        result = admit_payload({"state": self.state(), "obligations": [obligation]})
        self.assertFalse(result["admitted"])
        self.assertEqual(["missed-water"], result["overdue"])
        self.assertIn("deadline_elapsed", {row["code"] for row in result["structural_conflicts"]})

    def test_ready_requires_completed_dependencies_and_resources(self):
        obligations = [
            {
                "key": "water",
                "kind": "service",
                "earliest_turn": 10,
                "latest_turn": 11,
                "phase": "service",
                "depends_on": ["placed"],
                "inventory_delta": {"water": -1},
            },
            {
                "key": "expensive",
                "kind": "purchase",
                "earliest_turn": 10,
                "latest_turn": 11,
                "phase": "buy",
                "cash_delta": -99,
            },
        ]
        state = self.state(completed=["placed"])
        result = admit_payload({"state": state, "obligations": obligations})
        self.assertFalse(result["admitted"])
        self.assertEqual(["water"], result["ready"])
        self.assertEqual("cash_shortfall", result["structural_conflicts"][0]["code"])

    def test_input_order_does_not_change_schedule_or_hash(self):
        payload_a = {"state": self.state(), "obligations": self.chain()}
        payload_b = copy.deepcopy(payload_a)
        payload_b["obligations"].reverse()
        result_a = admit_payload(payload_a)
        result_b = admit_payload(payload_b)
        self.assertEqual(result_a, result_b)

    def test_source_hash_changes_when_observed_state_changes(self):
        first = admit_payload({"state": self.state(), "obligations": self.chain()})
        second = admit_payload({"state": self.state(cash=13), "obligations": self.chain()})
        self.assertNotEqual(first["source_hash"], second["source_hash"])
        self.assertNotEqual(first["certificate_hash"], second["certificate_hash"])

    def test_search_limit_fails_closed(self):
        obligations = [
            {
                "key": "consume",
                "kind": "purchase",
                "earliest_turn": 10,
                "latest_turn": 18,
                "phase": "buy",
                "cash_delta": -99,
            }
        ]
        result = admit_payload({"state": self.state(), "obligations": obligations, "max_nodes": 1})
        self.assertFalse(result["admitted"])
        self.assertEqual("search_limit_exceeded", result["structural_conflicts"][0]["code"])

    def test_recurring_expansion_chains_occurrences_and_terminal_guard_catches_tail(self):
        obligations = recurring_obligations(
            key_prefix="water",
            kind="service",
            first_turn=14,
            every_turns=2,
            occurrences=3,
            tolerance=0,
            actor_demand={"farmer": 1},
            machine_demand={"well": 1},
            settlement_lag=1,
        )
        self.assertEqual(("water:001",), obligations[1].depends_on)
        result = admit_bundle(CalendarState.from_dict(self.state()), obligations)
        self.assertFalse(result.admitted)
        self.assertIn("terminal_unsettled", {row.code for row in result.structural_conflicts})

    def test_unknown_fields_and_bool_integers_are_rejected(self):
        with self.assertRaises(CalendarInputError):
            admit_payload({"state": self.state(), "obligations": [], "surprise": True})
        bad = self.state(current_turn=True)
        with self.assertRaises(CalendarInputError):
            admit_payload({"state": bad, "obligations": []})

    def test_completed_obligation_is_not_rescheduled(self):
        obligations = [
            {
                "key": "placed",
                "kind": "place",
                "earliest_turn": 1,
                "latest_turn": 2,
                "phase": "place",
            },
            {
                "key": "water",
                "kind": "service",
                "earliest_turn": 10,
                "latest_turn": 10,
                "phase": "service",
                "depends_on": ["placed"],
            },
        ]
        result = admit_payload({"state": self.state(completed=["placed"]), "obligations": obligations})
        self.assertTrue(result["admitted"])
        self.assertEqual(["water"], list(result["schedule"]))


if __name__ == "__main__":
    unittest.main()
