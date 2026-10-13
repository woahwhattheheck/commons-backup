"""SAGE: State-Action Generalization Engine for ARC-AGI-3 style environments.

The module is deliberately dependency-free so the research core can run in Kaggle's
internet-disabled notebook environment and in Commons CI.  It does not assume the
meaning of ACTION1..ACTION7.  Instead it learns compact state/action/effect evidence
from interaction and spends actions where uncertainty or novelty is highest.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from hashlib import sha256
from math import log2
from typing import Iterable, Iterator, Mapping, Sequence

Grid = tuple[tuple[int, ...], ...]
Point = tuple[int, int]


def _canonical_bytes(parts: Iterable[object]) -> bytes:
    return "\x1f".join(str(p) for p in parts).encode("utf-8")


def infer_background_color(grid: Grid) -> int:
    """Infer a scene background without assuming ARC color 0.

    Interior prevalence is preferred so border/wall colors do not win merely because a
    frame is enclosed. Global prevalence breaks ties and handles tiny grids.
    """
    global_counts = Counter(v for row in grid for v in row)
    if len(grid) >= 3 and len(grid[0]) >= 3:
        interior = Counter(grid[y][x] for y in range(1, len(grid) - 1) for x in range(1, len(grid[0]) - 1))
        if interior:
            return max(interior, key=lambda c: (interior[c], global_counts[c], -c))
    return global_counts.most_common(1)[0][0]


def grid_digest(grid: Grid) -> str:
    h = sha256()
    h.update(f"{len(grid)}x{len(grid[0]) if grid else 0}|".encode())
    for row in grid:
        h.update(bytes(row))
    return h.hexdigest()


def validate_grid(raw: Sequence[Sequence[int]]) -> Grid:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        raise ValueError("grid must be a non-empty row sequence")
    width: int | None = None
    out: list[tuple[int, ...]] = []
    for row in raw:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or not row:
            raise ValueError("grid rows must be non-empty sequences")
        vals: list[int] = []
        for value in row:
            if type(value) is not int or not 0 <= value <= 15:
                raise ValueError("grid values must be exact ints in [0,15]")
            vals.append(value)
        if width is None:
            width = len(vals)
        elif len(vals) != width:
            raise ValueError("grid must be rectangular")
        out.append(tuple(vals))
    if len(out) > 64 or (width or 0) > 64:
        raise ValueError("grid exceeds ARC-AGI-3 64x64 bound")
    return tuple(out)


@dataclass(frozen=True, order=True)
class ActionToken:
    """One environment action, optionally carrying an ARC complex-action coordinate."""

    name: str
    x: int | None = None
    y: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.startswith("ACTION"):
            raise ValueError("action name must use ACTION* form")
        if (self.x is None) != (self.y is None):
            raise ValueError("x and y must be supplied together")
        if self.x is not None and not (0 <= self.x < 64 and 0 <= self.y < 64):
            raise ValueError("complex action coordinate outside 64x64 bounds")

    @property
    def key(self) -> str:
        return self.name if self.x is None else f"{self.name}@{self.x},{self.y}"


@dataclass(frozen=True)
class Observation:
    """Normalized response retaining *all* frames returned by an action."""

    frames: tuple[Grid, ...]
    available_actions: tuple[str, ...]
    state: str = "NOT_FINISHED"
    levels_completed: int = 0
    win_levels: int = 0

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("observation must retain at least one frame")
        for frame in self.frames:
            validate_grid(frame)
        if len(set(self.available_actions)) != len(self.available_actions):
            raise ValueError("available actions must be unique")
        if any(not a.startswith("ACTION") for a in self.available_actions):
            raise ValueError("available actions must use ACTION* names")
        if type(self.levels_completed) is not int or self.levels_completed < 0:
            raise ValueError("levels_completed must be a non-negative exact int")
        if type(self.win_levels) is not int or self.win_levels < 0:
            raise ValueError("win_levels must be a non-negative exact int")

    @property
    def frame(self) -> Grid:
        return self.frames[-1]

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.frame), len(self.frame[0])


@dataclass(frozen=True)
class Component:
    color: int
    cells: tuple[Point, ...]

    @property
    def area(self) -> int:
        return len(self.cells)

    @property
    def centroid(self) -> Point:
        x = sum(p[0] for p in self.cells) // len(self.cells)
        y = sum(p[1] for p in self.cells) // len(self.cells)
        return x, y

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        xs = [p[0] for p in self.cells]
        ys = [p[1] for p in self.cells]
        return min(xs), min(ys), max(xs), max(ys)


def connected_components(grid: Grid, *, include_zero: bool = False) -> tuple[Component, ...]:
    h = len(grid)
    w = len(grid[0])
    seen: set[Point] = set()
    components: list[Component] = []
    for y in range(h):
        for x in range(w):
            if (x, y) in seen:
                continue
            color = grid[y][x]
            if color == 0 and not include_zero:
                seen.add((x, y))
                continue
            queue = deque([(x, y)])
            seen.add((x, y))
            cells: list[Point] = []
            while queue:
                cx, cy = queue.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                        continue
                    if grid[ny][nx] != color:
                        continue
                    seen.add((nx, ny))
                    queue.append((nx, ny))
            components.append(Component(color, tuple(sorted(cells))))
    return tuple(sorted(components, key=lambda c: (c.color, c.bbox, c.area)))


def scene_signature(obs: Observation) -> str:
    """Generalized scene class, intentionally less specific than exact frame bytes."""
    components = connected_components(obs.frame)
    palette = tuple(sorted(set(v for row in obs.frame for v in row)))
    shape = obs.shape
    summary = tuple((c.color, c.area, c.bbox[2] - c.bbox[0] + 1, c.bbox[3] - c.bbox[1] + 1) for c in components)
    return sha256(_canonical_bytes((shape, palette, summary, tuple(sorted(obs.available_actions))))).hexdigest()


def changed_cells(before: Grid, after: Grid) -> tuple[Point, ...]:
    if (len(before), len(before[0])) != (len(after), len(after[0])):
        return tuple((x, y) for y, row in enumerate(after) for x, _ in enumerate(row))
    return tuple(
        (x, y)
        for y in range(len(after))
        for x in range(len(after[0]))
        if before[y][x] != after[y][x]
    )


def animation_signature(obs: Observation) -> str:
    """Digest temporal structure instead of silently discarding intermediate frames."""
    frame_digests = tuple(grid_digest(f) for f in obs.frames)
    temporal_deltas = tuple(changed_cells(obs.frames[i], obs.frames[i + 1]) for i in range(len(obs.frames) - 1))
    return sha256(_canonical_bytes((frame_digests, temporal_deltas))).hexdigest()


@dataclass(frozen=True)
class EffectSignature:
    changed_count: int
    colors_before: tuple[tuple[int, int], ...]
    colors_after: tuple[tuple[int, int], ...]
    bbox: tuple[int, int, int, int] | None
    level_delta: int
    terminal: str
    animation_frames: int
    digest: str


def effect_signature(before: Observation, after: Observation) -> EffectSignature:
    cells = changed_cells(before.frame, after.frame)
    if cells:
        xs, ys = zip(*cells)
        bbox = min(xs), min(ys), max(xs), max(ys)
    else:
        bbox = None
    cb = tuple(sorted(Counter(v for row in before.frame for v in row).items()))
    ca = tuple(sorted(Counter(v for row in after.frame for v in row).items()))
    level_delta = after.levels_completed - before.levels_completed
    raw = (len(cells), cb, ca, bbox, level_delta, after.state, len(after.frames), animation_signature(after))
    return EffectSignature(
        changed_count=len(cells),
        colors_before=cb,
        colors_after=ca,
        bbox=bbox,
        level_delta=level_delta,
        terminal=after.state,
        animation_frames=len(after.frames),
        digest=sha256(_canonical_bytes(raw)).hexdigest(),
    )


@dataclass(frozen=True)
class Transition:
    before: Observation
    action: ActionToken
    after: Observation
    effect: EffectSignature

    @classmethod
    def build(cls, before: Observation, action: ActionToken, after: Observation) -> "Transition":
        if action.name not in before.available_actions:
            raise ValueError("action was not available in before-state")
        return cls(before, action, after, effect_signature(before, after))


def trace_digest(trace: Sequence[Transition]) -> str:
    h = sha256()
    for t in trace:
        h.update(grid_digest(t.before.frame).encode())
        h.update(t.action.key.encode())
        h.update(t.effect.digest.encode())
        h.update(grid_digest(t.after.frame).encode())
        h.update(animation_signature(t.after).encode())
    return h.hexdigest()
