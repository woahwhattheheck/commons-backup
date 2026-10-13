from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from dataclasses import dataclass

HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import adapter
from benchmark import run, suite
from mock_env import SwitchDoorEnv
from receipts import canonical_json, compile_receipt, verify_receipt
from sage import (
    ActionToken,
    Observation,
    Policy,
    SAGEAgent,
    ScenePrecondition,
    SkillLibrary,
    Transition,
    WorldModel,
    animation_signature,
    changed_cells,
    connected_components,
    effect_signature,
    grid_digest,
    scene_signature,
    validate_grid,
)


def grid(rows):
    return validate_grid(rows)


class GridTests(unittest.TestCase):
    def test_validate_grid(self):
        self.assertEqual(validate_grid([[0, 1], [2, 3]])[1][1], 3)

    def test_reject_bool(self):
        with self.assertRaises(ValueError):
            validate_grid([[False]])

    def test_reject_ragged(self):
        with self.assertRaises(ValueError):
            validate_grid([[0], [0, 1]])

    def test_reject_range(self):
        with self.assertRaises(ValueError):
            validate_grid([[16]])

    def test_digest_changes(self):
        self.assertNotEqual(grid_digest(grid([[0, 1]])), grid_digest(grid([[1, 0]])))

    def test_components(self):
        comps = connected_components(grid([[1, 0, 2], [1, 0, 2], [0, 2, 2]]))
        self.assertEqual([(c.color, c.area) for c in comps], [(1, 2), (2, 4)])
        self.assertEqual(comps[0].centroid, (0, 0))


class ObservationTests(unittest.TestCase):
    def test_multiple_frames_retained(self):
        f1 = grid([[0, 1], [0, 0]])
        f2 = grid([[0, 0], [0, 1]])
        obs = Observation((f1, f2), ("ACTION1",))
        self.assertEqual(obs.frame, f2)
        self.assertNotEqual(animation_signature(obs), animation_signature(Observation((f2,), ("ACTION1",))))

    def test_duplicate_actions_rejected(self):
        with self.assertRaises(ValueError):
            Observation((grid([[0]]),), ("ACTION1", "ACTION1"))

    def test_changed_cells(self):
        self.assertEqual(changed_cells(grid([[0, 1]]), grid([[1, 1]])), ((0, 0),))

    def test_scene_signature_order_invariant_actions(self):
        f = grid([[0, 1], [0, 0]])
        a = Observation((f,), ("ACTION2", "ACTION1"))
        b = Observation((f,), ("ACTION1", "ACTION2"))
        self.assertEqual(scene_signature(a), scene_signature(b))


class ActionTests(unittest.TestCase):
    def test_coordinate_pair_required(self):
        with self.assertRaises(ValueError):
            ActionToken("ACTION6", 1, None)

    def test_coordinate_bound(self):
        with self.assertRaises(ValueError):
            ActionToken("ACTION6", 64, 1)

    def test_candidate_actions_include_component_clicks(self):
        obs = Observation((grid([[0, 3, 0], [0, 3, 0], [0, 0, 0]]),), ("ACTION1", "ACTION6"))
        actions = Policy.candidate_actions(obs)
        self.assertIn(ActionToken("ACTION6", 1, 0), actions)
        self.assertIn(ActionToken("ACTION1"), actions)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.before = Observation((grid([[0, 2], [0, 0]]),), ("ACTION1", "ACTION2"))
        self.after = Observation((grid([[0, 0], [0, 2]]),), ("ACTION1", "ACTION2"))

    def test_effect_change(self):
        e = effect_signature(self.before, self.after)
        self.assertEqual(e.changed_count, 2)
        self.assertEqual(e.level_delta, 0)

    def test_world_model_observe(self):
        model = WorldModel()
        t = Transition.build(self.before, ActionToken("ACTION1"), self.after)
        model.observe(t)
        self.assertEqual(model.stats(self.before, ActionToken("ACTION1")).total, 1)
        self.assertEqual(model.stats(self.before, ActionToken("ACTION1")).change_rate, 1.0)

    def test_unavailable_transition_rejected(self):
        with self.assertRaises(ValueError):
            Transition.build(self.before, ActionToken("ACTION3"), self.after)

    def test_policy_prefers_untried(self):
        model = WorldModel()
        t = Transition.build(self.before, ActionToken("ACTION1"), self.before)
        for _ in range(4):
            model.observe(t)
        decision = Policy(model).choose(self.before, actions_left=20)
        self.assertEqual(decision.action.name, "ACTION2")
        self.assertEqual(decision.mode, "EXPLORE")

    def test_policy_penalizes_loop(self):
        model = WorldModel()
        policy = Policy(model)
        for _ in range(3):
            policy.record_choice(ActionToken("ACTION2"))
        d = policy.choose(self.before, actions_left=20)
        self.assertEqual(d.action.name, "ACTION1")

    def test_zero_budget_rejected(self):
        with self.assertRaises(ValueError):
            Policy(WorldModel()).choose(self.before, actions_left=0)


