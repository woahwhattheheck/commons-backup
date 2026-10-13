"""Action-efficient latent-control policy and spatial planner for SAGE."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from math import log2

from sage_core import ActionToken, Observation, Point, Transition, connected_components, infer_background_color
from sage_model import SkillLibrary, WorldModel

@dataclass(frozen=True)
class Decision:
    action: ActionToken
    mode: str
    score: float
    evidence: tuple[tuple[str, float], ...]


class Policy:
    """Action-efficient exploration, latent-control discovery, and spatial exploitation.

    SAGE never assumes an ACTIONn meaning.  Unit avatar motion is inferred from observed
    deltas.  Once enough controls are known, a small symbolic navigator approaches salient
    objects, probes non-motion interactions, and only enters a target after interaction
    hypotheses are exhausted.  The planner is an evidence consumer, not a game-specific
    rule table: colors, action IDs, switch locations and goals are never hard-coded.
    """

    def __init__(self, model: WorldModel, skills: SkillLibrary | None = None) -> None:
        self.model = model
        self.skills = skills or SkillLibrary()
        self._action_counts: Counter[str] = Counter()
        self._last_actions: deque[str] = deque(maxlen=6)
        self._target_attempts: dict[tuple[int, int, int], set[str]] = defaultdict(set)
        self._completed_targets: set[tuple[int, int, int]] = set()
        self._covered_target: tuple[int, int, int] | None = None

    @staticmethod
    def candidate_actions(obs: Observation) -> tuple[ActionToken, ...]:
        tokens: list[ActionToken] = []
        for name in sorted(obs.available_actions):
            if name == "ACTION6":
                points: set[Point] = set()
                h, w = obs.shape
                points.update({(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, h // 2)})
                for c in connected_components(obs.frame):
                    points.add(c.centroid)
                    x0, y0, x1, y1 = c.bbox
                    points.update({(x0, y0), (x1, y1)})
                tokens.extend(ActionToken(name, x, y) for x, y in sorted(points))
            else:
                tokens.append(ActionToken(name))
        return tuple(tokens)

    def _agent_position(self, obs: Observation) -> Point | None:
        color = self.model.mobile_color
        if color is None:
            return None
        cells = [(x, y) for y, row in enumerate(obs.frame) for x, value in enumerate(row) if value == color]
        return cells[0] if len(cells) == 1 else None

    def _salient_targets(self, obs: Observation) -> tuple[tuple[tuple[int, int, int], Point], ...]:
        counts = Counter(v for row in obs.frame for v in row)
        background = infer_background_color(obs.frame)
        mobile = self.model.mobile_color
        total = obs.shape[0] * obs.shape[1]
        max_object = max(4, int(total * 0.15))
        out: list[tuple[tuple[int, int, int], Point]] = []
        for component in connected_components(obs.frame):
            if component.color in {background, mobile}:
                continue
            if component.area > max_object:
                continue
            point = component.centroid
            key = (component.color, point[0], point[1])
            out.append((key, point))
        return tuple(sorted(out))

    def _path(self, obs: Observation, target: Point, *, enter_target: bool) -> tuple[Point, int] | None:
        """Return first unit delta and shortest distance under a conservative occupancy map."""
        start = self._agent_position(obs)
        if start is None:
            return None
        h, w = obs.shape
        counts = Counter(v for row in obs.frame for v in row)
        background = infer_background_color(obs.frame)
        mobile = self.model.mobile_color

        def traversable(point: Point) -> bool:
            x, y = point
            if not (0 <= x < w and 0 <= y < h):
                return False
            if point == target and enter_target:
                return True
            return obs.frame[y][x] in {background, mobile}

        if enter_target:
            goals = {target}
        else:
            tx, ty = target
            goals = {
                p for p in ((tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1))
                if traversable(p)
            }
        if start in goals:
            return (0, 0), 0
        queue = deque([start])
        parent: dict[Point, Point | None] = {start: None}
        found: Point | None = None
        while queue:
            current = queue.popleft()
            if current in goals:
                found = current
                break
            cx, cy = current
            for nxt in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if nxt in parent or not traversable(nxt):
                    continue
                parent[nxt] = current
                queue.append(nxt)
        if found is None:
            return None
        path: list[Point] = []
        cur = found
        while cur != start:
            path.append(cur)
            prev = parent[cur]
            assert prev is not None
            cur = prev
        path.reverse()
        first = path[0]
        return (first[0] - start[0], first[1] - start[1]), len(path)

    def _planner_decision(self, obs: Observation, *, actions_left: int) -> Decision | None:
        if self.model.mobile_color is None or len(self.model.movement_actions()) < 3:
            return None
        agent = self._agent_position(obs)
        if agent is None:
            return None
        candidates: list[tuple[int, tuple[int, int, int], Point, Point]] = []
        for key, point in self._salient_targets(obs):
            if key in self._completed_targets:
                continue
            route = self._path(obs, point, enter_target=False)
            if route is None:
                continue
            delta, distance = route
            candidates.append((distance, key, point, delta))
        if not candidates:
            return None
        distance, key, target, delta = min(candidates, key=lambda row: (row[0], row[1]))

        if distance == 0:
            attempts = self._target_attempts[key]
            movement = self.model.movement_actions()
            probes: list[ActionToken] = []
            if "ACTION6" in obs.available_actions:
                click = ActionToken("ACTION6", target[0], target[1])
                if click.key not in attempts:
                    probes.append(click)
            for name in sorted(obs.available_actions):
                if name == "ACTION6" or name in movement:
                    continue
                token = ActionToken(name)
                if token.key not in attempts:
                    probes.append(token)
            if probes:
                token = probes[0]
                return Decision(token, "TARGET_PROBE", 50.0, (("target_distance", 0.0), ("prior_target_probes", float(len(attempts)))))

            route = self._path(obs, target, enter_target=True)
            if route is not None:
                enter_delta, enter_distance = route
                name = self.model.action_for_delta(enter_delta, obs.available_actions)
                if name is not None:
                    return Decision(ActionToken(name), "TARGET_ENTER", 45.0, (("target_distance", float(enter_distance)),))
            return None

        name = self.model.action_for_delta(delta, obs.available_actions)
        if name is None:
            return None
        return Decision(ActionToken(name), "NAVIGATE", 40.0 - distance * 0.01, (("target_distance", float(distance)),))

    def choose(self, obs: Observation, *, actions_left: int) -> Decision:
        if type(actions_left) is not int or actions_left <= 0:
            raise ValueError("actions_left must be a positive exact int")

        skill_candidates = [s for s in self.skills.candidates(obs) if len(s.actions) <= actions_left]
        if skill_candidates:
            skill = max(skill_candidates, key=lambda s: (s.confidence, s.successes, -len(s.actions)))
            action = skill.actions[0]
            if action.name in obs.available_actions:
                return Decision(
                    action,
                    "SKILL_REPLAY",
                    100.0 + skill.confidence,
                    (("skill_confidence", skill.confidence), ("skill_support", float(skill.support))),
                )

        planned = self._planner_decision(obs, actions_left=actions_left)
        if planned is not None:
            return planned

        scored: list[tuple[float, ActionToken, tuple[tuple[str, float], ...]]] = []
        for token in self.candidate_actions(obs):
            stats = self.model.stats(obs, token)
            local = self.model.local_stats(obs, token)
            globally_untried = stats.total == 0
            untried_bonus = 6.0 if globally_untried else (1.25 if local.total == 0 and token.x is None else 0.0)
            uncertainty = stats.entropy * stats.change_rate
            progress = 4.0 * stats.progress_rate + 5.0 * (stats.terminal_wins / stats.total if stats.total else 0.0)
            change = 1.5 * stats.change_rate
            repetition = self._last_actions.count(token.key) * 1.25
            global_repeat = log2(1 + self._action_counts[token.key]) * 0.25
            budget_pressure = 1.0 / max(1, actions_left)
            exploration_scale = min(1.0, actions_left / 8.0)
            score = (untried_bonus + uncertainty + change) * exploration_scale + progress * (1.0 + budget_pressure) - repetition - global_repeat
            evidence = (
                ("untried", untried_bonus),
                ("uncertainty", uncertainty),
                ("progress", progress),
                ("change", change),
                ("repetition_penalty", repetition + global_repeat),
            )
            scored.append((score, token, evidence))
        if not scored:
            raise ValueError("no available actions")
        score, action, evidence = max(scored, key=lambda item: (item[0], item[1].x is None, item[1].key))
        mode = "EXPLORE" if self.model.stats(obs, action).total == 0 else "MODEL_GUIDED"
        return Decision(action, mode, score, evidence)

    def record_choice(self, action: ActionToken) -> None:
        self._action_counts[action.key] += 1
        self._last_actions.append(action.key)

    def record_transition(self, transition: Transition) -> None:
        self.record_choice(transition.action)
        agent = self._agent_position(transition.before)
        if agent is None:
            return
        targets = self._salient_targets(transition.before)
        movement = self.model.movement_actions()

        if transition.action.name in movement:
            after_agent = self._agent_position(transition.after)
            if after_agent is not None:
                for key, point in targets:
                    if point == after_agent:
                        self._covered_target = key
                        break

        associated: tuple[int, int, int] | None = None
        if transition.action.x is not None:
            for key, point in targets:
                if point == (transition.action.x, transition.action.y):
                    associated = key
                    break
        elif transition.action.name not in movement:
            adjacent = [(key, point) for key, point in targets if abs(point[0] - agent[0]) + abs(point[1] - agent[1]) <= 1]
            if adjacent:
                associated = min(adjacent, key=lambda row: row[0])[0]
            elif self._covered_target is not None:
                associated = self._covered_target
        if associated is None:
            return
        self._target_attempts[associated].add(transition.action.key)
        if transition.effect.changed_count > 0 or transition.effect.level_delta > 0 or transition.after.state == "WIN":
            self._completed_targets.add(associated)
            if associated == self._covered_target:
                self._covered_target = None
