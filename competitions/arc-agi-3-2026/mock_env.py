"""No-network ARC3-style mock environments for deterministic SAGE testing.

The environment intentionally scrambles action meanings by seed and emits animation
frames when the door opens.  An agent that assumes ACTION1 == UP or discards intermediate
frames will learn brittle behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Mapping

from sage import ActionToken, Grid, Observation, validate_grid


@dataclass(frozen=True)
class MockConfig:
    width: int = 7
    height: int = 7
    max_actions: int = 80


class SwitchDoorEnv:
    """Tiny hidden-control game with one switch, one locked door, and one goal.

    Colors: 0 empty, 1 wall, 2 agent, 3 switch, 4 closed door, 5 open-door animation,
    6 goal.  The semantic mapping of ACTION1..ACTION5 is shuffled each seed.
    ACTION6 is a click/no-op-like complex action which can activate the switch when the
    click lands on it, providing a coordinate-action research path.
    """

    MOVES = ((0, -1), (0, 1), (-1, 0), (1, 0))

    def __init__(self, seed: int = 0, config: MockConfig | None = None) -> None:
        self.seed = seed
        self.config = config or MockConfig()
        rng = Random(seed)
        semantics = ["UP", "DOWN", "LEFT", "RIGHT", "INTERACT"]
        rng.shuffle(semantics)
        self.semantic_by_action = {f"ACTION{i+1}": semantics[i] for i in range(5)}
        self.reset_state()

    def reset_state(self) -> None:
        self.agent = (1, 5)
        self.switch = (2, 3)
        self.door = (3, 2)
        self.goal = (5, 1)
        self.door_open = False
        self.actions = 0
        self.levels_completed = 0
        self.state = "NOT_FINISHED"

    def _base_grid(self, *, door_color: int | None = None) -> Grid:
        w, h = self.config.width, self.config.height
        g = [[0 for _ in range(w)] for _ in range(h)]
        for x in range(w):
            g[0][x] = g[h - 1][x] = 1
        for y in range(h):
            g[y][0] = g[y][w - 1] = 1
        # Vertical separator; door is the only crossing.
        for y in range(1, h - 1):
            g[y][3] = 1
        dx, dy = self.door
        if self.door_open:
            g[dy][dx] = 0
        else:
            g[dy][dx] = 4 if door_color is None else door_color
        sx, sy = self.switch
        g[sy][sx] = 3
        gx, gy = self.goal
        g[gy][gx] = 6
        ax, ay = self.agent
        g[ay][ax] = 2
        return validate_grid(g)

    def observation(self, frames: tuple[Grid, ...] | None = None) -> Observation:
        return Observation(
            frames=frames or (self._base_grid(),),
            available_actions=("ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"),
            state=self.state,
            levels_completed=self.levels_completed,
            win_levels=1,
        )

    def reset(self) -> Observation:
        self.reset_state()
        return self.observation()

    def _try_move(self, dx: int, dy: int) -> None:
        nx, ny = self.agent[0] + dx, self.agent[1] + dy
        grid = self._base_grid()
        if grid[ny][nx] not in (1, 4):
            self.agent = (nx, ny)

    def _activate_switch(self) -> tuple[Grid, ...] | None:
        # Adjacent INTERACT or exact click opens door and returns temporal animation.
        if abs(self.agent[0] - self.switch[0]) + abs(self.agent[1] - self.switch[1]) <= 1:
            if not self.door_open:
                closed = self._base_grid()
                flicker = self._base_grid(door_color=5)
                self.door_open = True
                opened = self._base_grid()
                return (closed, flicker, opened)
        return None

    def step(self, action: ActionToken) -> Observation:
        if self.state != "NOT_FINISHED":
            return self.observation()
        if action.name not in self.observation().available_actions:
            raise ValueError("unavailable action")
        self.actions += 1
        animation: tuple[Grid, ...] | None = None
        if action.name == "ACTION6":
            if action.x is None:
                raise ValueError("ACTION6 requires coordinate")
            if (action.x, action.y) == self.switch:
                animation = self._activate_switch()
        else:
            semantic = self.semantic_by_action[action.name]
            if semantic == "UP":
                self._try_move(0, -1)
            elif semantic == "DOWN":
                self._try_move(0, 1)
            elif semantic == "LEFT":
                self._try_move(-1, 0)
            elif semantic == "RIGHT":
                self._try_move(1, 0)
            elif semantic == "INTERACT":
                animation = self._activate_switch()
        if self.agent == self.goal:
            self.levels_completed = 1
            self.state = "WIN"
        elif self.actions >= self.config.max_actions:
            self.state = "GAME_OVER"
        if animation:
            # Ensure final frame includes any move-independent state after activation.
            return self.observation(animation)
        return self.observation()
