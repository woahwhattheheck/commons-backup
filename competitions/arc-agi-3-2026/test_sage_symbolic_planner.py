from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import copy
import unittest

from sage_symbolic_planner import (
    ActionHypothesis, PlannerBudget, ReceiptVerificationError, SageEvidenceAdapter,
    SymbolicState, observation_digest, plan, verify_receipt,
)


def h(text: str) -> str:
    return sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Token:
    name: str
    x: int | None = None
    y: int | None = None
    @property
    def key(self):
        return self.name if self.x is None else f"{self.name}@{self.x},{self.y}"


@dataclass(frozen=True)
class Obs:
    frame: tuple[tuple[int, ...], ...]
    available_actions: tuple[str, ...]
    state: str = "NOT_FINISHED"
    levels_completed: int = 0
    win_levels: int = 0


@dataclass(frozen=True)
class Effect:
    digest: str
    changed_count: int = 0
    level_delta: int = 0
    terminal: str = "NOT_FINISHED"


@dataclass(frozen=True)
class Transition:
    before: Obs
    action: Token
    after: Obs
    effect: Effect


class FakeModel:
    def __init__(self, transitions=()):
        self.transitions = list(transitions)
        self.seen = {}
    def novelty(self, obs):
        return 1.0 / (1 + self.seen.get(observation_digest(obs), 0))


class GraphAdapter:
    def __init__(self, graph, start="S", model_tag="m1"):
        self.graph = graph
        self.start = start
        self._model_digest = h(model_tag)
    @property
    def model_digest(self):
        return self._model_digest
    def root_state(self):
        row = self.graph[self.start]
        return SymbolicState(h(self.start), tuple(sorted(row.get("actions", {}))), row.get("terminal", "NOT_FINISHED"), 0)
    def hypotheses(self, state):
        label = next((k for k in self.graph if h(k) == state.digest), None)
        if label is None:
            return ()
        out = []
        for action, edge in sorted(self.graph[label].get("actions", {}).items()):
            conf = edge.get("confidence", 10_000)
            out.append(ActionHypothesis(
                Token(action), action, h(label + ":" + action + ":effect"), edge.get("support", 1), edge.get("total", 1),
                conf, 10_000-conf, edge.get("changed", 10_000), edge.get("progress", 0),
                self.graph[edge["to"]].get("terminal", "NOT_FINISHED"), edge.get("novelty", 0), edge.get("risk", 0), "SYNTHETIC"
            ))
        return tuple(out)
    def simulate(self, state, hypothesis):
        label = next(k for k in self.graph if h(k) == state.digest)
        edge = self.graph[label]["actions"][hypothesis.action_key]
        target = edge["to"]
        row = self.graph[target]
        return SymbolicState(h(target), tuple(sorted(row.get("actions", {}))), row.get("terminal", "NOT_FINISHED"), state.cumulative_progress + hypothesis.progress)


