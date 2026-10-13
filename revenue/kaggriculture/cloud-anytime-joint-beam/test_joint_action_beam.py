# SPDX-License-Identifier: Apache-2.0
import copy
import unittest

from joint_action_beam import (
    BeamConfig,
    propose_worker_action,
    replace_worker_actions,
    search_joint_actions,
    worker_actions,
)


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)
        self.last = 0
    def __call__(self):
        try:
            self.last = next(self.values)
        except StopIteration:
            self.last += 1
        return self.last


def transition(state, idx, action):
    """Tiny sequential resource model: TAKE consumes shared stock; MOVE gains value."""
    out = copy.deepcopy(state)
    op = action[0]
    if op == "PASS":
        return out
    if op == "TAKE":
        item = action[1]
        if out["stock"].get(item, 0) <= 0:
            return None
        out["stock"][item] -= 1
        out["held"][idx] = out["held"].get(idx, 0) + 1
        return out
    if op == "MOVE":
        out["travel"][idx] = max(0, out["travel"].get(idx, 0) - 1)
        return out
    return None


def scorer(state, actions):
    return 100 * sum(state["held"].values()) - 5 * sum(state["travel"].values())


class BeamTests(unittest.TestCase):
    def base(self, n=2):
        return {"stock": {"W": 1}, "held": {}, "travel": {i: 2 for i in range(n)}}

    def test_expired_deadline_returns_exact_canonical(self):
        canonical = (["MOVE"], ["PASS"])
        result = search_joint_actions(
            self.base(), canonical,
            lambda *_: (["TAKE", "W"],), transition, scorer,
            config=BeamConfig(width=24, depth=4, budget_ns=0),
            now_ns=lambda: 10,
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertEqual("deadline-before-search", result.reason)

    def test_shared_resource_conflict_is_pruned_sequentially(self):
        canonical = (["PASS"], ["PASS"])
        result = search_joint_actions(
            self.base(), canonical,
            lambda state, idx, base: (["TAKE", "W"], ["PASS"]),
            transition, scorer,
            config=BeamConfig(width=24, depth=4, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertFalse(result.used_fallback)
        self.assertEqual(1, sum(a == ["TAKE", "W"] for a in result.actions))
        self.assertGreater(result.pruned_illegal, 0)

    def test_noncanonical_prefix_prunes_canonical_text_resource_conflict(self):
        canonical = (["PASS"], ["TAKE", "W"])
        # Token-count greedy would keep (TAKE W, TAKE W) if the second TAKE were
        # retained as a no-op after an alternative prefix consumed the stock.
        def greedy(state, actions):
            return 10 * sum(1 for a in actions if a and a[0] == "TAKE") + scorer(state, actions)
        result = search_joint_actions(
            self.base(), canonical,
            lambda state, idx, base: (["TAKE", "W"], ["PASS"]),
            transition, greedy,
            config=BeamConfig(width=24, depth=4, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertFalse(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertGreater(result.pruned_illegal, 0)
        self.assertNotEqual((["TAKE", "W"], ["TAKE", "W"]), result.actions)

    def test_deterministic_tie_keeps_canonical(self):
        canonical = (["PASS"],)
        result = search_joint_actions(
            self.base(1), canonical,
            lambda *_: (["MOVE"], ["PASS"]),
            lambda state, idx, action: copy.deepcopy(state),
            lambda state, actions: 0,
            config=BeamConfig(width=24, depth=4, budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertEqual(canonical, result.actions)

    def test_width_depth_and_candidate_family_are_hard_bounded(self):
        canonical = (["PASS"], ["PASS"], ["MOVE"], ["PASS"], ["MOVE"])
        result = search_joint_actions(
            self.base(5), canonical,
            lambda *_: (["PASS"], ["MOVE"], ["TAKE", "W"], ["BAD"], ["BAD2"]),
            transition, scorer,
            config=BeamConfig(width=2, depth=2, max_candidates=3,
                              budget_ns=1_000_000_000),
            now_ns=FakeClock(range(10000)),
        )
        self.assertLessEqual(result.frontier_peak, 2)
        self.assertEqual(2, result.searched_depth)
        self.assertEqual(canonical[2:], result.actions[2:])
        self.assertLessEqual(result.expanded, 1 * 3 + 2 * 3)

    def test_callback_failure_fails_closed_with_completed_depth(self):
        canonical = (["PASS"], ["PASS"])
        calls = {"n": 0}
        def provider(*_):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("boom")
            return (["PASS"],)
        result = search_joint_actions(
            self.base(), canonical, provider, transition, scorer,
            config=BeamConfig(budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertEqual("callback-error", result.reason)
        self.assertEqual(1, result.searched_depth)

    def test_only_worker_fields_change(self):
        base = {
            "farmer": ["NORTH"],
            "hands": [["PASS"]],
            "market": [["SELL", "WHEAT", 2], ["BUY_PRODUCT", "WHEAT", 1]],
            "hire": 1,
            "buyLand": 0,
        }
        units = worker_actions(base, hand_count=2)
        self.assertEqual((["NORTH"], ["PASS"], ["PASS"]), units)
        changed = replace_worker_actions(base, (["SOUTH"], ["WEST"], ["PASS"]))
        self.assertEqual(base["market"], changed["market"])
        self.assertEqual(base["hire"], changed["hire"])
        self.assertEqual(base["buyLand"], changed["buyLand"])
        self.assertEqual(["SOUTH"], changed["farmer"])
        self.assertEqual([["WEST"], ["PASS"]], changed["hands"])

    def test_completed_canonical_choice_preserves_exact_action_shape(self):
        base = {
            "farmer": ["NORTH"], "hands": [],
            "market": [["SELL", "WHEAT", 2]], "hire": 0, "buyLand": 0,
        }
        proposed, result = propose_worker_action(
            base, self.base(3), lambda *_: (["PASS"],),
            lambda state, idx, action: copy.deepcopy(state),
            lambda state, actions: 0,
            hand_count=3,
            config=BeamConfig(budget_ns=1_000_000_000),
            now_ns=FakeClock(range(1000)),
        )
        self.assertFalse(result.used_fallback)
        self.assertEqual(base, proposed)
        self.assertEqual([], proposed["hands"])

    def test_full_action_fallback_is_byte_semantic_identity(self):
        base = {
            "farmer": ["NORTH"], "hands": [["PASS"]],
            "market": [["SELL", "WHEAT", 2]], "hire": 0, "buyLand": 0,
        }
        proposed, result = propose_worker_action(
            base, self.base(), lambda *_: (["MOVE"],), transition, scorer,
            config=BeamConfig(budget_ns=0), now_ns=lambda: 99,
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(base, proposed)
        self.assertIsNot(base, proposed)


class ManualClock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        return self.value
    def advance(self, amount):
        self.value += amount


class DeadlineBarrierTests(unittest.TestCase):
    def test_last_expansion_transition_overrun_fails_closed(self):
        clock = ManualClock()
        canonical = (["PASS"],)
        def slow_transition(state, idx, action):
            out = copy.deepcopy(state)
            if action == ["GAIN"]:
                out["value"] += 1
                clock.advance(11)
            return out
        result = search_joint_actions(
            {"value": 0}, canonical,
            lambda *_: (["GAIN"],), slow_transition,
            lambda state, actions: state["value"],
            config=BeamConfig(width=4, depth=1, budget_ns=10),
            now_ns=clock,
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertEqual("deadline-during-search", result.reason)

    def test_final_scorer_overrun_fails_closed(self):
        clock = ManualClock()
        canonical = (["PASS"],)
        calls = {"n": 0}
        def slow_final_score(state, actions):
            calls["n"] += 1
            if calls["n"] == 4:
                clock.advance(11)
            return state["value"]
        def gain_transition(state, idx, action):
            out = copy.deepcopy(state)
            if action == ["GAIN"]:
                out["value"] += 1
            return out
        result = search_joint_actions(
            {"value": 0}, canonical,
            lambda *_: (["GAIN"],), gain_transition, slow_final_score,
            config=BeamConfig(width=4, depth=1, budget_ns=10),
            now_ns=clock,
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertEqual("deadline-during-finalization", result.reason)

    def test_last_suffix_transition_overrun_fails_closed(self):
        clock = ManualClock()
        canonical = (["PASS"], ["SLOW"])
        def slow_suffix_transition(state, idx, action):
            out = copy.deepcopy(state)
            if action == ["GAIN"]:
                out["armed"] = True
                out["value"] = -1  # keep canonical finalist first
            if action == ["SLOW"] and out.get("armed"):
                out["value"] = 10
                clock.advance(11)  # changed finalist is last and becomes best
            return out
        result = search_joint_actions(
            {"value": 0, "armed": False}, canonical,
            lambda *_: (["GAIN"],), slow_suffix_transition,
            lambda state, actions: state["value"],
            config=BeamConfig(width=4, depth=1, budget_ns=10),
            now_ns=clock,
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(canonical, result.actions)
        self.assertEqual("deadline-during-finalization", result.reason)


if __name__ == "__main__":
    unittest.main()
