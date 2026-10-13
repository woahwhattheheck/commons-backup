import unittest

from audit_engine import EXPECTED_ENGINE_BLOB, assert_engine_authority
from carrybank import admit_carrybank_pickup


BASE = dict(
    current_unit_action=["PASS"],
    adjacent_to_shed=True,
    shed={"WHEAT": 8, "FERTILIZER": 4, "MILK": 86},
    shed_capacity=100,
    projected_shed_inflow_units=4,
    current_inventory={},
    future_unit_actions=[["FEED"], ["FEED"], ["FERTILIZE"]],
    turns_remaining=3,
)


class EngineAuthorityTests(unittest.TestCase):
    def test_official_engine_blob_is_exact(self):
        self.assertEqual(EXPECTED_ENGINE_BLOB, assert_engine_authority())


class CarrybankTests(unittest.TestCase):
    def decide(self, **overrides):
        args = dict(BASE)
        args.update(overrides)
        return admit_carrybank_pickup(**args)

    def test_multi_qty_wheat_pickup_is_bounded_by_future_sink(self):
        decision = self.decide()
        self.assertIsNotNone(decision)
        self.assertEqual(["PICKUP", "WHEAT", 2], decision.action())
        self.assertEqual(2, decision.pressure_units)
        self.assertEqual(2, decision.guaranteed_consumption_units)

    def test_refuses_to_displace_productive_action(self):
        self.assertIsNone(self.decide(current_unit_action=["HARVEST"]))

    def test_refuses_when_not_at_shed(self):
        self.assertIsNone(self.decide(adjacent_to_shed=False))

    def test_refuses_without_capacity_pressure(self):
        self.assertIsNone(
            self.decide(
                shed={"WHEAT": 8, "FERTILIZER": 4},
                projected_shed_inflow_units=4,
            )
        )

    def test_existing_inventory_consumes_future_sink_budget(self):
        self.assertIsNone(
            self.decide(current_inventory={"WHEAT": 2, "FERTILIZER": 1})
        )

    def test_fertilizer_is_supported_when_it_has_the_larger_proven_sink(self):
        decision = self.decide(
            future_unit_actions=[["FERTILIZE"], ["FERTILIZE"], ["FERTILIZE"]],
            turns_remaining=3,
        )
        self.assertIsNotNone(decision)
        self.assertEqual(["PICKUP", "FERTILIZER", 2], decision.action())

    def test_non_consumable_shed_products_are_never_hoisted(self):
        self.assertIsNone(
            self.decide(
                shed={"MILK": 100},
                future_unit_actions=[["HARVEST"], ["COLLECT_FERTILIZER"]],
            )
        )

    def test_pressure_caps_pickup_quantity(self):
        decision = self.decide(
            shed={"WHEAT": 99},
            projected_shed_inflow_units=2,
            future_unit_actions=[["FEED"], ["FEED"], ["FEED"]],
            turns_remaining=3,
        )
        self.assertEqual(["PICKUP", "WHEAT", 1], decision.action())

    def test_only_same_day_prefix_counts(self):
        decision = self.decide(
            future_unit_actions=[["PASS"], ["FEED"], ["FEED"]],
            turns_remaining=1,
        )
        self.assertIsNone(decision)

    def test_zero_turns_remaining_refuses(self):
        self.assertIsNone(self.decide(turns_remaining=0))

    def test_prefers_wheat_on_equal_sink(self):
        decision = self.decide(
            future_unit_actions=[["FEED"], ["FERTILIZE"]],
            turns_remaining=2,
        )
        self.assertEqual(["PICKUP", "WHEAT", 1], decision.action())

    def test_malformed_actions_fail_closed(self):
        self.assertIsNone(
            self.decide(
                future_unit_actions=[None, {}, [], "FEED"],
                turns_remaining=4,
            )
        )


if __name__ == "__main__":
    unittest.main()
