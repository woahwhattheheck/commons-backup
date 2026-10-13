"""Evidence model and generalized skill induction for SAGE."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import log2
from typing import Iterable, Sequence

from sage_core import (
    ActionToken, EffectSignature, Grid, Observation, Point, Transition,
    connected_components, grid_digest, infer_background_color, scene_signature, trace_digest,
)

@dataclass
class EffectStats:
    total: int = 0
    effect_counts: Counter[str] = field(default_factory=Counter)
    changed_total: int = 0
    progress_total: int = 0
    terminal_wins: int = 0

    def add(self, effect: EffectSignature) -> None:
        self.total += 1
        self.effect_counts[effect.digest] += 1
        self.changed_total += int(effect.changed_count > 0)
        self.progress_total += max(0, effect.level_delta)
        self.terminal_wins += int(effect.terminal == "WIN")

    @property
    def entropy(self) -> float:
        if not self.total:
            return 0.0
        out = 0.0
        for count in self.effect_counts.values():
            p = count / self.total
            out -= p * log2(p)
        return out

    @property
    def confidence(self) -> float:
        if not self.total:
            return 0.0
        return max(self.effect_counts.values()) / self.total

    @property
    def change_rate(self) -> float:
        return self.changed_total / self.total if self.total else 0.0

    @property
    def progress_rate(self) -> float:
        return self.progress_total / self.total if self.total else 0.0


class WorldModel:
    """Evidence model keyed by generalized scene class and abstract action name.

    Complex coordinates are deliberately pooled under the action name for global action
    semantics and separately tracked by coordinate bucket.  This yields transfer across
    levels while retaining enough locality for click-like actions.
    """

    def __init__(self) -> None:
        self._scene_action: dict[tuple[str, str], EffectStats] = defaultdict(EffectStats)
        self._global_action: dict[str, EffectStats] = defaultdict(EffectStats)
        self._coordinate_action: dict[tuple[str, int, int], EffectStats] = defaultdict(EffectStats)
        self._motion_votes: dict[str, Counter[Point]] = defaultdict(Counter)
        self._mobile_color_votes: Counter[int] = Counter()
        self.transitions: list[Transition] = []
        self.seen_frames: Counter[str] = Counter()

    @staticmethod
    def _infer_unit_motion(before: Grid, after: Grid) -> tuple[int, Point] | None:
        """Infer a small object's one-cell translation without knowing its color a priori.

        The dominant background is excluded. Candidate colors must preserve population and
        move exactly one occupied cell to one new cell by Manhattan distance one. The
        smallest population wins, which strongly favors avatar-like objects over scenery.
        """
        if (len(before), len(before[0])) != (len(after), len(after[0])):
            return None
        counts = Counter(v for row in before for v in row)
        background = infer_background_color(before)
        candidates: list[tuple[int, int, Point]] = []
        colors = set(v for row in before for v in row) | set(v for row in after for v in row)
        for color in colors:
            if color == background:
                continue
            bp = {(x, y) for y, row in enumerate(before) for x, v in enumerate(row) if v == color}
            ap = {(x, y) for y, row in enumerate(after) for x, v in enumerate(row) if v == color}
            if not bp or len(bp) != len(ap) or len(bp) > 8:
                continue
            removed = bp - ap
            added = ap - bp
            if len(removed) != 1 or len(added) != 1:
                continue
            (x0, y0), = removed
            (x1, y1), = added
            delta = (x1 - x0, y1 - y0)
            if abs(delta[0]) + abs(delta[1]) != 1:
                continue
            candidates.append((len(bp), color, delta))
        if not candidates:
            return None
        _, color, delta = min(candidates)
        return color, delta

    def observe(self, transition: Transition) -> None:
        scene = scene_signature(transition.before)
        self._scene_action[(scene, transition.action.name)].add(transition.effect)
        self._global_action[transition.action.name].add(transition.effect)
        if transition.action.x is not None:
            self._coordinate_action[(transition.action.name, transition.action.x, transition.action.y)].add(transition.effect)
        motion = self._infer_unit_motion(transition.before.frame, transition.after.frame)
        if motion is not None and transition.action.x is None:
            color, delta = motion
            self._mobile_color_votes[color] += 1
            self._motion_votes[transition.action.name][delta] += 1
        self.transitions.append(transition)
        self.seen_frames[grid_digest(transition.after.frame)] += 1

    @property
    def mobile_color(self) -> int | None:
        return self._mobile_color_votes.most_common(1)[0][0] if self._mobile_color_votes else None

    def movement_delta(self, action_name: str) -> Point | None:
        votes = self._motion_votes.get(action_name)
        if not votes:
            return None
        delta, count = votes.most_common(1)[0]
        total = sum(votes.values())
        return delta if count * 2 >= total else None

    def action_for_delta(self, delta: Point, available: Iterable[str]) -> str | None:
        choices: list[tuple[int, str]] = []
        for name in available:
            votes = self._motion_votes.get(name)
            if votes and votes.get(delta, 0):
                choices.append((votes[delta], name))
        return max(choices)[1] if choices else None

    def movement_actions(self) -> frozenset[str]:
        return frozenset(name for name in self._motion_votes if self.movement_delta(name) is not None)

    def local_stats(self, obs: Observation, action: ActionToken) -> EffectStats:
        return self._scene_action.get((scene_signature(obs), action.name), EffectStats())

    def stats(self, obs: Observation, action: ActionToken) -> EffectStats:
        scene = scene_signature(obs)
        local = self._scene_action.get((scene, action.name))
        if local and local.total:
            return local
        if action.x is not None:
            coord = self._coordinate_action.get((action.name, action.x, action.y))
            if coord and coord.total:
                return coord
        return self._global_action.get(action.name, EffectStats())

    def novelty(self, obs: Observation) -> float:
        seen = self.seen_frames[grid_digest(obs.frame)]
        return 1.0 / (1 + seen)


@dataclass(frozen=True)
class ScenePrecondition:
    shape: tuple[int, int]
    palette: tuple[int, ...]
    component_histogram: tuple[tuple[int, int], ...]
    required_actions: tuple[str, ...]

    @classmethod
    def from_observation(cls, obs: Observation) -> "ScenePrecondition":
        components = connected_components(obs.frame)
        hist = Counter(c.color for c in components)
        return cls(
            obs.shape,
            tuple(sorted(set(v for row in obs.frame for v in row))),
            tuple(sorted(hist.items())),
            tuple(sorted(obs.available_actions)),
        )

    def matches(self, obs: Observation) -> bool:
        candidate = ScenePrecondition.from_observation(obs)
        return (
            self.shape == candidate.shape
            and self.palette == candidate.palette
            and self.component_histogram == candidate.component_histogram
            and set(self.required_actions).issubset(candidate.required_actions)
        )


@dataclass(frozen=True)
class Skill:
    precondition: ScenePrecondition
    actions: tuple[ActionToken, ...]
    expected_effects: tuple[str, ...]
    support: int
    successes: int
    source_trace_digest: str

    @property
    def confidence(self) -> float:
        return self.successes / self.support if self.support else 0.0


class SkillLibrary:
    def __init__(self) -> None:
        self._skills: list[Skill] = []

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills)

    def learn_success_suffix(self, trace: Sequence[Transition], *, max_len: int = 12) -> Skill | None:
        """Compile the shortest useful suffix ending in progress/WIN into a replay candidate."""
        if not trace:
            return None
        end = len(trace) - 1
        if trace[end].after.state != "WIN" and trace[end].effect.level_delta <= 0:
            return None
        start = end
        while start > 0 and end - start + 1 < max_len:
            prior = trace[start - 1]
            if prior.effect.level_delta > 0 or prior.after.state == "WIN":
                break
            start -= 1
        segment = tuple(trace[start : end + 1])
        action_names = tuple(t.action.name for t in segment)
        pre = ScenePrecondition.from_observation(segment[0].before)
        effects = tuple(t.effect.digest for t in segment)
        digest = trace_digest(segment)

        for idx, skill in enumerate(self._skills):
            if skill.precondition == pre and tuple(a.name for a in skill.actions) == action_names:
                successes = skill.successes + 1
                updated = Skill(pre, skill.actions, skill.expected_effects, skill.support + 1, successes, skill.source_trace_digest)
                self._skills[idx] = updated
                return updated
        skill = Skill(pre, tuple(t.action for t in segment), effects, 1, 1, digest)
        self._skills.append(skill)
        return skill

    def candidates(self, obs: Observation, *, min_confidence: float = 0.75) -> tuple[Skill, ...]:
        return tuple(s for s in self._skills if s.confidence >= min_confidence and s.precondition.matches(obs))
