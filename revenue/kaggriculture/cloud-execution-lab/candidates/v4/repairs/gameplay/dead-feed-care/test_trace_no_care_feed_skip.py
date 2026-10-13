import copy
import unittest

import trace_no_care_feed_skip as T

CFG = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720}


def cow(*, unfed=0, fed=False, cared=False, pending=0, placed_day=0):
    return {
        "kind": "PASTURE",
        "animal": "COW",
        "placed_day": placed_day,
        "yield_units": 0,
        "pending_care_bonus": pending,
        "consecutive_unfed": unfed,
        "fed_today": fed,
        "cared_today": cared,
        "fertilizer_available": False,
    }


def observation(step, *, tile=None, wheat=1, position=None, hands=None):
    tiles0 = [[None for _ in range(10)] for _ in range(10)]
    tiles1 = [[None for _ in range(10)] for _ in range(10)]
    tiles0[1][1] = cow() if tile is None else tile
    own_hands = [] if hands is None else hands
    farm0 = {
        "tiles": tiles0,
        "farmer": [1, 1] if position is None else position,
        "hands": own_hands,
    }
    farm1 = {"tiles": tiles1, "farmer": [0, 0], "hands": []}
    inventories = [{"WHEAT": wheat}] + [{"WHEAT": wheat} for _ in own_hands]
    return {
        "step": step,
        "player": 0,
        "farms": [farm0, farm1],
        "private": {"inventories": inventories, "shed": {}, "seeds": {}},
    }


def action(farmer=None, hands=None):
    return {
        "farmer": ["FEED"] if farmer is None else farmer,
        "hands": [] if hands is None else hands,
        "market": [],
    }


def suffix(start_step, *, overrides=None):
    overrides = overrides or {}
    end = (start_step // 24) * 24 + 23
    rows = []
    for step in range(start_step + 1, end + 1):
        obs = observation(step)
        act = action(["PASS"])
        if step in overrides:
            obs, act = overrides[step]
        rows.append({"observation": obs, "action": act})
    return rows


class TraceNoCareFeedSkipTests(unittest.TestCase):
    def test_earlier_feed_with_gapless_no_care_suffix_is_conditional_only(self):
        obs = observation(20)
        current = action()
        certs = T.plan_trace_no_care_feed_skip(current, obs, CFG, suffix(20))
        self.assertEqual(len(certs), 1)
        cert = certs[0]
        self.assertEqual(cert["site"], [1, 1])
        self.assertEqual(cert["current_hour"], 20)
        self.assertEqual(cert["synthetic_fast_gate_step"], 23)
        self.assertTrue(cert["fixed_tape_only"])
        self.assertTrue(cert["caller_supplied_tape_only"])
        self.assertFalse(cert["authenticated_trace_claim"])
        self.assertFalse(cert["current_native_reachability_claim"])
        self.assertEqual(
            cert["remaining_day_certificate"]["provenance"],
            "CALLER_SUPPLIED_UNVERIFIED_TAPE",
        )
        self.assertFalse(cert["activation_claim"])
        candidate = T.build_single_counterfactual(
            current, obs, CFG, suffix(20), enabled=True)
        self.assertEqual(candidate["farmer"], ["PASS"])

    def test_current_same_site_extended_plus_exact_feed_is_rejected(self):
        obs = observation(20, hands=[[1, 1]])
        current = action(["FEED", "extra"], [["FEED"]])
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, suffix(20)), [])

    def test_later_same_site_care_blocks(self):
        obs = observation(20)
        current = action()
        bad_obs = observation(22)
        bad_action = action(["CARE"])
        remaining = suffix(20, overrides={22: (bad_obs, bad_action)})
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, remaining), [])

    def test_later_same_site_feed_blocks_overlap_with_service_lane(self):
        obs = observation(20)
        current = action()
        bad_obs = observation(21)
        bad_action = action(["FEED"])
        remaining = suffix(20, overrides={21: (bad_obs, bad_action)})
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, remaining), [])

    def test_care_elsewhere_does_not_block(self):
        obs = observation(20)
        current = action()
        later_obs = observation(22, position=[2, 2])
        later_action = action(["CARE"])
        remaining = suffix(20, overrides={22: (later_obs, later_action)})
        self.assertEqual(len(T.plan_trace_no_care_feed_skip(current, obs, CFG, remaining)), 1)

    def test_suffix_must_be_complete_and_step_exact(self):
        obs = observation(20)
        current = action()
        remaining = suffix(20)
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, remaining[:-1]), [])
        wrong = copy.deepcopy(remaining)
        wrong[0]["observation"]["step"] = 22
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, wrong), [])

    def test_hour23_is_owned_by_existing_fasting_helper(self):
        obs = observation(23)
        current = action()
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, obs, CFG, []), [])

    def test_inherits_physical_wheat_and_escape_guards(self):
        current = action()
        no_wheat = observation(20, wheat=0)
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, no_wheat, CFG, suffix(20)), [])
        escape = observation(20, tile=cow(unfed=1))
        self.assertEqual(T.plan_trace_no_care_feed_skip(current, escape, CFG, suffix(20)), [])

    def test_inherits_pending_care_bonus_production_boundary(self):
        # COW first yield day is 8. At current day 7, EOD produces for a day-0
        # cow and an existing pending CARE bonus requires feeding.
        step = 7 * 24 + 20
        obs = observation(step, tile=cow(pending=1, placed_day=0))
        self.assertEqual(T.plan_trace_no_care_feed_skip(action(), obs, CFG, suffix(step)), [])

    def test_truthy_enable_poison_preserves_exact_identity(self):
        obs = observation(20)
        current = action()
        remaining = suffix(20)
        for poison in (1, 1.0, "false", [True], {"enabled": True}):
            with self.subTest(poison=poison):
                self.assertIs(
                    T.build_single_counterfactual(
                        current, obs, CFG, remaining, enabled=poison
                    ),
                    current,
                )

    def test_current_and_suffix_inputs_are_not_mutated(self):
        obs = observation(20)
        current = action()
        remaining = suffix(20)
        before = copy.deepcopy((obs, current, remaining))
        T.plan_trace_no_care_feed_skip(current, obs, CFG, remaining)
        T.build_single_counterfactual(current, obs, CFG, remaining, enabled=True)
        self.assertEqual((obs, current, remaining), before)

    def test_disabled_or_bad_candidate_index_is_identity(self):
        obs = observation(20)
        current = action()
        remaining = suffix(20)
        self.assertIs(T.build_single_counterfactual(current, obs, CFG, remaining), current)
        self.assertIs(
            T.build_single_counterfactual(
                current, obs, CFG, remaining, candidate_index=99, enabled=True),
            current,
        )


if __name__ == "__main__":
    unittest.main()
