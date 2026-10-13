import unittest

from carrybank import admit_carrybank_pickup


BASE = dict(
    current_unit_action=["PASS"],
    adjacent_to_shed=True,
    shed={"WHEAT": 50, "FERTILIZER": 50},
    shed_capacity=100,
    projected_shed_inflow_units=2,
    current_inventory={},
    turns_remaining=3,
)


class AcquisitionAwareSinkTests(unittest.TestCase):
    def decide(self, future, **overrides):
        args = dict(BASE, future_unit_actions=future)
        args.update(overrides)
        return admit_carrybank_pickup(**args)

    def test_future_wheat_pickup_spends_the_only_feed_sink(self):
        self.assertIsNone(self.decide([["PICKUP", "WHEAT"], ["FEED"]], turns_remaining=2))

    def test_two_feeds_minus_future_pickup_leaves_one_safe_hoist(self):
        decision = self.decide([["PICKUP", "WHEAT", 1], ["FEED"], ["FEED"]])
        self.assertEqual(["PICKUP", "WHEAT", 1], decision.action())
        self.assertEqual(1, decision.guaranteed_consumption_units)

    def test_collect_fertilizer_spends_fertilize_sink(self):
        self.assertIsNone(
            self.decide([["COLLECT_FERTILIZER"], ["FERTILIZE"]], turns_remaining=2)
        )

    def test_drop_truncates_consumption_guarantee(self):
        self.assertIsNone(self.decide([["DROP"], ["FEED"], ["FEED"]]))

    def test_sink_before_drop_still_counts(self):
        decision = self.decide([["FEED"], ["DROP"], ["FEED"]])
        self.assertEqual(["PICKUP", "WHEAT", 1], decision.action())

    def test_wheat_harvest_makes_wheat_sink_capacity_unprovable(self):
        self.assertIsNone(self.decide([["HARVEST"], ["FEED"]], turns_remaining=2))

    def test_harvest_does_not_create_fertilizer(self):
        decision = self.decide(
            [["HARVEST"], ["FERTILIZE"]], turns_remaining=2,
            shed={"FERTILIZER": 100},
        )
        self.assertEqual(["PICKUP", "FERTILIZER", 1], decision.action())

    def test_malformed_matching_pickup_refuses_item(self):
        self.assertIsNone(
            self.decide([["PICKUP", "WHEAT", "x"], ["FEED"], ["FEED"]])
        )


if __name__ == "__main__":
    unittest.main()
