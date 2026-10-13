# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest
from commitment_window import inspect_commitment, program_boundary


def program(n=6):
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(n)]


class RecordingController:
    """Interface-only fixture; the CLI separately consumes the actual Arlene class."""
    def __init__(self, left, right):
        self.cur = "left"
        self.R = {"left": left, "right": right}
        self.calls = []

    def _switch_ok(self, target, now):
        self.calls.append((target, now))
        return self.R[self.cur] is not self.R[target] and self.R[self.cur][:now] == self.R[target][:now]

    def act(self, *args):
        raise AssertionError("no parent action call belongs in this consumer")


class BoundaryTests(unittest.TestCase):
    def test_first_difference_is_inclusive_preaction_checkpoint(self):
        a, b = program(), program()
        b[2]["market"] = [["BUY_ANIMAL", "SHEEP", 1]]
        w = program_boundary(a, b, decision_stop=5)
        self.assertEqual((w.first_difference, w.last_equal_prefix_checkpoint), (2, 2))
        self.assertTrue(w.prefix_matches(2)); self.assertFalse(w.prefix_matches(3))
        self.assertTrue(w.can_wait_one(1)); self.assertFalse(w.can_wait_one(2))

    def test_later_equal_actions_never_restore_prefix(self):
        a, b = program(), program(); b[1]["farmer"] = ["NORTH"]
        w = program_boundary(a, b, decision_stop=5)
        self.assertEqual(a[4], b[4]); self.assertFalse(w.prefix_matches(4))

    def test_unit_and_market_boundaries_are_separate(self):
        a, b = program(), program()
        b[1]["market"] = [["HIRE"]]; b[3]["hands"] = [["PICKUP", "SHEEP"]]
        b[4]["farmer"] = ["NORTH"]
        w = program_boundary(a, b, decision_stop=5)
        self.assertEqual((w.first_market_difference, w.first_hands_difference, w.first_farmer_difference), (1, 3, 4))

    def test_market_order_and_zero_based_slot(self):
        a, b = program(), program()
        a[2]["market"] = [["SELL", "MILK", 1], ["HIRE"]]
        b[2]["market"] = [["HIRE"], ["SELL", "MILK", 1]]
        w = program_boundary(a, b, decision_stop=5)
        self.assertEqual(w.first_market_slot, 0)
        b[2]["market"] = [["SELL", "MILK", 1], ["BUY_ANIMAL", "SHEEP", 1]]
        self.assertEqual(program_boundary(a, b, decision_stop=5).first_market_slot, 1)

    def test_extra_market_order_is_a_difference(self):
        a, b = program(), program(); b[2]["market"] = [["HIRE"]]
        self.assertEqual(program_boundary(a, b, decision_stop=5).first_market_slot, 0)

    def test_only_nonexecuted_tail_difference_is_ignored(self):
        a, b = program(), program(); b[5]["market"] = [["HIRE"]]
        w = program_boundary(a, b, decision_stop=5)
        self.assertIsNone(w.first_difference); self.assertEqual(w.last_equal_prefix_checkpoint, 4)
        self.assertTrue(w.prefix_matches(4)); self.assertFalse(w.prefix_matches(5))
        self.assertFalse(w.can_wait_one(4))

    def test_same_object_matches_prefix_but_is_not_another_choice(self):
        a = program(); c = RecordingController(a, a)
        out = inspect_commitment(c, "right", 2, decision_stop=5)
        self.assertTrue(out["same_object"]); self.assertFalse(out["structural_choice_now"])
        self.assertFalse(out["can_wait_one_structurally"]); self.assertTrue(out["predicate_agrees"])

    def test_equal_distinct_programs_preserve_choice(self):
        a = program(); c = RecordingController(a, deepcopy(a))
        out = inspect_commitment(c, "right", 2, decision_stop=5)
        self.assertTrue(out["structural_choice_now"]); self.assertTrue(out["can_wait_one_structurally"])

    def test_controller_not_called_at_terminal_or_later(self):
        c = RecordingController(program(), program())
        out = inspect_commitment(c, "right", 5, decision_stop=5)
        self.assertIsNone(out["controller_accepts_now"]); self.assertEqual(c.calls, [])

    def test_invalid_ranges_or_incomplete_tails_fail_explicitly(self):
        for kwargs in ({"decision_stop": 0}, {"decision_stop": True}, {"decision_stop": 7},
                       {"decision_stop": 5, "max_steps": 4}, {"decision_stop": 5, "max_steps": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                program_boundary(program(), program(), **kwargs)
        with self.assertRaises(ValueError): program_boundary([[]], [{}], decision_stop=1)
        with self.assertRaises(ValueError): inspect_commitment(RecordingController(program(), program()), "right", -1, decision_stop=5)

    def test_read_only_consumer_and_return_isolation(self):
        a, b = program(), program(); b[2]["market"] = [["HIRE"]]
        c = RecordingController(a, b); before = deepcopy(c.R)
        out = inspect_commitment(c, "right", 2, decision_stop=5)
        self.assertEqual(c.calls, [("right", 2)]); self.assertEqual(c.cur, "left"); self.assertEqual(c.R, before)
        out["target_at_first_difference"]["market"].clear()
        self.assertEqual(b[2]["market"], [["HIRE"]])

    def test_predicate_disagreement_is_reported_not_overruled(self):
        c = RecordingController(program(), program())
        c._switch_ok = lambda target, now: False
        out = inspect_commitment(c, "right", 2, decision_stop=5)
        self.assertTrue(out["structural_choice_now"]); self.assertFalse(out["predicate_agrees"])
        self.assertEqual(c.cur, "left")

    def test_exhaustive_first_difference_positions(self):
        for first in range(6):
            a, b = program(), program(); b[first]["market"] = [["HIRE"]]
            w = program_boundary(a, b, decision_stop=5)
            for now in range(7):
                self.assertEqual(w.prefix_matches(now), now < 5 and now <= first)

    def test_fingerprints_and_witness_do_not_mutate(self):
        a, b = program(), program(); b[1]["market"] = [["HIRE"]]
        w = program_boundary(a, b, decision_stop=5); old = w.as_dict()
        a[1]["farmer"] = ["WEST"]; b[1]["market"].clear()
        self.assertEqual(w.as_dict(), old); self.assertNotEqual(w.current_sha256, w.target_sha256)


if __name__ == "__main__":
    unittest.main()
