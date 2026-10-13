"""Deterministic visual-effect factorization for SAGE/ARC3-style transitions.

This module classifies *observed visual transition structure*. It does not claim that an
action is the unique physical cause of a visual change; ambiguous/global explanations
remain explicit in the result.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Sequence

Grid = tuple[tuple[int, ...], ...]
Point = tuple[int, int]
KINDS = (
    "MOTION", "SPAWN", "DESPAWN", "RECOLOR", "TOPOLOGY",
    "UI", "CAMERA", "COMPOUND", "NO_CHANGE", "AMBIGUOUS",
)
_KIND_ORDER = {name: i for i, name in enumerate(KINDS)}


def _validate_grid(grid: Sequence[Sequence[int]]) -> Grid:
    if not isinstance(grid, Sequence) or isinstance(grid, (str, bytes)) or not grid:
        raise ValueError("grid must be a non-empty row sequence")
    width = None
    rows: list[tuple[int, ...]] = []
    for raw in grid:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
            raise ValueError("grid rows must be non-empty sequences")
        row: list[int] = []
        for value in raw:
            if type(value) is not int or not 0 <= value <= 15:
                raise ValueError("grid values must be exact ints in [0,15]")
            row.append(value)
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError("grid must be rectangular")
        rows.append(tuple(row))
    if len(rows) > 64 or (width or 0) > 64:
        raise ValueError("grid exceeds 64x64 bound")
    return tuple(rows)


def _digest(grid: Grid) -> str:
    h = sha256(f"{len(grid)}x{len(grid[0])}|".encode())
    for row in grid:
        h.update(bytes(row))
    return h.hexdigest()


def _background(grid: Grid) -> int:
    global_counts = Counter(v for row in grid for v in row)
    if len(grid) >= 3 and len(grid[0]) >= 3:
        interior = Counter(grid[y][x] for y in range(1, len(grid) - 1) for x in range(1, len(grid[0]) - 1))
        if interior:
            return max(interior, key=lambda c: (interior[c], global_counts[c], -c))
    return max(global_counts, key=lambda c: (global_counts[c], -c))


@dataclass(frozen=True)
class Component:
    color: int
    cells: tuple[Point, ...]

    @property
    def area(self) -> int:
        return len(self.cells)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        xs = [p[0] for p in self.cells]
        ys = [p[1] for p in self.cells]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def origin(self) -> Point:
        x0, y0, _, _ = self.bbox
        return x0, y0

    @property
    def normalized_shape(self) -> tuple[Point, ...]:
        x0, y0 = self.origin
        return tuple((x - x0, y - y0) for x, y in self.cells)

    @property
    def digest(self) -> str:
        return sha256(f"{self.color}|{self.cells}".encode()).hexdigest()


def _components(grid: Grid) -> tuple[Component, ...]:
    bg = _background(grid)
    h, w = len(grid), len(grid[0])
    seen: set[Point] = set()
    out: list[Component] = []
    for y in range(h):
        for x in range(w):
            if (x, y) in seen:
                continue
            color = grid[y][x]
            if color == bg:
                seen.add((x, y))
                continue
            q = deque([(x, y)])
            seen.add((x, y))
            cells: list[Point] = []
            while q:
                cx, cy = q.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and grid[ny][nx] == color:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            out.append(Component(color, tuple(sorted(cells))))
    return tuple(sorted(out, key=lambda c: (c.color, c.bbox, c.area, c.cells)))


def _changed(before: Grid, after: Grid) -> tuple[Point, ...]:
    if (len(before), len(before[0])) != (len(after), len(after[0])):
        return tuple((x, y) for y, row in enumerate(after) for x, _ in enumerate(row))
    return tuple((x, y) for y in range(len(after)) for x in range(len(after[0])) if before[y][x] != after[y][x])


@dataclass(frozen=True)
class Witness:
    kind: str
    before_component: str | None
    after_component: str | None
    dx: int | None = None
    dy: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class PairEffect:
    kinds: tuple[str, ...]
    confidence_bps: int
    changed_count: int
    before_sha256: str
    after_sha256: str
    witnesses: tuple[Witness, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kinds": list(self.kinds),
            "confidence_bps": self.confidence_bps,
            "changed_count": self.changed_count,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "witnesses": [asdict(w) for w in self.witnesses],
        }


@dataclass(frozen=True)
class ActionSequence:
    action_key: str
    before: Grid
    frames: tuple[Grid, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key.startswith("ACTION"):
            raise ValueError("action_key must use ACTION* form")
        object.__setattr__(self, "before", _validate_grid(self.before))
        if not self.frames:
            raise ValueError("frames must retain at least one post-action frame")
        object.__setattr__(self, "frames", tuple(_validate_grid(f) for f in self.frames))
        shape = (len(self.before), len(self.before[0]))
        if any((len(f), len(f[0])) != shape for f in self.frames):
            raise ValueError("all frames in one action sequence must have the same shape")


@dataclass(frozen=True)
class ActionEffect:
    action_key: str
    kinds: tuple[str, ...]
    confidence_bps: int
    frame_effects: tuple[PairEffect, ...]
    input_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action_key": self.action_key,
            "kinds": list(self.kinds),
            "confidence_bps": self.confidence_bps,
            "input_sha256": self.input_sha256,
            "frame_effects": [x.to_dict() for x in self.frame_effects],
        }


def sequence_digest(seq: ActionSequence) -> str:
    h = sha256(seq.action_key.encode())
    h.update(_digest(seq.before).encode())
    for frame in seq.frames:
        h.update(_digest(frame).encode())
    return h.hexdigest()


def factor_pair(before_raw: Sequence[Sequence[int]], after_raw: Sequence[Sequence[int]]) -> PairEffect:
    before, after = _validate_grid(before_raw), _validate_grid(after_raw)
    if (len(before), len(before[0])) != (len(after), len(after[0])):
        return PairEffect(("AMBIGUOUS",), 1000, len(after) * len(after[0]), _digest(before), _digest(after),
                          (Witness("AMBIGUOUS", None, None, detail="frame shape changed"),))
    changes = _changed(before, after)
    if not changes:
        return PairEffect(("NO_CHANGE",), 10000, 0, _digest(before), _digest(after), ())

    bcomps, acomps = _components(before), _components(after)
    b_used: set[int] = set()
    a_used: set[int] = set()
    witnesses: list[Witness] = []
    motions: list[tuple[int, int, int, int]] = []

    candidates: list[tuple[int, int, int, int, int]] = []
    for bi, b in enumerate(bcomps):
        for ai, a in enumerate(acomps):
            if b.color != a.color or b.normalized_shape != a.normalized_shape:
                continue
            dx, dy = a.origin[0] - b.origin[0], a.origin[1] - b.origin[1]
            candidates.append((abs(dx) + abs(dy), bi, ai, dx, dy))
    for _, bi, ai, dx, dy in sorted(candidates):
        if bi in b_used or ai in a_used:
            continue
        b_used.add(bi)
        a_used.add(ai)
        if dx or dy:
            motions.append((bi, ai, dx, dy))

    recolors: list[tuple[int, int]] = []
    for bi, b in enumerate(bcomps):
        if bi in b_used:
            continue
        matches = [(ai, a) for ai, a in enumerate(acomps) if ai not in a_used and a.cells == b.cells and a.color != b.color]
        if matches:
            ai, _ = sorted(matches, key=lambda pair: pair[1].color)[0]
            b_used.add(bi)
            a_used.add(ai)
            recolors.append((bi, ai))

    topology_pairs: list[tuple[tuple[int, ...], tuple[int, ...], int]] = []
    for color in sorted({c.color for c in bcomps} | {c.color for c in acomps}):
        bis = tuple(i for i, c in enumerate(bcomps) if i not in b_used and c.color == color)
        ais = tuple(i for i, c in enumerate(acomps) if i not in a_used and c.color == color)
        if not bis or not ais or len(bis) == len(ais):
            continue
        bcells = set().union(*(set(bcomps[i].cells) for i in bis))
        acells = set().union(*(set(acomps[i].cells) for i in ais))
        overlap = len(bcells & acells)
        union = len(bcells | acells)
        if union and overlap * 2 >= union:
            topology_pairs.append((bis, ais, color))
            b_used.update(bis)
            a_used.update(ais)

    delta_votes = Counter((dx, dy) for _, _, dx, dy in motions)
    camera_delta: tuple[int, int] | None = None
    if delta_votes:
        delta, count = delta_votes.most_common(1)[0]
        moved_area = sum(bcomps[bi].area for bi, _, dx, dy in motions if (dx, dy) == delta)
        total_fg = max(1, sum(c.area for c in bcomps))
        if count >= 2 and count == len(motions) and moved_area * 10 >= total_fg * 7:
            camera_delta = delta

    h, w = len(before), len(before[0])
    border_changes = sum(1 for x, y in changes if x in (0, w-1) or y in (0, h-1))
    ui = camera_delta is None and border_changes * 10 >= len(changes) * 8

    kinds: set[str] = set()
    if camera_delta is not None:
        kinds.add("CAMERA")
        witnesses.append(Witness("CAMERA", None, None, camera_delta[0], camera_delta[1], f"{len(motions)} matched components share global translation"))
    elif ui:
        kinds.add("UI")
        witnesses.append(Witness("UI", None, None, detail=f"{border_changes}/{len(changes)} changed cells lie on border"))
    else:
        for bi, ai, dx, dy in motions:
            kinds.add("MOTION")
            witnesses.append(Witness("MOTION", bcomps[bi].digest, acomps[ai].digest, dx, dy, "same-color normalized shape translated"))

    for bi, ai in recolors:
        kinds.add("RECOLOR")
        witnesses.append(Witness("RECOLOR", bcomps[bi].digest, acomps[ai].digest, detail=f"color {bcomps[bi].color}->{acomps[ai].color} at same cells"))
    for bis, ais, color in topology_pairs:
        kinds.add("TOPOLOGY")
        witnesses.append(Witness("TOPOLOGY", None, None, detail=f"color {color} component count {len(bis)}->{len(ais)} with spatial continuity"))

    if not ui and camera_delta is None:
        for bi, b in enumerate(bcomps):
            if bi not in b_used:
                kinds.add("DESPAWN")
                witnesses.append(Witness("DESPAWN", b.digest, None, detail="unmatched before component"))
        for ai, a in enumerate(acomps):
            if ai not in a_used:
                kinds.add("SPAWN")
                witnesses.append(Witness("SPAWN", None, a.digest, detail="unmatched after component"))

    if not kinds:
        kinds.add("AMBIGUOUS")
        witnesses.append(Witness("AMBIGUOUS", None, None, detail="changed cells lack stable component correspondence"))

    semantic = tuple(sorted(kinds, key=_KIND_ORDER.__getitem__))
    if len(semantic) > 1:
        semantic = tuple(sorted(set(semantic) | {"COMPOUND"}, key=_KIND_ORDER.__getitem__))
    base_conf = {
        "CAMERA": 9200, "UI": 9300, "MOTION": 9500, "RECOLOR": 9500,
        "TOPOLOGY": 8500, "SPAWN": 9000, "DESPAWN": 9000,
        "AMBIGUOUS": 3000, "NO_CHANGE": 10000,
    }
    parts = [k for k in semantic if k != "COMPOUND"]
    confidence = min(base_conf[k] for k in parts)
    if "COMPOUND" in semantic:
        confidence = max(1000, confidence - 500)
    return PairEffect(semantic, confidence, len(changes), _digest(before), _digest(after), tuple(witnesses))


def factor_action(seq: ActionSequence) -> ActionEffect:
    frames = (seq.before,) + seq.frames
    effects = [factor_pair(before, after) for before, after in zip(frames, frames[1:])]
    active = [e for e in effects if e.kinds != ("NO_CHANGE",)]
    if not active:
        kinds = ("NO_CHANGE",)
        confidence = 10000
    else:
        union = {k for e in active for k in e.kinds if k not in {"COMPOUND", "NO_CHANGE"}}
        kinds = tuple(sorted(union, key=_KIND_ORDER.__getitem__))
        if len(kinds) > 1:
            kinds = tuple(sorted(set(kinds) | {"COMPOUND"}, key=_KIND_ORDER.__getitem__))
        confidence = min(e.confidence_bps for e in active)
        if len(active) > 1 and "COMPOUND" in kinds:
            confidence = max(1000, confidence - 250)
    return ActionEffect(seq.action_key, kinds, confidence, tuple(effects), sequence_digest(seq))
