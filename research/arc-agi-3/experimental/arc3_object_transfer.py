"""Role-free object-motion transfer for the ARC-AGI-3 frontier baseline.

This module stays observation-only: it infers a reusable movement model only when
exactly one non-background connected component translates without changing shape.
It then plans over previously observed object positions, treating model predictions
as hypotheses that are invalidated by no-change observations.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable
from pathlib import Path
import sys

_PARENT = Path(__file__).resolve().parents[1]
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from arc3_baseline import (
    Decision,
    Grid,
    NoveltyExplorer,
    VALID,
    changed_cells,
    coordinate_candidates,
    grid_signature,
    normalize_actions,
    normalize_grid,
    state_name,
    RESET_STATES,
)

Fingerprint = tuple[int, int, int, tuple[tuple[int, int], ...]]
SceneKey = tuple[str, Fingerprint]


@dataclass(frozen=True)
class Component:
    color: int
    origin: tuple[int, int]
    shape: tuple[tuple[int, int], ...]
    width: int
    height: int

    @property
    def fingerprint(self) -> Fingerprint:
        return (self.color, self.width, self.height, self.shape)


@dataclass(frozen=True)
class Translation:
    fingerprint: Fingerprint
    source: tuple[int, int]
    target: tuple[int, int]
    delta: tuple[int, int]


def extract_components(grid: Grid) -> tuple[int, tuple[Component, ...]]:
    background = Counter(cell for row in grid for cell in row).most_common(1)[0][0]
    height, width = len(grid), len(grid[0])
    seen: set[tuple[int, int]] = set()
    output: list[Component] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] == background or (x, y) in seen:
                continue
            color = grid[y][x]
            queue = deque([(x, y)])
            seen.add((x, y))
            cells: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and (nx, ny) not in seen
                        and grid[ny][nx] == color
                    ):
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            min_x = min(px for px, _ in cells)
            min_y = min(py for _, py in cells)
            max_x = max(px for px, _ in cells)
            max_y = max(py for _, py in cells)
            shape = tuple(sorted((px - min_x, py - min_y) for px, py in cells))
            output.append(Component(color, (min_x, min_y), shape, max_x - min_x + 1, max_y - min_y + 1))
    return background, tuple(sorted(output, key=lambda c: (c.color, c.origin, c.shape)))


def infer_single_translation(before: Grid, after: Grid) -> Translation | None:
    if len(before) != len(after) or len(before[0]) != len(after[0]):
        return None
    bg_before, before_components = extract_components(before)
    bg_after, after_components = extract_components(after)
    if bg_before != bg_after:
        return None

    groups_before: defaultdict[Fingerprint, list[Component]] = defaultdict(list)
    groups_after: defaultdict[Fingerprint, list[Component]] = defaultdict(list)
    for component in before_components:
        groups_before[component.fingerprint].append(component)
    for component in after_components:
        groups_after[component.fingerprint].append(component)
    if set(groups_before) != set(groups_after):
        return None

    moved: list[Translation] = []
    for fingerprint in sorted(groups_before, key=repr):
        left = groups_before[fingerprint]
        right = groups_after[fingerprint]
        if len(left) != len(right):
            return None
        if len(left) == 1:
            source, target = left[0], right[0]
            if source.origin != target.origin:
                moved.append(
                    Translation(
                        fingerprint,
                        source.origin,
                        target.origin,
                        (target.origin[0] - source.origin[0], target.origin[1] - source.origin[1]),
                    )
                )
        else:
            if sorted(component.origin for component in left) != sorted(component.origin for component in right):
                return None
    return moved[0] if len(moved) == 1 else None


def scene_signature(grid: Grid, mobile: Fingerprint) -> SceneKey | None:
    background, components = extract_components(grid)
    matching = [component for component in components if component.fingerprint == mobile]
    if len(matching) != 1:
        return None
    static = [
        (component.fingerprint, component.origin)
        for component in components
        if component.fingerprint != mobile
    ]
    payload = (len(grid), len(grid[0]), background, static)
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), default=list).encode("utf-8")).hexdigest()[:24]
    return (digest, mobile)


def mobile_origin(grid: Grid, mobile: Fingerprint) -> tuple[int, int] | None:
    _, components = extract_components(grid)
    matching = [component.origin for component in components if component.fingerprint == mobile]
    return matching[0] if len(matching) == 1 else None


class ObjectTransferExplorer(NoveltyExplorer):
    """V3: exact transition graph + conservative role-free movement transfer."""

    def __init__(self) -> None:
        super().__init__()
        self.global_action_visits: Counter[int] = Counter()
        self.movement_effects: defaultdict[tuple[Fingerprint, int], Counter[tuple[int, int]]] = defaultdict(Counter)
        self.visited_positions: defaultdict[SceneKey, set[tuple[int, int]]] = defaultdict(set)
        self.blocked_predictions: set[tuple[SceneKey, tuple[int, int], int]] = set()
        self.object_plans = 0
        self.motion_observations = 0

    def _observe(self, state: str, grid: Grid, level: int) -> None:
        previous_grid = self.last_grid
        previous_decision = self.last_decision
        super()._observe(state, grid, level)
        if previous_grid is None or previous_decision is None or previous_decision.action_id == 6:
            return

        action_id = previous_decision.action_id
        translation = infer_single_translation(previous_grid, grid)
        if translation is not None:
            scene_before = scene_signature(previous_grid, translation.fingerprint)
            scene_after = scene_signature(grid, translation.fingerprint)
            if scene_before is not None and scene_before == scene_after:
                self.movement_effects[(translation.fingerprint, action_id)][translation.delta] += 1
                self.visited_positions[scene_before].add(translation.source)
                self.visited_positions[scene_before].add(translation.target)
                self.motion_observations += 1
            return

        if not changed_cells(previous_grid, grid):
            for fingerprint, known_action in tuple(self.movement_effects):
                if known_action != action_id:
                    continue
                scene = scene_signature(previous_grid, fingerprint)
                origin = mobile_origin(previous_grid, fingerprint)
                if scene is not None and origin is not None:
                    self.blocked_predictions.add((scene, origin, action_id))
                    self.visited_positions[scene].add(origin)

    def _untried_decisions(self, state: str) -> tuple[Decision, ...]:
        # Balance action *ids* globally, but preserve the baseline's candidate
        # ordering within an action. That matters for ACTION6 because its first
        # coordinate is intentionally the most salient changed/component point.
        indexed = [
            (index, decision)
            for index, decision in enumerate(self._candidate_decisions(state))
            if self.action_key_visits[(state, decision.key)] == 0
        ]
        return tuple(
            decision
            for _, decision in sorted(
                indexed,
                key=lambda item: (
                    self.global_action_visits[item[1].action_id],
                    item[1].action_id,
                    item[0],
                ),
            )
        )

    def _best_vectors(self, fingerprint: Fingerprint, actions: tuple[int, ...]) -> dict[int, tuple[int, int]]:
        output: dict[int, tuple[int, int]] = {}
        for action_id in actions:
            if action_id == 6:
                continue
            counter = self.movement_effects.get((fingerprint, action_id))
            if not counter:
                continue
            delta, _ = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
            if delta != (0, 0):
                output[action_id] = delta
        return output

    def _in_bounds(self, origin: tuple[int, int], fingerprint: Fingerprint, grid: Grid) -> bool:
        _, component_width, component_height, _ = fingerprint
        x, y = origin
        return 0 <= x <= len(grid[0]) - component_width and 0 <= y <= len(grid) - component_height

    def _object_plan(self, grid: Grid, actions: tuple[int, ...]) -> Decision | None:
        fingerprints = sorted({fingerprint for fingerprint, action_id in self.movement_effects if action_id in actions}, key=repr)
        for fingerprint in fingerprints:
            vectors = self._best_vectors(fingerprint, actions)
            if len(vectors) < 2:
                continue
            scene = scene_signature(grid, fingerprint)
            origin = mobile_origin(grid, fingerprint)
            if scene is None or origin is None:
                continue
            visited = self.visited_positions[scene]
            visited.add(origin)

            queue = deque([(origin, tuple())])
            seen = {origin}
            while queue:
                position, path = queue.popleft()
                # First prefer a one-step model prediction into unseen position space.
                for action_id in sorted(vectors):
                    if (scene, position, action_id) in self.blocked_predictions:
                        continue
                    dx, dy = vectors[action_id]
                    target = (position[0] + dx, position[1] + dy)
                    if not self._in_bounds(target, fingerprint, grid):
                        continue
                    if target not in visited:
                        first_action = path[0] if path else action_id
                        return Decision(
                            first_action,
                            reason=(
                                f"object-frontier route={len(path)} target={target} "
                                f"model=ACTION{action_id}:{dx},{dy}"
                            ),
                        )
                # Traverse only through positions actually seen under the same static scene.
                for action_id in sorted(vectors):
                    if (scene, position, action_id) in self.blocked_predictions:
                        continue
                    dx, dy = vectors[action_id]
                    target = (position[0] + dx, position[1] + dy)
                    if target not in visited or target in seen:
                        continue
                    seen.add(target)
                    queue.append((target, path + (action_id,)))
        return None

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

        # Once at least two movement semantics are learned, use the transferred model
        # before re-testing every action at every translated object position.
        decision = self._object_plan(grid, actions)
        if decision is not None:
            self.object_plans += 1
        else:
            untried = self._untried_decisions(signature)
            if untried:
                chosen = untried[0]
                decision = Decision(chosen.action_id, chosen.x, chosen.y, "globally-balanced-frontier")
            else:
                decision = self._frontier_route(signature)
                if decision is not None:
                    self.frontier_routes += 1
                else:
                    decision = self._fallback_decision(signature, grid, actions)

        self.state_action_visits[(signature, decision.action_id)] += 1
        self.action_key_visits[(signature, decision.key)] += 1
        self.global_action_visits[decision.action_id] += 1
        if decision.action_id == 6 and decision.x is not None and decision.y is not None:
            self.coord_visits[(signature, decision.x, decision.y)] += 1
        self.total_decisions += 1
        self.last_state = signature
        self.last_grid = grid
        self.last_level = int(levels_completed)
        self.last_decision = decision
        return decision

    def diagnostics(self) -> dict[str, Any]:
        diagnostics = super().diagnostics()
        diagnostics.update(
            {
                "policy": "object-transfer-frontier-v3",
                "object_plans": self.object_plans,
                "motion_observations": self.motion_observations,
                "movement_models": len(self.movement_effects),
                "blocked_predictions": len(self.blocked_predictions),
            }
        )
        return diagnostics
