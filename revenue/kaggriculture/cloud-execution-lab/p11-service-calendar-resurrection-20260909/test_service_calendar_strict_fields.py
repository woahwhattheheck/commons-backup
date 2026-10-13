# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import unittest

import service_calendar
from service_calendar import (
    CalendarInputError,
    CalendarState,
    Obligation,
    Reservation,
    admit_payload,
)


class StrictNestedFieldTests(unittest.TestCase):
    def minimal_state(self, **overrides):
        state = {
            "current_turn": 0,
            "terminal_turn": 0,
            "cash": 0,
            "actor_capacity": {"farmer": 1},
            "actor_reservations": [],
        }
        state.update(overrides)
        return state

    def test_obligation_typo_cannot_erase_cash_constraint(self):
        payload = {
            "state": self.minimal_state(),
            "obligations": [
                {
                    "key": "buy",
                    "earliest_turn": 0,
                    "latest_turn": 0,
                    "cash_dleta": -999,
                }
            ],
        }
        with self.assertRaisesRegex(
            CalendarInputError,
            r"obligations\[0\] contains unknown fields: cash_dleta",
        ):
            admit_payload(payload)

    def test_state_unknown_field_is_rejected(self):
        state = self.minimal_state(cahs=999)
        with self.assertRaisesRegex(
            CalendarInputError,
            r"state contains unknown fields: cahs",
        ):
            CalendarState.from_dict(state)

    def test_obligation_unknown_field_is_rejected_directly(self):
        with self.assertRaisesRegex(
            CalendarInputError,
            r"obligations\[4\] contains unknown fields: room_dleta",
        ):
            Obligation.from_dict(
                {
                    "key": "drop",
                    "earliest_turn": 0,
                    "latest_turn": 0,
                    "room_dleta": {"shed": 1},
                },
                4,
            )

    def test_reservation_unknown_field_is_rejected_directly_and_nested(self):
        bad = {"turn": 0, "resource": "farmer", "unitz": 1}
        with self.assertRaisesRegex(
            CalendarInputError,
            r"reservation contains unknown fields: unitz",
        ):
            Reservation.from_dict(bad, "reservation")
        with self.assertRaisesRegex(
            CalendarInputError,
            r"state\.actor_reservations\[0\] contains unknown fields: unitz",
        ):
            CalendarState.from_dict(self.minimal_state(actor_reservations=[bad]))

    def test_known_fields_preserve_existing_admission_behavior(self):
        result = admit_payload(
            {
                "state": self.minimal_state(cash=5),
                "obligations": [
                    {
                        "key": "buy",
                        "kind": "purchase",
                        "earliest_turn": 0,
                        "latest_turn": 0,
                        "phase": "buy",
                        "cash_delta": -5,
                    }
                ],
            }
        )
        self.assertTrue(result["admitted"])
        self.assertEqual([], result["structural_conflicts"])

    def test_reload_is_idempotent(self):
        first = importlib.reload(service_calendar)
        second = importlib.reload(first)
        with self.assertRaises(CalendarInputError):
            second.admit_payload(
                {
                    "state": self.minimal_state(),
                    "obligations": [
                        {
                            "key": "buy",
                            "earliest_turn": 0,
                            "latest_turn": 0,
                            "cash_dleta": -1,
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
