from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import unittest

import _sage_symbolic_planner_core as predecessor
from sage_symbolic_planner import (
    REACHABILITY_POLICY,
    SageEvidenceAdapter,
    observation_digest,
    plan,
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


class ReachabilityBoundaryTests(unittest.TestCase):
    def candidates(self, obs):
        return tuple(Token(name) for name in sorted(obs.available_actions))

    def test_scene_fallback_cannot_promote_other_predecessor_win(self):
        current = Obs(((0, 1), (0, 0)), ("ACTION1",))
        evidence_before = Obs(((1, 0), (0, 0)), ("ACTION1",))
        foreign_win = Obs(((0, 0), (1, 0)), ("ACTION1",), state="WIN", levels_completed=1)
        transition = Transition(
            evidence_before,
            Token("ACTION1"),
            foreign_win,
            Effect(h("scene-win"), 2, 1, "WIN"),
        )
        adapter = SageEvidenceAdapter(FakeModel([transition]), current, candidate_factory=self.candidates)
        hypothesis, = adapter.hypotheses(adapter.root_state())

        self.assertEqual(hypothesis.evidence_scope, "SCENE")
        self.assertEqual(hypothesis.terminal, "NOT_FINISHED")
        self.assertEqual(hypothesis.progress, 0)
        self.assertEqual(hypothesis.novelty_bps, 0)
        self.assertIsNone(hypothesis.successor_observation_digest)
        self.assertIsNone(hypothesis.successor_observation)
        successor = adapter.simulate(adapter.root_state(), hypothesis)
        self.assertIsNone(successor.observation)
        self.assertEqual(successor.terminal, "NOT_FINISHED")
        self.assertEqual(successor.cumulative_progress, 0)

    def test_global_fallback_cannot_promote_other_predecessor_win(self):
        current = Obs(((9, 9), (9, 9)), ("ACTION1",))
        evidence_before = Obs(((1, 0), (0, 0)), ("ACTION1",))
        foreign_win = Obs(((0, 0), (1, 0)), ("ACTION1",), state="WIN", levels_completed=1)
        transition = Transition(
            evidence_before,
            Token("ACTION1"),
            foreign_win,
            Effect(h("global-win"), 2, 1, "WIN"),
        )
        adapter = SageEvidenceAdapter(FakeModel([transition]), current, candidate_factory=self.candidates)
        hypothesis, = adapter.hypotheses(adapter.root_state())

        self.assertEqual(hypothesis.evidence_scope, "GLOBAL")
        self.assertEqual(hypothesis.terminal, "NOT_FINISHED")
        self.assertEqual(hypothesis.progress, 0)
        self.assertEqual(hypothesis.novelty_bps, 0)
        self.assertIsNone(hypothesis.successor_observation)

    def test_exact_predecessor_still_carries_observed_reachability(self):
        current = Obs(((0, 1),), ("ACTION1",))
        exact_win = Obs(((1, 0),), ("ACTION1",), state="WIN", levels_completed=1)
        transition = Transition(
            current,
            Token("ACTION1"),
            exact_win,
            Effect(h("exact-win"), 2, 1, "WIN"),
        )
        adapter = SageEvidenceAdapter(FakeModel([transition]), current, candidate_factory=self.candidates)
        hypothesis, = adapter.hypotheses(adapter.root_state())

        self.assertEqual(hypothesis.evidence_scope, "EXACT")
        self.assertEqual(hypothesis.terminal, "WIN")
        self.assertEqual(hypothesis.progress, 1)
        self.assertEqual(hypothesis.successor_observation_digest, observation_digest(exact_win))
        self.assertIs(hypothesis.successor_observation, exact_win)

    def test_foreign_win_no_longer_beats_exact_progress(self):
        current = Obs(((9, 9), (9, 9)), ("ACTION1", "ACTION2"))
        foreign_before = Obs(((1, 0), (0, 0)), ("ACTION1", "ACTION2"))
        foreign_win = Obs(
            ((0, 1), (0, 0)),
            ("ACTION1", "ACTION2"),
            state="WIN",
            levels_completed=1,
        )
        exact_progress = Obs(
            ((9, 9), (9, 8)),
            ("ACTION1", "ACTION2"),
            levels_completed=1,
        )
        transitions = [
            Transition(
                foreign_before,
                Token("ACTION1"),
                foreign_win,
                Effect(h("foreign-win"), 1, 1, "WIN"),
            ),
            Transition(
                current,
                Token("ACTION2"),
                exact_progress,
                Effect(h("exact-progress"), 1, 1, "NOT_FINISHED"),
            ),
        ]
        adapter = SageEvidenceAdapter(FakeModel(transitions), current, candidate_factory=self.candidates)
        decision = plan(adapter, actions_left=1)
        self.assertEqual(decision.selected_prefix, ("ACTION2",))

    def test_policy_is_bound_into_model_digest(self):
        current = Obs(((0, 1),), ("ACTION1",))
        after = Obs(((1, 0),), ("ACTION1",))
        transition = Transition(current, Token("ACTION1"), after, Effect(h("move"), 1))
        model = FakeModel([transition])
        public = SageEvidenceAdapter(model, current, candidate_factory=self.candidates)
        old = predecessor.SageEvidenceAdapter(model, current, candidate_factory=self.candidates)

        self.assertEqual(REACHABILITY_POLICY, "exact-predecessor-concrete-reachability/v1")
        self.assertNotEqual(public.model_digest, old.model_digest)
        public_again = SageEvidenceAdapter(model, current, candidate_factory=self.candidates)
        self.assertEqual(public.model_digest, public_again.model_digest)


if __name__ == "__main__":
    unittest.main()
