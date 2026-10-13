"""Self-contained ARC-AGI-3 Kaggle frontier-model agent.

Drop this file into the official starter as agent/my_agent.py.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable

MAX_SIDE = 64
RESET = 0
VALID = frozenset(range(1, 8))
RESET_STATES = frozenset({"NOT_PLAYED", "GAME_OVER"})
Grid = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Decision:
    action_id: int
    x: int | None = None
    y: int | None = None
    reason: str = ""

    @property
    def key(self) -> str:
        return f"6:{self.x}:{self.y}" if self.action_id == 6 else str(self.action_id)

    def as_action_data(self) -> dict[str, int]:
        if self.action_id != 6:
            return {}
        if self.x is None or self.y is None:
            raise ValueError("ACTION6 requires x,y")
        return {"x": self.x, "y": self.y}


@dataclass
class TransitionStat:
    visits: int = 0
    reward_sum: float = 0.0
    changed_cells: int = 0
    novel_successors: int = 0
    level_advances: int = 0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.visits if self.visits else 0.0


def state_name(state: Any) -> str:
    name = getattr(state, "name", None)
    if isinstance(name, str):
        return name.upper()
    text = str(state or "NOT_FINISHED").upper()
    return text.rsplit(".", 1)[-1]


def normalize_grid(frame: Any) -> Grid:
    if hasattr(frame, "tolist"):
        frame = frame.tolist()
    if not isinstance(frame, (list, tuple)) or not frame:
        raise ValueError("frame must be non-empty")
    first = frame[0]
    if isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
        frame = frame[-1]
        if hasattr(frame, "tolist"):
            frame = frame.tolist()
    if not isinstance(frame, (list, tuple)) or not frame or len(frame) > MAX_SIDE:
        raise ValueError("invalid grid height")
    rows: list[tuple[int, ...]] = []
    width: int | None = None
    for row in frame:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (list, tuple)) or not row or len(row) > MAX_SIDE:
            raise ValueError("invalid grid row")
        width = len(row) if width is None else width
        if len(row) != width:
            raise ValueError("grid must be rectangular")
        out: list[int] = []
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 15:
                raise ValueError("grid cells must be ints 0..15")
            out.append(cell)
        rows.append(tuple(out))
    return tuple(rows)


def normalize_actions(actions: Iterable[Any] | None) -> tuple[int, ...]:
    if actions is None:
        return tuple(sorted(VALID))
    ids: set[int] = set()
    for action in actions:
        raw = getattr(action, "value", action)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value in VALID:
            ids.add(value)
    if not ids:
        raise ValueError("no valid available actions")
    return tuple(sorted(ids))


def grid_signature(grid: Grid) -> str:
    packed = json.dumps(grid, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(packed).hexdigest()[:24]


def changed_cells(a: Grid, b: Grid) -> tuple[tuple[int, int], ...]:
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return tuple()
    return tuple(
        (x, y)
        for y, (row_a, row_b) in enumerate(zip(a, b))
        for x, (value_a, value_b) in enumerate(zip(row_a, row_b))
        if value_a != value_b
    )


def component_centers(grid: Grid) -> list[tuple[int, int, int]]:
    background = Counter(cell for row in grid for cell in row).most_common(1)[0][0]
    height = len(grid)
    width = len(grid[0])
    seen: set[tuple[int, int]] = set()
    parts: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] == background or (x, y) in seen:
                continue
            color = grid[y][x]
            queue = deque([(x, y)])
            seen.add((x, y))
            points: list[tuple[int, int]] = []
            while queue:
                current_x, current_y = queue.popleft()
                points.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if (
                        0 <= next_x < width
                        and 0 <= next_y < height
                        and (next_x, next_y) not in seen
                        and grid[next_y][next_x] == color
                    ):
                        seen.add((next_x, next_y))
                        queue.append((next_x, next_y))
            parts.append(
                (
                    len(points),
                    round(sum(px for px, _ in points) / len(points)),
                    round(sum(py for _, py in points) / len(points)),
                )
            )
    return sorted(parts, key=lambda item: (item[0], item[2], item[1]))


def coordinate_candidates(grid: Grid, previous: Grid | None = None) -> tuple[tuple[int, int], ...]:
    height = len(grid)
    width = len(grid[0])
    points: list[tuple[int, int]] = []
    if previous is not None:
        diff = changed_cells(previous, grid)
        if diff:
            points.append(
                (
                    round(sum(x for x, _ in diff) / len(diff)),
                    round(sum(y for _, y in diff) / len(diff)),
                )
            )
            points.extend(diff[:8])
    points.extend((x, y) for _, x, y in component_centers(grid)[:12])
    points.extend(
        [(width // 2, height // 2), (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    )
    output: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for x, y in points:
        point = (max(0, min(63, int(x))), max(0, min(63, int(y))))
        if point not in seen:
            seen.add(point)
            output.append(point)
    return tuple(output[:24])


def decision_from_key(key: str, reason: str = "") -> Decision:
    if key.startswith("6:"):
        _, raw_x, raw_y = key.split(":", 2)
        return Decision(6, int(raw_x), int(raw_y), reason)
    return Decision(int(key), reason=reason)


class NoveltyExplorer:
    """Online transition learner with deterministic frontier routing and UCB fallback."""

    ORDER = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}

    def __init__(self) -> None:
        self.seen_states: Counter[str] = Counter()
        self.state_action_visits: Counter[tuple[str, int]] = Counter()
        self.action_key_visits: Counter[tuple[str, str]] = Counter()
        self.coord_visits: Counter[tuple[str, int, int]] = Counter()
        self.stats: defaultdict[tuple[str, str], TransitionStat] = defaultdict(TransitionStat)
        self.successors: defaultdict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self.state_actions: dict[str, tuple[int, ...]] = {}
        self.state_grids: dict[str, Grid] = {}
        self.last_state: str | None = None
        self.last_grid: Grid | None = None
        self.last_level = 0
        self.last_decision: Decision | None = None
        self.total_decisions = 0
        self.frontier_routes = 0

    def reset_episode_memory(self) -> None:
        self.last_state = None
        self.last_grid = None
        self.last_decision = None
        self.last_level = 0

    def _observe(self, state: str, grid: Grid, level: int) -> None:
        if self.last_state is None or self.last_decision is None or self.last_grid is None:
            return
        diff = changed_cells(self.last_grid, grid)
        resized = len(self.last_grid) != len(grid) or len(self.last_grid[0]) != len(grid[0])
        advance = max(0, level - self.last_level)
        novel = self.seen_states[state] == 0
        visible_reward = (
            -0.15
            if not diff and not resized
            else 0.5 + min(1.5, len(diff) / max(1, len(grid) * len(grid[0])) * 6.0)
        )
        reward = visible_reward + int(novel) + 8.0 * advance
        key = (self.last_state, self.last_decision.key)
        stat = self.stats[key]
        stat.visits += 1
        stat.reward_sum += reward
        stat.changed_cells += len(diff)
        stat.novel_successors += int(novel)
        stat.level_advances += advance
        self.successors[key][state] += 1

    def _candidate_decisions(self, state: str) -> tuple[Decision, ...]:
        actions = self.state_actions.get(state, tuple())
        grid = self.state_grids.get(state)
        output: list[Decision] = []
        for action_id in actions:
            if action_id == 6:
                if grid is None:
                    continue
                output.extend(Decision(6, x, y) for x, y in coordinate_candidates(grid))
            else:
                output.append(Decision(action_id))
        return tuple(output)

    def _untried_decisions(self, state: str) -> tuple[Decision, ...]:
        return tuple(
            decision
            for decision in self._candidate_decisions(state)
            if self.action_key_visits[(state, decision.key)] == 0
        )

    def _edge_successor(self, state: str, key: str) -> str | None:
        counter = self.successors.get((state, key))
        if not counter:
            return None
        ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        for successor, _ in ranked:
            if successor != state:
                return successor
        return None

    def _frontier_route(self, start: str) -> Decision | None:
        """Return the first learned action on a shortest route to an explorable state."""
        queue = deque([(start, tuple())])
        seen = {start}
        while queue:
            state, path = queue.popleft()
            if state != start and self._untried_decisions(state):
                first_key = path[0]
                decision = decision_from_key(first_key, reason=f"frontier-route depth={len(path)}")
                current_actions = self.state_actions.get(start, tuple())
                if decision.action_id in current_actions:
                    return decision
            for candidate in self._candidate_decisions(state):
                successor = self._edge_successor(state, candidate.key)
                if successor is None or successor in seen:
                    continue
                seen.add(successor)
                queue.append((successor, path + (candidate.key,)))
        return None

    def _score(self, state: str, action_id: int) -> tuple[float, float, float, int]:
        visits = self.state_action_visits[(state, action_id)]
        total = 1 + sum(self.state_action_visits[(state, candidate)] for candidate in VALID)
        matching = [
            stat
            for (source, key), stat in self.stats.items()
            if source == state and key.split(":", 1)[0] == str(action_id)
        ]
        samples = sum(stat.visits for stat in matching)
        mean = sum(stat.reward_sum for stat in matching) / samples if samples else 0.0
        ucb = mean + 0.45 * math.sqrt(math.log(total + 1) / (visits + 1))
        return (1.0 if visits == 0 else 0.0, ucb, -float(visits), -self.ORDER.get(action_id, 99))

    def _fallback_decision(self, state: str, grid: Grid, actions: tuple[int, ...]) -> Decision:
        action_id = max(actions, key=lambda candidate: self._score(state, candidate))
        if action_id == 6:
            candidates = coordinate_candidates(grid, self.last_grid)
            x, y = min(
                candidates,
                key=lambda point: (
                    self.coord_visits[(state, point[0], point[1])],
                    candidates.index(point),
                ),
            )
            return Decision(6, x, y, f"fallback-UCB ACTION6 target ({x},{y})")
        return Decision(action_id, reason=f"fallback-UCB ACTION{action_id}")

    def choose(
        self,
        frame: Any,
        available_actions: Iterable[Any] | None,
        *,
        state: Any = "NOT_FINISHED",
        levels_completed: int = 0,
    ) -> Decision:
        state_label = state_name(state)
        if state_label in RESET_STATES:
            self.reset_episode_memory()
            return Decision(0, reason=f"{state_label}: RESET only")
        if state_label == "WIN":
            return Decision(0, reason="WIN observed")

        grid = normalize_grid(frame)
        actions = normalize_actions(available_actions)
        signature = grid_signature(grid)
        self._observe(signature, grid, int(levels_completed))
        self.seen_states[signature] += 1
        self.state_actions[signature] = actions
        self.state_grids[signature] = grid

        untried = self._untried_decisions(signature)
        if untried:
            decision = untried[0]
            decision = Decision(decision.action_id, decision.x, decision.y, "untried-frontier")
        else:
            decision = self._frontier_route(signature)
            if decision is not None:
                self.frontier_routes += 1
            else:
                decision = self._fallback_decision(signature, grid, actions)

        self.state_action_visits[(signature, decision.action_id)] += 1
        self.action_key_visits[(signature, decision.key)] += 1
        if decision.action_id == 6 and decision.x is not None and decision.y is not None:
            self.coord_visits[(signature, decision.x, decision.y)] += 1
        self.total_decisions += 1
        self.last_state = signature
        self.last_grid = grid
        self.last_level = int(levels_completed)
        self.last_decision = decision
        return decision

    def diagnostics(self) -> dict[str, Any]:
        known_edges = sum(
            1
            for (state, key) in self.successors
            if self._edge_successor(state, key) is not None
        )
        self_loops = sum(
            counter.get(state, 0)
            for (state, _), counter in self.successors.items()
        )
        return {
            "policy": "deterministic-frontier-model-v2",
            "total_decisions": self.total_decisions,
            "unique_states": len(self.seen_states),
            "known_edges": known_edges,
            "frontier_routes": self.frontier_routes,
            "self_loop_observations": self_loops,
            "transitions": {
                f"{state}:{key}": {
                    "visits": stat.visits,
                    "mean_reward": round(stat.mean_reward, 6),
                    "changed_cells": stat.changed_cells,
                    "novel_successors": stat.novel_successors,
                    "level_advances": stat.level_advances,
                    "successor_count": len(self.successors[(state, key)]),
                }
                for (state, key), stat in sorted(self.stats.items())
            },
        }


from arcengine import FrameData, GameAction, GameState
from agents.agent import Agent
import os


class MyAgent(Agent):
    """Deterministic model-based frontier baseline for the official Kaggle starter."""

    MAX_ACTIONS = int(os.environ.get("SOL_ARC3_MAX_ACTIONS", "400"))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.policy = NoveltyExplorer()

    @property
    def name(self) -> str:
        return f"{super().name}.{self.MAX_ACTIONS}.solarc3-frontier-v2"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            return GameAction.RESET
        decision = self.policy.choose(
            latest_frame.frame,
            latest_frame.available_actions,
            state=latest_frame.state,
            levels_completed=latest_frame.levels_completed,
        )
        action = GameAction.from_id(decision.action_id)
        if decision.action_id == 6:
            action.set_data(decision.as_action_data())
        diagnostics = self.policy.diagnostics()
        action.reasoning = {
            "policy": diagnostics["policy"],
            "reason": decision.reason,
            "unique_states": diagnostics["unique_states"],
            "known_edges": diagnostics["known_edges"],
            "frontier_routes": diagnostics["frontier_routes"],
            "decisions": diagnostics["total_decisions"],
        }
        return action