class SkillTests(unittest.TestCase):
    def make_trace(self):
        a = Observation((grid([[2, 0], [0, 6]]),), ("ACTION1", "ACTION2"), levels_completed=0)
        b = Observation((grid([[0, 2], [0, 6]]),), ("ACTION1", "ACTION2"), levels_completed=0)
        c = Observation((grid([[0, 0], [0, 2]]),), ("ACTION1", "ACTION2"), state="WIN", levels_completed=1, win_levels=1)
        return [Transition.build(a, ActionToken("ACTION1"), b), Transition.build(b, ActionToken("ACTION2"), c)]

    def test_learn_success_skill(self):
        lib = SkillLibrary()
        skill = lib.learn_success_suffix(self.make_trace())
        self.assertIsNotNone(skill)
        self.assertEqual([a.name for a in skill.actions], ["ACTION1", "ACTION2"])
        self.assertEqual(skill.confidence, 1.0)

    def test_non_success_not_learned(self):
        trace = self.make_trace()[:1]
        self.assertIsNone(SkillLibrary().learn_success_suffix(trace))

    def test_support_folds(self):
        lib = SkillLibrary()
        lib.learn_success_suffix(self.make_trace())
        skill = lib.learn_success_suffix(self.make_trace())
        self.assertEqual(skill.support, 2)

    def test_precondition_mismatch(self):
        trace = self.make_trace()
        skill = SkillLibrary().learn_success_suffix(trace)
        different = Observation((grid([[2, 7], [0, 6]]),), ("ACTION1", "ACTION2"))
        self.assertFalse(skill.precondition.matches(different))


class MockEnvironmentTests(unittest.TestCase):
    def test_action_mapping_scrambled(self):
        a = SwitchDoorEnv(0).semantic_by_action
        b = SwitchDoorEnv(1).semantic_by_action
        self.assertNotEqual(a, b)

    def test_click_opens_with_animation_when_adjacent(self):
        env = SwitchDoorEnv(0)
        env.agent = (1, 3)
        out = env.step(ActionToken("ACTION6", *env.switch))
        self.assertTrue(env.door_open)
        self.assertEqual(len(out.frames), 3)

    def test_benchmark_succeeds_some_seed(self):
        # This is a research benchmark, not a claim of ARC public/private score.
        row = run(0, max_actions=80)
        self.assertTrue(row["won"])
        self.assertTrue(row["receipt_ok"])
        self.assertLessEqual(row["actions"], 80)

    def test_seed5_covered_target_regression(self):
        # Seed 5 previously reached the goal/switch target cell, visually covered the
        # target with the avatar, then forgot which object should receive INTERACT.
        # Preserve that exact action-permutation failure as a permanent regression.
        row = run(5, max_actions=80)
        self.assertTrue(row["won"])
        self.assertTrue(row["receipt_ok"])
        self.assertLess(row["actions"], 30)

    def test_suite_deterministic(self):
        a = suite(range(3), max_actions=80)
        b = suite(range(3), max_actions=80)
        self.assertEqual(a, b)


class ReceiptTests(unittest.TestCase):
    def trace(self):
        env = SwitchDoorEnv(3)
        agent = SAGEAgent()
        obs = env.reset()
        for step in range(8):
            d = agent.decide(obs, actions_left=20 - step)
            after = env.step(d.action)
            agent.learn(obs, d, after)
            obs = after
        return agent.trace

    def test_receipt_verifies(self):
        r = compile_receipt(self.trace(), agent_revision="abc", source_refs={"toolkit": "official"})
        self.assertTrue(verify_receipt(r))

    def test_receipt_tamper_fails(self):
        r = compile_receipt(self.trace(), agent_revision="abc", source_refs={})
        r["steps"][0]["state"] = "WIN"
        self.assertFalse(verify_receipt(r))

    def test_authority_escalation_fails(self):
        r = compile_receipt(self.trace(), agent_revision="abc", source_refs={})
        r["external_authority"]["prize_or_revenue"] = True
        self.assertFalse(verify_receipt(r))

    def test_non_ascii_canonicalized(self):
        self.assertEqual(canonical_json({"x": "é"}), b'{"x":"\\u00e9"}')


@dataclass
class Raw:
    frame: object
    available_actions: object
    state: object = "NOT_FINISHED"
    levels_completed: int = 0
    win_levels: int = 1


class AdapterTests(unittest.TestCase):
    def test_normalize_single_grid(self):
        raw = Raw([[0, 1], [2, 0]], ["ACTION1"])
        obs = adapter.normalize_frame_data(raw)
        self.assertEqual(len(obs.frames), 1)

    def test_normalize_multi_frame(self):
        raw = Raw([[[0, 1]], [[1, 0]]], ["ACTION1"])
        obs = adapter.normalize_frame_data(raw)
        self.assertEqual(len(obs.frames), 2)
        self.assertEqual(obs.frame[0][0], 1)

    def test_missing_frame_fails(self):
        class Bad:
            available_actions = ["ACTION1"]
        with self.assertRaises(ValueError):
            adapter.normalize_frame_data(Bad())

    def test_toolkit_not_required_on_import(self):
        self.assertTrue(callable(adapter.normalize_frame_data))


class AgentTests(unittest.TestCase):
    def test_learn_records_trace(self):
        env = SwitchDoorEnv(5)
        agent = SAGEAgent()
        obs = env.reset()
        d = agent.decide(obs, actions_left=20)
        nxt = env.step(d.action)
        agent.learn(obs, d, nxt)
        self.assertEqual(len(agent.trace), 1)
        self.assertEqual(len(agent.model.transitions), 1)

    def test_reset_preserves_model(self):
        env = SwitchDoorEnv(5)
        agent = SAGEAgent()
        obs = env.reset()
        d = agent.decide(obs, actions_left=20)
        nxt = env.step(d.action)
        agent.learn(obs, d, nxt)
        agent.reset_episode(preserve_knowledge=True)
        self.assertEqual(len(agent.trace), 0)
        self.assertEqual(len(agent.model.transitions), 1)

    def test_hard_reset(self):
        env = SwitchDoorEnv(5)
        agent = SAGEAgent()
        obs = env.reset()
        d = agent.decide(obs, actions_left=20)
        nxt = env.step(d.action)
        agent.learn(obs, d, nxt)
        agent.reset_episode(preserve_knowledge=False)
        self.assertEqual(len(agent.model.transitions), 0)


if __name__ == "__main__":
    unittest.main()