class PlannerTests(unittest.TestCase):
    def test_two_step_terminal_beats_one_step_progress(self):
        graph = {
            "S": {"actions": {"ACTION1": {"to": "A", "progress": 1}, "ACTION2": {"to": "B"}}},
            "A": {"terminal": "NOT_FINISHED", "actions": {}},
            "B": {"actions": {"ACTION3": {"to": "W"}}},
            "W": {"terminal": "WIN", "actions": {}},
        }
        decision = plan(GraphAdapter(graph), actions_left=4)
        self.assertEqual(decision.selected_prefix, ("ACTION2", "ACTION3"))
        self.assertEqual(decision.receipt["selected_progress"], 0)

    def test_tie_break_is_lexical_and_deterministic(self):
        graph = {"S": {"actions": {"ACTION2": {"to": "B"}, "ACTION1": {"to": "A"}}}, "A": {"actions": {}}, "B": {"actions": {}}}
        d1 = plan(GraphAdapter(graph), actions_left=1)
        d2 = plan(GraphAdapter(graph), actions_left=1)
        self.assertEqual(d1.selected_prefix, ("ACTION1",))
        self.assertEqual(d1.receipt_bytes(), d2.receipt_bytes())
        self.assertEqual(d1.receipt["candidate_order"], ["ACTION1", "ACTION2"])

    def test_real_budget_caps_depth_and_simulation_spends_zero(self):
        graph = {
            "S": {"actions": {"ACTION1": {"to": "A"}}},
            "A": {"actions": {"ACTION2": {"to": "B"}}},
            "B": {"actions": {"ACTION3": {"to": "W"}}},
            "W": {"terminal": "WIN", "actions": {}},
        }
        d = plan(GraphAdapter(graph), actions_left=2, budget=PlannerBudget(max_depth=8, max_width=4, max_nodes=20, max_plan_actions=8))
        self.assertLessEqual(d.receipt["planned_real_actions"], 2)
        self.assertEqual(d.receipt["real_action_ceiling"], 2)
        self.assertEqual(d.receipt["real_actions_spent_by_simulation"], 0)
        self.assertGreater(d.receipt["simulated_nodes"], 0)
        self.assertNotEqual(d.receipt["selected_prefix"], ["ACTION1", "ACTION2", "ACTION3"])

    def test_node_budget_is_hard(self):
        graph = {"S": {"actions": {f"ACTION{i}": {"to": f"N{i}"} for i in range(1, 7)}}}
        graph.update({f"N{i}": {"actions": {}} for i in range(1, 7)})
        d = plan(GraphAdapter(graph), actions_left=4, budget=PlannerBudget(max_depth=4, max_width=6, max_nodes=3, max_plan_actions=4))
        self.assertEqual(d.receipt["simulated_nodes"], 3)

    def test_loop_is_penalized_and_not_expanded_forever(self):
        graph = {
            "S": {"actions": {"ACTION1": {"to": "S"}, "ACTION2": {"to": "A"}}},
            "A": {"actions": {}},
        }
        d = plan(GraphAdapter(graph), actions_left=10, budget=PlannerBudget(max_depth=10, max_width=3, max_nodes=50, max_plan_actions=10))
        self.assertEqual(d.selected_prefix, ("ACTION2",))
        self.assertLess(d.receipt["simulated_nodes"], 10)

    def test_low_confidence_increases_risk(self):
        graph = {
            "S": {"actions": {"ACTION1": {"to": "A", "confidence": 2_000, "risk": 8_000}, "ACTION2": {"to": "B", "confidence": 9_000, "risk": 1_000}}},
            "A": {"actions": {}}, "B": {"actions": {}}
        }
        d = plan(GraphAdapter(graph), actions_left=1)
        self.assertEqual(d.selected_prefix, ("ACTION2",))
        self.assertEqual(d.receipt["risk_bps"], 1_000)

    def test_receipt_tamper_fails(self):
        graph = {"S": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        adapter = GraphAdapter(graph)
        d = plan(adapter, actions_left=1)
        tampered = copy.deepcopy(d.receipt)
        tampered["selected_score"] += 1
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(adapter, tampered, actions_left=1)

    def test_receipt_state_or_model_drift_fails(self):
        graph = {"S": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        d = plan(GraphAdapter(graph, model_tag="m1"), actions_left=1)
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(GraphAdapter(graph, model_tag="m2"), d.receipt, actions_left=1)
        changed = {"X": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(GraphAdapter(changed, start="X", model_tag="m1"), d.receipt, actions_left=1)

    def test_receipt_budget_mismatch_fails(self):
        graph = {"S": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        adapter = GraphAdapter(graph)
        d = plan(adapter, actions_left=2)
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(adapter, d.receipt, actions_left=1)

    def test_receipt_field_injection_fails(self):
        graph = {"S": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        adapter = GraphAdapter(graph)
        d = plan(adapter, actions_left=1)
        injected = dict(d.receipt, surprise=True)
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(adapter, injected, actions_left=1)

    def test_exact_int_validation_rejects_bool(self):
        graph = {"S": {"actions": {"ACTION1": {"to": "A"}}}, "A": {"actions": {}}}
        with self.assertRaises(ValueError):
            plan(GraphAdapter(graph), actions_left=True)
        with self.assertRaises(ValueError):
            PlannerBudget(max_nodes=True).validate()


class SageAdapterTests(unittest.TestCase):
    def candidates(self, obs):
        return tuple(Token(name) for name in sorted(obs.available_actions))

    def test_exact_observed_successor_is_reused_without_pixel_invention(self):
        before = Obs(((0, 1), (0, 0)), ("ACTION1",))
        after = Obs(((0, 0), (0, 1)), ("ACTION1",), levels_completed=1)
        t = Transition(before, Token("ACTION1"), after, Effect(h("move"), 2, 1))
        adapter = SageEvidenceAdapter(FakeModel([t]), before, candidate_factory=self.candidates)
        root = adapter.root_state()
        hyp, = adapter.hypotheses(root)
        self.assertEqual(hyp.evidence_scope, "EXACT")
        self.assertEqual(hyp.successor_observation_digest, observation_digest(after))
        successor = adapter.simulate(root, hyp)
        self.assertEqual(successor.observation_digest, observation_digest(after))
        self.assertEqual(successor.cumulative_progress, 1)

    def test_unseen_effect_stays_abstract(self):
        obs = Obs(((0, 1), (0, 0)), ("ACTION9",))
        adapter = SageEvidenceAdapter(FakeModel([]), obs, candidate_factory=self.candidates)
        root = adapter.root_state()
        hyp, = adapter.hypotheses(root)
        self.assertEqual(hyp.evidence_scope, "UNOBSERVED")
        self.assertIsNone(hyp.successor_observation)
        successor = adapter.simulate(root, hyp)
        self.assertIsNone(successor.observation)
        self.assertIsNone(successor.observation_digest)

    def test_model_digest_is_order_invariant_but_content_bound(self):
        a = Obs(((0, 1),), ("ACTION1", "ACTION2"))
        b = Obs(((1, 0),), ("ACTION1", "ACTION2"))
        c = Obs(((2, 0),), ("ACTION1", "ACTION2"))
        t1 = Transition(a, Token("ACTION1"), b, Effect(h("e1"), 2))
        t2 = Transition(a, Token("ACTION2"), c, Effect(h("e2"), 2))
        m1 = SageEvidenceAdapter(FakeModel([t1, t2]), a, candidate_factory=self.candidates)
        m2 = SageEvidenceAdapter(FakeModel([t2, t1]), a, candidate_factory=self.candidates)
        self.assertEqual(m1.model_digest, m2.model_digest)
        changed = Transition(a, Token("ACTION2"), c, Effect(h("e3"), 2))
        m3 = SageEvidenceAdapter(FakeModel([t1, changed]), a, candidate_factory=self.candidates)
        self.assertNotEqual(m1.model_digest, m3.model_digest)

    def test_scene_fallback_and_global_contradiction_raise_risk(self):
        # Two exact-scene ACTION1 rows agree on local effect; three other-scene rows make
        # a different effect globally modal.  Local evidence must remain selected but risk
        # must reflect the contradiction.
        a = Obs(((0, 1), (0, 0)), ("ACTION1",))
        a2 = Obs(((1, 0), (0, 0)), ("ACTION1",))  # same shape/hist/action scene class
        b = Obs(((0, 0), (0, 1)), ("ACTION1",))
        other = Obs(((2, 2), (0, 0)), ("ACTION1",))
        other_after = Obs(((3, 3), (0, 0)), ("ACTION1",))
        local_effect = Effect(h("local"), 2)
        global_effect = Effect(h("global"), 2)
        transitions = [
            Transition(a2, Token("ACTION1"), b, local_effect),
            Transition(a2, Token("ACTION1"), b, local_effect),
            Transition(other, Token("ACTION1"), other_after, global_effect),
            Transition(other, Token("ACTION1"), other_after, global_effect),
            Transition(other, Token("ACTION1"), other_after, global_effect),
        ]
        adapter = SageEvidenceAdapter(FakeModel(transitions), a, candidate_factory=self.candidates)
        hyp, = adapter.hypotheses(adapter.root_state())
        self.assertEqual(hyp.evidence_scope, "SCENE")
        self.assertEqual(hyp.effect_digest, local_effect.digest)
        self.assertGreaterEqual(hyp.risk_bps, 2_500)

    def test_multiple_modal_successor_bytes_remain_abstract(self):
        a = Obs(((0, 1),), ("ACTION1",))
        b = Obs(((1, 0),), ("ACTION1",))
        c = Obs(((1, 1),), ("ACTION1",))
        effect = Effect(h("same-effect"), 1)
        adapter = SageEvidenceAdapter(FakeModel([
            Transition(a, Token("ACTION1"), b, effect),
            Transition(a, Token("ACTION1"), c, effect),
        ]), a, candidate_factory=self.candidates)
        hyp, = adapter.hypotheses(adapter.root_state())
        self.assertIsNone(hyp.successor_observation_digest)
        self.assertIsNone(hyp.successor_observation)

    def test_sage_receipt_rejects_model_drift(self):
        a = Obs(((0, 1),), ("ACTION1",))
        b = Obs(((1, 0),), ("ACTION1",))
        t = Transition(a, Token("ACTION1"), b, Effect(h("e1"), 1))
        adapter = SageEvidenceAdapter(FakeModel([t]), a, candidate_factory=self.candidates)
        d = plan(adapter, actions_left=2)
        self.assertEqual(verify_receipt(adapter, d.receipt, actions_left=2), "VERIFIED_OFFLINE")
        changed = SageEvidenceAdapter(FakeModel([t, Transition(b, Token("ACTION1"), a, Effect(h("e2"), 1))]), a, candidate_factory=self.candidates)
        with self.assertRaises(ReceiptVerificationError):
            verify_receipt(changed, d.receipt, actions_left=2)

    def test_observation_digest_binds_action_space_and_state(self):
        base = Obs(((0, 1),), ("ACTION1",))
        action_changed = Obs(((0, 1),), ("ACTION1", "ACTION2"))
        terminal_changed = Obs(((0, 1),), ("ACTION1",), state="WIN")
        self.assertNotEqual(observation_digest(base), observation_digest(action_changed))
        self.assertNotEqual(observation_digest(base), observation_digest(terminal_changed))


if __name__ == "__main__":
    unittest.main()
