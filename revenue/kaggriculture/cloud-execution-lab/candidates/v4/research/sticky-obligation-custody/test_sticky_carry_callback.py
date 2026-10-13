from __future__ import annotations

import unittest

import sticky_obligation as S


def carry(*, quantity: int = 1):
    return S.issue_carry_consumption(
        actor="hand-0",
        item="WHEAT",
        quantity=quantity,
        created_step=10,
        due_end=23,
        capacity_pressure_units=quantity,
    )


def row(step: int, actor: str, op: str):
    payload = {"step": step, "actor": actor, "op": op}
    if op.upper() == "FEED":
        payload.update(
            consumption_authenticated=True,
            consumed_item="WHEAT",
            consumed_units=1,
        )
    return payload


class CarryCallbackCustodyTests(unittest.TestCase):
    def test_duplicate_feed_rows_cannot_mint_two_sink_units(self):
        with self.assertRaisesRegex(
            S.UnsupportedObligation,
            "duplicate obligated actor row in callback",
        ):
            S.prove_carry_consumption(
                carry(quantity=2),
                [
                    row(11, "hand-0", "FEED"),
                    row(11, "hand-0", "FEED"),
                ],
                current_inventory_units=0,
            )

    def test_early_feed_cannot_hide_same_callback_duplicate_drop(self):
        with self.assertRaisesRegex(
            S.UnsupportedObligation,
            "duplicate obligated actor row in callback",
        ):
            S.prove_carry_consumption(
                carry(),
                [
                    row(11, "hand-0", "FEED"),
                    row(11, "hand-0", "DROP"),
                ],
                current_inventory_units=0,
            )

    def test_same_callback_other_actor_does_not_collide(self):
        got = S.prove_carry_consumption(
            carry(),
            [
                row(11, "hand-0", "FEED"),
                row(11, "hand-1", "DROP"),
            ],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])
        self.assertEqual(11, got["sink_step"])

    def test_same_actor_across_different_callbacks_remains_legal(self):
        got = S.prove_carry_consumption(
            carry(quantity=2),
            [
                row(11, "hand-0", "FEED"),
                row(12, "hand-0", "FEED"),
            ],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])
        self.assertEqual(12, got["sink_step"])


if __name__ == "__main__":
    unittest.main()
