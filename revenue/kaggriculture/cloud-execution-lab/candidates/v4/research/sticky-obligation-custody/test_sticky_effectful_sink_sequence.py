from __future__ import annotations

import unittest

import sticky_obligation as S


class StickyEffectfulSinkSequenceTests(unittest.TestCase):
    def test_one_real_feed_plus_later_noop_feed_is_only_one_sink_unit(self):
        obligation = S.issue_carry_consumption(
            actor="hand-0",
            item="WHEAT",
            quantity=2,
            created_step=10,
            due_end=23,
            capacity_pressure_units=2,
        )
        got = S.prove_carry_consumption(
            obligation,
            [
                {
                    "step": 11,
                    "actor": "hand-0",
                    "op": "FEED",
                    "consumption_authenticated": True,
                    "consumed_item": "WHEAT",
                    "consumed_units": 1,
                },
                {
                    "step": 12,
                    "actor": "hand-0",
                    "op": "FEED",
                    "consumption_authenticated": False,
                },
            ],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["sink_units"], 1)
        self.assertEqual(got["reserved_units"], 2)
        self.assertEqual(got["reason"], "insufficient_actor_local_consumption_capacity")


if __name__ == "__main__":
    unittest.main()
