# SPDX-License-Identifier: Apache-2.0
import copy
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p07_joint_actor_assignment import JointActorAssignment


def obs(step, day, hands, *, player=0):
    return {
        "step": step,
        "day": day,
        "player": player,
        "farms": [
            {"hands": [{} for _ in range(hands)]},
            {"hands": []},
        ],
    }


def action(hands, market=None, farmer=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": copy.deepcopy(hands),
        "market": [] if market is None else copy.deepcopy(market),
    }


def route(*rows):
    return list(rows)


class P07JointActorAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {"maxMarketOrdersPerTurn": 10}

    def test_flag_off_is_exact_identity_and_stateless(self):
        lane = JointActorAssignment(enabled=False)
        selected = action([["PASS"]], [["HIRE"]])
        out, report = lane.apply(obs(0, 0, 1), self.cfg, selected, route=[selected], route_id="MAIN")
        self.assertIs(out, selected)
        self.assertEqual(report, {"enabled": False, "changed": False, "reason": "flag_off"})

    def test_observed_underfill_selects_strongest_new_lanes(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"], ["HIRE"]])
        tape = route(
            first,
            action([["PASS"], ["PASS"], ["HARVEST"], ["WATER"]]),
            action([["PASS"], ["PASS"], ["HARVEST"], ["PASS"]]),
        )
        out0, r0 = lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="MAIN")
        self.assertIs(out0, first)
        self.assertEqual(r0["reason"], "hire_receipt_pending")

        farmer = ["EAST"]
        market = [["SELL", "WHEAT", 1]]
        second = {"farmer": farmer, "hands": [["PASS"], ["PASS"], ["HARVEST"], ["WATER"]], "market": market}
        original = copy.deepcopy(second)
        out1, r1 = lane.apply(obs(1, 0, 3), self.cfg, second, route=tape, route_id="MAIN")
        self.assertEqual(out1["hands"], [["PASS"], ["HARVEST"], ["WATER"]])
        self.assertEqual(r1["mapping"], [0, 2, 3])
        self.assertTrue(r1["changed"])
        self.assertIs(out1["farmer"], farmer)
        self.assertIs(out1["market"], market)
        self.assertEqual(second, original)

    def test_existing_actor_identity_is_never_reassigned(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"], ["PASS"]], [["HIRE"], ["HIRE"]])
        tape = route(first, action([["PASS"], ["PASS"], ["HARVEST"], ["WATER"]]))
        lane.apply(obs(0, 0, 2), self.cfg, first, route=tape, route_id="MAIN")
        second = action([["PASS"], ["PASS"], ["HARVEST"], ["WATER"]])
        out, report = lane.apply(obs(1, 0, 3), self.cfg, second, route=tape, route_id="MAIN")
        self.assertEqual(report["mapping"][:2], [0, 1])
        self.assertEqual(out["hands"][:2], second["hands"][:2])

    def test_mapping_is_stable_not_reoptimized_each_step(self):
        lane = JointActorAssignment(enabled=True)
        tape = route(
            action([["PASS"]], [["HIRE"], ["HIRE"]]),
            action([["PASS"], ["HARVEST"], ["PASS"]]),
            action([["PASS"], ["PASS"], ["HARVEST"]]),
        )
        lane.apply(obs(0, 0, 1), self.cfg, tape[0], route=tape, route_id="MAIN")
        out1, r1 = lane.apply(obs(1, 0, 2), self.cfg, tape[1], route=tape, route_id="MAIN")
        self.assertEqual(r1["mapping"], [0, 1])
        out2, r2 = lane.apply(obs(2, 0, 2), self.cfg, tape[2], route=tape, route_id="MAIN")
        self.assertEqual(r2["mapping"], [0, 1])
        self.assertEqual(out2["hands"], [["PASS"], ["PASS"]])

    def test_fully_completed_hires_do_not_change_action(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        second = action([["PASS"], ["HARVEST"], ["WATER"]])
        tape = route(first, second)
        lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="MAIN")
        out, report = lane.apply(obs(1, 0, 3), self.cfg, second, route=tape, route_id="MAIN")
        self.assertIs(out, second)
        self.assertEqual(report["reason"], "all_hires_completed")

    def test_nonexecutable_hire_suffix_is_not_counted(self):
        lane = JointActorAssignment(enabled=True)
        cfg = {"maxMarketOrdersPerTurn": 2}
        selected = action([["PASS"]], [["SELL", "WHEAT", 1], [], ["HIRE"]])
        out, report = lane.apply(obs(0, 0, 1), cfg, selected, route=[selected], route_id="MAIN")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "no_observed_underfill")

    def test_market_cap_has_max_one_semantics(self):
        lane = JointActorAssignment(enabled=True)
        cfg = {"maxMarketOrdersPerTurn": 0}
        selected = action([["PASS"]], [["HIRE"], ["HIRE"]])
        _, report = lane.apply(obs(0, 0, 1), cfg, selected, route=[selected], route_id="MAIN")
        self.assertEqual(report["requested_hands"], 1)

    def test_zero_completed_hires_removes_only_requested_suffix(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        second = action([["EAST"], ["HARVEST"], ["WATER"]])
        tape = route(first, second)
        lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="MAIN")
        out, report = lane.apply(obs(1, 0, 1), self.cfg, second, route=tape, route_id="MAIN")
        self.assertEqual(report["mapping"], [0])
        self.assertEqual(out["hands"], [["EAST"]])

    def test_late_join_cannot_infer_prior_hire(self):
        lane = JointActorAssignment(enabled=True)
        selected = action([["PASS"], ["HARVEST"], ["WATER"]])
        out, report = lane.apply(obs(26, 1, 2), self.cfg, selected, route=[action([])] * 26 + [selected], route_id="MAIN")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "no_observed_underfill")

    def test_route_switch_fails_closed_for_interval(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        tape = route(first, action([["PASS"], ["HARVEST"], ["WATER"]]))
        lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="A")
        second = tape[1]
        out, report = lane.apply(obs(1, 0, 2), self.cfg, second, route=tape, route_id="B")
        self.assertIs(out, second)
        self.assertEqual(report["reason"], "route_switch")

    def test_repeated_step_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        selected = action([["PASS"]])
        tape = route(selected, selected)
        lane.apply(obs(0, 0, 1), self.cfg, selected, route=tape, route_id="A")
        out, report = lane.apply(obs(0, 0, 1), self.cfg, selected, route=tape, route_id="A")
        # step zero is an explicit episode reset; a nonzero retry is the blocked case
        self.assertEqual(report["reason"], "episode_reset")
        lane.apply(obs(1, 0, 1), self.cfg, selected, route=tape, route_id="A")
        out, report = lane.apply(obs(1, 0, 1), self.cfg, selected, route=tape, route_id="A")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "repeated_or_reordered_step")

    def test_step_gap_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        selected = action([["PASS"]])
        tape = [selected] * 4
        lane.apply(obs(0, 0, 1), self.cfg, selected, route=tape, route_id="A")
        out, report = lane.apply(obs(2, 0, 1), self.cfg, selected, route=tape, route_id="A")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "step_gap")

    def test_day_reset_drops_active_mapping(self):
        lane = JointActorAssignment(enabled=True)
        tape = route(
            action([["PASS"]], [["HIRE"], ["HIRE"]]),
            action([["PASS"], ["HARVEST"], ["WATER"]]),
            action([["PASS"], ["PASS"], ["HARVEST"]]),
        )
        lane.apply(obs(0, 0, 1), self.cfg, tape[0], route=tape, route_id="A")
        lane.apply(obs(1, 0, 2), self.cfg, tape[1], route=tape, route_id="A")
        out, report = lane.apply(obs(2, 1, 2), self.cfg, tape[2], route=tape, route_id="A")
        self.assertIs(out, tape[2])
        self.assertEqual(report["reason"], "day_reset")

    def test_logical_cardinality_ambiguity_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        second = action([["PASS"], ["HARVEST"], ["WATER"], ["DIG"]])
        tape = route(first, second)
        lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="A")
        out, report = lane.apply(obs(1, 0, 2), self.cfg, second, route=tape, route_id="A")
        self.assertIs(out, second)
        self.assertEqual(report["reason"], "ambiguous_underfill")

    def test_active_physical_cardinality_drift_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        tape = route(
            action([["PASS"]], [["HIRE"], ["HIRE"]]),
            action([["PASS"], ["HARVEST"], ["WATER"]]),
            action([["PASS"], ["HARVEST"], ["WATER"]]),
        )
        lane.apply(obs(0, 0, 1), self.cfg, tape[0], route=tape, route_id="A")
        lane.apply(obs(1, 0, 2), self.cfg, tape[1], route=tape, route_id="A")
        out, report = lane.apply(obs(2, 0, 3), self.cfg, tape[2], route=tape, route_id="A")
        self.assertIs(out, tape[2])
        self.assertEqual(report["reason"], "binding_drift")

    def test_future_hire_boundary_applies_current_units_then_blocks(self):
        lane = JointActorAssignment(enabled=True)
        tape = route(
            action([["PASS"]], [["HIRE"], ["HIRE"]]),
            action([["PASS"], ["HARVEST"], ["WATER"]]),
            action([["PASS"], ["HARVEST"], ["WATER"]], [["HIRE"]]),
            action([["PASS"], ["HARVEST"], ["WATER"], ["DIG"]]),
        )
        lane.apply(obs(0, 0, 1), self.cfg, tape[0], route=tape, route_id="A")
        lane.apply(obs(1, 0, 2), self.cfg, tape[1], route=tape, route_id="A")
        out2, report2 = lane.apply(obs(2, 0, 2), self.cfg, tape[2], route=tape, route_id="A")
        self.assertEqual(len(out2["hands"]), 2)
        self.assertEqual(report2["reason"], "binding_interval_end")
        out3, report3 = lane.apply(obs(3, 0, 3), self.cfg, tape[3], route=tape, route_id="A")
        self.assertIs(out3, tape[3])
        self.assertEqual(report3["reason"], "blocked_interval")

    def test_lower_logical_index_breaks_exact_score_tie(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        second = action([["PASS"], ["HARVEST"], ["HARVEST"]])
        tape = route(first, second)
        lane.apply(obs(0, 0, 1), self.cfg, first, route=tape, route_id="A")
        out, report = lane.apply(obs(1, 0, 2), self.cfg, second, route=tape, route_id="A")
        self.assertEqual(report["mapping"], [0, 1])
        self.assertEqual(out["hands"], [["PASS"], ["HARVEST"]])

    def test_malformed_route_command_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        first = action([["PASS"]], [["HIRE"], ["HIRE"]])
        second = action([["PASS"], ["HARVEST"], ["WATER"]])
        bad_route = route(first, {"farmer": ["PASS"], "hands": [["PASS"], None, ["WATER"]], "market": []})
        lane.apply(obs(0, 0, 1), self.cfg, first, route=bad_route, route_id="A")
        out, report = lane.apply(obs(1, 0, 2), self.cfg, second, route=bad_route, route_id="A")
        self.assertIs(out, second)
        self.assertEqual(report["reason"], "ambiguous_underfill")

    def test_malformed_market_limit_fails_closed(self):
        lane = JointActorAssignment(enabled=True)
        selected = action([["PASS"]], [["HIRE"]])
        out, report = lane.apply(obs(0, 0, 1), {"maxMarketOrdersPerTurn": 1.5}, selected, route=[selected], route_id="A")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "malformed_market_prefix")

    def test_uncertified_existing_mismatch_blocks_new_hire_receipt(self):
        lane = JointActorAssignment(enabled=True)
        selected = action([["PASS"], ["HARVEST"]], [["HIRE"]])
        out, report = lane.apply(obs(0, 0, 1), self.cfg, selected, route=[selected], route_id="A")
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "uncertified_hire_baseline")

    def test_farm_short_form_hand_count_is_supported(self):
        lane = JointActorAssignment(enabled=True)
        observation = {"step": 0, "day": 0, "farm": {"hands": 1}}
        selected = action([["PASS"]], [["HIRE"]])
        out, report = lane.apply(observation, self.cfg, selected, route=[selected], route_id=7)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "hire_receipt_pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
