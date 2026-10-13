import unittest

from targeted_rescue import Coverage, coverage_from_tail, plan_targeted_rescue, uncovered_starving_targets


def base_obs():
    tiles = [[None for _ in range(5)] for _ in range(5)]
    tiles[1][1] = {"kind": "PASTURE", "animal": "SHEEP", "fed_today": False, "consecutive_unfed": 1}
    tiles[3][3] = {"kind": "PASTURE", "animal": "COW", "fed_today": False, "consecutive_unfed": 1}
    return {
        "step": 40,
        "player": 0,
        "farms": [{"farmer": [2, 2], "hands": [[2, 3]], "tiles": tiles}],
        "private": {"inventories": [{"WHEAT": 1}, {}], "shed": {"WHEAT": 5}},
    }


def action(farmer=None, hand=None, market=None):
    return {"farmer": farmer or ["PASS"], "hands": [hand or ["PASS"]], "market": market or []}


class TargetedRescueTest(unittest.TestCase):
    def test_different_target_feed_does_not_cover_starving_sheep(self):
        obs = base_obs()
        tail = [action(hand=["EAST"]), action(hand=["FEED"])]
        coverage = coverage_from_tail(obs, action(), tail)
        self.assertEqual(coverage.feed_targets, frozenset({(3, 3)}))
        self.assertEqual(uncovered_starving_targets(obs, coverage), ((1, 1),))

    def test_same_target_future_feed_suppresses_that_candidate(self):
        obs = base_obs()
        obs["farms"][0]["hands"][0] = [1, 2]
        tail = [action(hand=["NORTH"]), action(hand=["FEED"])]
        coverage = coverage_from_tail(obs, action(), tail)
        self.assertEqual(coverage.feed_targets, frozenset({(1, 1)}))
        self.assertEqual(uncovered_starving_targets(obs, coverage), ((3, 3),))

    def test_weed_motion_is_ambiguous_and_fails_closed(self):
        obs = base_obs()
        obs["farms"][0]["tiles"][2][2] = {"kind": "WEED"}
        self.assertIsNone(coverage_from_tail(obs, action(), [action(hand=["NORTH"])]))

    def test_current_returned_movement_is_used_for_projection(self):
        obs = base_obs()
        obs["farms"][0]["hands"][0] = [2, 2]
        coverage = coverage_from_tail(obs, action(hand=["SOUTH"]), [action(hand=["EAST"]), action(hand=["FEED"])])
        self.assertEqual(coverage.feed_targets, frozenset({(3, 3)}))

    def test_tail_stops_at_calendar_boundary(self):
        obs = base_obs()
        obs["step"] = 46
        coverage = coverage_from_tail(obs, action(), [action(hand=["EAST"]), action(hand=["FEED"])])
        self.assertEqual(coverage.feed_targets, frozenset())
        self.assertEqual(coverage.future_feed_count, 0)

    def test_bad_strike_type_fails_closed(self):
        obs = base_obs()
        obs["farms"][0]["tiles"][1][1]["consecutive_unfed"] = True
        self.assertIsNone(uncovered_starving_targets(obs, Coverage(frozenset(), 0)))

    def test_planner_rescues_uncovered_target_and_returns_origin(self):
        obs = base_obs()
        # Later hand feed covers cow; farmer has enough PASS callbacks to rescue sheep.
        tail = [action(hand=["EAST"]), action(hand=["FEED"])] + [action() for _ in range(10)]
        plan, reason = plan_targeted_rescue(obs, action(), tail, queues_empty=True)
        self.assertEqual(reason, "target_uncovered")
        self.assertEqual(plan.target, (1, 1))
        self.assertEqual(plan.positions[0], (2, 2))
        self.assertTrue(plan.commands)
        self.assertIn(plan.commands[-1][0], {"EAST", "WEST", "NORTH", "SOUTH"})

    def test_planner_fails_closed_when_queues_exist(self):
        plan, reason = plan_targeted_rescue(base_obs(), action(), [action()] * 10, queues_empty=False)
        self.assertIsNone(plan)
        self.assertEqual(reason, "queued_work")

    def test_planner_respects_authored_farmer_work(self):
        obs = base_obs()
        tail = [action(farmer=["CARE"])] + [action() for _ in range(10)]
        plan, reason = plan_targeted_rescue(obs, action(), tail, queues_empty=True)
        self.assertIsNone(plan)
        self.assertEqual(reason, "no_safe_round_trip")

    def test_planner_pickup_preserves_reserved_wheat(self):
        obs = base_obs()
        obs["private"]["inventories"][0] = {}
        obs["private"]["shed"]["WHEAT"] = 1
        tail = [action(hand=["PICKUP", "WHEAT", 1])] + [action() for _ in range(10)]
        plan, reason = plan_targeted_rescue(obs, action(), tail, queues_empty=True)
        self.assertIsNone(plan)
        self.assertEqual(reason, "wheat_reserved")

    def test_planner_uses_shed_pickup_when_unreserved(self):
        obs = base_obs()
        obs["private"]["inventories"][0] = {}
        tail = [action() for _ in range(12)]
        plan, reason = plan_targeted_rescue(obs, action(), tail, queues_empty=True)
        self.assertEqual(reason, "target_uncovered")
        self.assertTrue(plan.needs_pickup)
        self.assertEqual(plan.commands[0], ("PICKUP", "WHEAT"))


if __name__ == "__main__":
    unittest.main()
