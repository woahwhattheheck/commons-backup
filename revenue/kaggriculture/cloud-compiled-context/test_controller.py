# SPDX-License-Identifier: MIT OR CC-BY-4.0
import copy
import json
import unittest
import controller as c


def observation(step=0, animals=0, pending=0, cash=3000):
    tiles = [[None for _ in range(6)] for _ in range(6)]
    for n in range(animals):
        tiles[n//6][n%6] = {"kind": "COOP", "animal": "GOOSE", "fed_today": False}
    return {"player": 0, "day": step//24, "hour": step%24, "step": step,
            "farms": [{"tiles": tiles, "money": cash, "farmer": [2,2], "hands": [], "hires_today": 0}],
            "private": {"shed": {"GOOSE": pending}, "inventories": [{}], "seeds": {}},
            "market": {"prices": {"WHEAT": 25, "EGG": 50}}}


class ControllerTests(unittest.TestCase):
    def test_buy_is_not_completion_and_pending_blocks_rebuy(self):
        obs = observation()
        s = c.advance(obs)
        action = {"farmer": ["PASS"], "hands": [], "market": [["BUY_ANIMAL", "GOOSE", 3]]}
        a, s = c.constrain_orders(action, c.select_context(obs), s)
        self.assertEqual(a["market"], action["market"])
        s = c.advance(observation(1, pending=3), previous=s)
        self.assertEqual((s["status"], s["phase"]), ("active", "install"))
        a, _ = c.constrain_orders(action, c.select_context(observation(1, pending=3)), s)
        self.assertEqual(a["market"], [])

    def test_completion_requires_actual_target_and_cleared_stock(self):
        s = c.advance(observation(pending=2), options={"daily_crops": 0})
        s = c.advance(observation(1, animals=2), previous=s)
        self.assertEqual(s["status"], "completed")
        self.assertEqual(s["completed_count"], 1)
        self.assertEqual(s["bank"][0]["outcome"]["advancement_score"], 2)
        s = c.advance(observation(2, animals=2), previous=s)
        self.assertEqual(s["completed_count"], 1)

    def test_stale_plan_expires_and_failed_requests_do_not_enter_bank(self):
        s = c.advance(observation())
        s = c.advance(observation(24, pending=2), previous=s)
        self.assertEqual(s["feedback"][-1]["outcome"], "expired")
        self.assertEqual(s["bank"], [])
        self.assertEqual(s["animal_allowance"], 0)
        self.assertEqual(s["installation_target"], 2)

    def test_cash_and_feed_reserve(self):
        obs = observation(24, animals=10, cash=500)
        s = c.advance(obs)
        self.assertEqual(s["feed_needed"], 10)
        self.assertEqual(s["cash_reserve"], 410)
        a, _ = c.constrain_orders({"farmer": ["PASS"], "hands": [], "market": [["BUY_ANIMAL", "GOOSE", 1]]}, c.select_context(obs), s)
        self.assertEqual(a["market"], [])

    def test_terminal_inclusive_boundary_and_horizons(self):
        ctx = c.select_context(observation(717))
        self.assertEqual(ctx["remaining_actions"], 2)
        s = c.advance(observation(717))
        self.assertEqual(s["phase"], "liquidate")
        self.assertEqual(s["animal_allowance"], 0)
        self.assertEqual(s["seed_allowance"], 0)

    def test_retry_bound_no_input_mutation_and_serializable_state(self):
        obs = observation()
        original = copy.deepcopy(obs)
        s = c.advance(obs, options={"daily_crops": 0, "max_attempts": 3})
        for step in range(4):
            obs["step"] = step
            obs["hour"] = step
            s = c.advance(obs, previous=s)
            a, s = c.constrain_orders({"farmer": ["PASS"], "hands": [], "market": [["BUY_ANIMAL", "GOOSE", 1]]}, c.select_context(obs), s)
        self.assertEqual(a["market"], [])
        json.dumps(s, allow_nan=False)
        self.assertEqual(c.advance(obs, previous=s), s)
        self.assertEqual(c.advance(original, previous=s)["animal_attempts"], 0)
        self.assertEqual(original, observation())

    def test_installation_intent_finishes_same_target(self):
        obs = observation()
        obs["private"]["inventories"] = [{"GOOSE": 1}]
        obs["farms"][0]["tiles"][2][2] = {"kind": "WEED"}
        # Force this sole available tile to exercise the full chain.
        obs["farms"][0]["tiles"] = [["LOCKED"]*6 for _ in range(6)]
        obs["farms"][0]["tiles"][2][2] = {"kind": "WEED"}
        jobs, feedback = c.installation_jobs(obs)
        self.assertEqual(jobs[0]["next_operation"], ["DIG"])
        obs["farms"][0]["tiles"][2][2] = None
        jobs, feedback = c.installation_jobs(obs, jobs)
        self.assertEqual(jobs[0]["next_operation"], ["BUILD_COOP"])
        obs["farms"][0]["tiles"][2][2] = {"kind": "COOP"}
        jobs, feedback = c.installation_jobs(obs, jobs)
        self.assertEqual(jobs[0]["next_operation"], ["PLACE", "GOOSE"])
        self.assertEqual(feedback, [])
        obs["farms"][0]["tiles"][2][2]["animal"] = "GOOSE"
        obs["private"]["inventories"] = [{}]
        jobs, feedback = c.installation_jobs(obs, jobs)
        self.assertEqual(jobs, [])
        self.assertEqual(feedback[0]["outcome"], "installation_completed")

    def test_installation_reservation_and_conflicting_live_state(self):
        obs = observation()
        obs["farms"][0]["hands"] = [[2,2]]
        obs["private"]["inventories"] = [{"GOOSE": 1}, {"GOOSE": 1}]
        jobs, _ = c.installation_jobs(obs)
        self.assertNotEqual(jobs[0]["target"], jobs[1]["target"])
        old = jobs[0]["target"]
        x,y = old
        obs["farms"][0]["tiles"][y][x] = {"kind": "PLANT", "crop": "WHEAT"}
        jobs, _ = c.installation_jobs(obs, jobs)
        self.assertNotEqual(jobs[0]["target"], old)

    def test_class_matched_examples_are_bounded_and_precede_live_state(self):
        s = c.advance(observation(pending=2), options={"daily_crops": 0})
        s = c.advance(observation(1, animals=2), previous=s)
        # Same kind of situation next day retrieves own observed success.
        obs = observation(24, animals=2, pending=1)
        s = c.advance(obs, previous=s)
        packet = c.situation_packet(c.select_context(obs), s)
        self.assertEqual(len(packet), 2)
        self.assertIn("example", packet[0])
        self.assertIn("live_state", packet[-1])
        self.assertNotIn("seed", packet[-1]["live_state"])


if __name__ == "__main__":
    unittest.main()
