"""Observed-position joint visit scheduling for the pinned Kaggriculture engine.

Jobs describe destinations and ordered operations, never movement tape offsets.
The caller retains investment/hiring and values complete joint replays. This
module has no access to hidden engine RNG or another player's private state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
from copy import deepcopy
from typing import Callable, Iterable, Mapping
import time

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
CAPITAL = {"PLANT", "BUILD_COOP", "BUILD_PASTURE", "DIG"}
ANIMALS = {"COW", "SHEEP", "GOOSE"}


@dataclass(frozen=True)
class Operation:
    action: tuple
    original_step: int
    release: int
    deadline: int


@dataclass(frozen=True)
class Visit:
    id: str
    target: tuple[int, int]
    operations: tuple[Operation, ...]
    original_worker: int

    @property
    def capital(self) -> bool:
        return any(o.action[0] in CAPITAL or
                   (o.action[0] == "PLACE" and len(o.action) > 1 and o.action[1] in ANIMALS)
                   for o in self.operations)

    @property
    def input_item(self) -> str | None:
        for o in self.operations:
            if o.action[0] == "FEED":
                return "WHEAT"
            if o.action[0] == "FERTILIZE":
                return "FERTILIZER"
        return None


def _spawn(positions: list[list[int]], board: int) -> list[int]:
    h = board // 2
    tiles = ((h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h))
    counts = Counter(map(tuple, positions))
    return list(min(tiles, key=lambda p: (counts[p], tiles.index(p))))


def decode_day(route: list[dict], day: int, *, board: int = 10,
               turns_per_day: int = 24, episode_steps: int = 720) -> dict[int, tuple[Visit, ...]]:
    """Decode planned capital/service targets with the engine's hire-spawn order.

    All intended HIRE orders are assumed paid for *decoding only*. Execution
    always uses the actually present workers/positions. Movement occurs before
    market hires. Within-day PLANT dates are equivalent in the official engine;
    their deadline remains this day, not an unspecified future investment.
    """
    first, last = day * turns_per_day, min((day + 1) * turns_per_day - 1, episode_steps - 2)
    birth_last = max((t for t in range(first, last + 1)
                      if any(o and o[0] == "HIRE" for o in route[t].get("market", [])[:10])), default=first - 1)
    birth_last = max(min(first + 1, last), birth_last)
    positions = [[board // 2 - 1, board // 2 - 1]]
    raw: dict[int, list[tuple[int, tuple, tuple]]] = {0: []}
    for step in range(first, last + 1):
        action = route[step]
        units = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
        units += [["PASS"]] * max(0, len(positions) - len(units))
        for worker, unit in enumerate(units[:len(positions)]):
            if not unit:
                continue
            if unit[0] in MOVES:
                dx, dy = MOVES[unit[0]]
                x, y = positions[worker]
                if 0 <= x + dx < board and 0 <= y + dy < board:
                    positions[worker] = [x + dx, y + dy]
                if step <= birth_last:
                    raw.setdefault(worker, []).append((step, tuple(positions[worker]), ("ARRIVE",)))
            elif unit[0] != "PASS" or step <= birth_last:
                raw.setdefault(worker, []).append((step, tuple(positions[worker]), tuple(unit)))
        for order in action.get("market", [])[:10]:
            if order and order[0] == "HIRE":
                positions.append(_spawn(positions, board))
                raw[len(positions) - 1] = []
    result = {}
    for worker, items in raw.items():
        visits = []
        for step, target, action in items:
            op = Operation(action, step, step, last)
            if visits and visits[-1].target == target and visits[-1].operations[-1].original_step == step - 1:
                visits[-1] = replace(visits[-1], operations=(*visits[-1].operations, op))
            else:
                visits.append(Visit(f"{day}:{worker}:{step}", target, (op,), worker))
        result[worker] = tuple(visits)
    return result


def remaining(queues: Mapping[int, tuple[Visit, ...]], step: int,
              workers: int) -> dict[int, tuple[Visit, ...]]:
    """Select not-yet-due jobs for the actual existing workforce."""
    result = {}
    for worker in range(workers):
        visits = []
        for visit in queues.get(worker, ()):
            ops = tuple(o for o in visit.operations if o.original_step >= step)
            if ops:
                visits.append(replace(visit, operations=ops))
        result[worker] = tuple(visits)
    return result


def relax(visit: Visit, step: int) -> Visit:
    """A moved service visit may run earlier; shed inputs retain release dates."""
    return replace(visit, operations=tuple(
        replace(op, release=op.release if op.action[0] == "PICKUP" else step)
        for op in visit.operations))


class JointPlan:
    """Persistent all-worker job cursors; each action reads the real observation.

    Assignment changes do not change where a worker actually stands. Expired
    jobs are recorded as missed. No action is emitted for a nonexistent hand.
    A supplied plan is copied so lookahead cannot advance its live cursors.
    """
    def __init__(self, queues: Mapping[int, tuple[Visit, ...]]):
        self.queues = {int(k): tuple(v) for k, v in queues.items()}
        self.cursor = {k: [0, 0] for k in self.queues}
        self.completed: list[str] = []
        self.missed: list[str] = []
        self.last_step = -1
        self.last_actions: list[list] | None = None

    def fork(self) -> "JointPlan":
        out = JointPlan(self.queues)
        out.cursor = {k: list(v) for k, v in self.cursor.items()}
        out.completed, out.missed = list(self.completed), list(self.missed)
        out.last_step = self.last_step
        out.last_actions = deepcopy(self.last_actions)
        return out

    def pending(self) -> dict[int, tuple[Visit, ...]]:
        result = {}
        for worker, visits in self.queues.items():
            vi, oi = self.cursor[worker]
            result[worker] = (() if vi >= len(visits) else
                             (replace(visits[vi], operations=visits[vi].operations[oi:]), *visits[vi + 1:]))
        return result

    def actions(self, obs: Mapping) -> list[list]:
        step = int(obs["step"])
        if step == self.last_step:
            return deepcopy(self.last_actions)
        if step < self.last_step:
            raise ValueError("A live joint plan cannot rewind; fork for speculative replay")
        farm = obs["farms"][int(obs["player"])]
        positions = [farm["farmer"], *farm.get("hands", [])]
        output = []
        for worker, position in enumerate(positions):
            visits = self.queues.get(worker, ())
            vi, oi = self.cursor.setdefault(worker, [0, 0])
            chosen = ["PASS"]
            while vi < len(visits):
                visit = visits[vi]
                operation = visit.operations[oi]
                if step > operation.deadline:
                    self.missed.append(f"{visit.id}/{oi}")
                    oi += 1
                    if oi == len(visit.operations):
                        vi, oi = vi + 1, 0
                    continue
                x, y = map(int, position)
                tx, ty = visit.target
                if operation.action[0] == "ARRIVE":
                    if step < operation.release:
                        chosen = ["PASS"]
                    else:
                        if x != tx:
                            chosen = ["EAST" if x < tx else "WEST"]
                        elif y != ty:
                            chosen = ["SOUTH" if y < ty else "NORTH"]
                        if abs(tx - x) + abs(ty - y) <= 1:
                            self.completed.append(f"{visit.id}/{oi}")
                            oi += 1
                            if oi == len(visit.operations):
                                vi, oi = vi + 1, 0
                elif x != tx:
                    chosen = ["EAST" if x < tx else "WEST"]
                elif y != ty:
                    chosen = ["SOUTH" if y < ty else "NORTH"]
                elif step < operation.release:
                    chosen = ["PASS"]
                else:
                    chosen = list(operation.action)
                    tile = farm["tiles"][y][x]
                    # A new observed weed is a real route dependency, not a
                    # reason to leap into an old movement offset after detouring.
                    if chosen[0] == "PLANT" and isinstance(tile, dict) and tile.get("kind") == "WEED":
                        chosen = ["DIG"]
                    else:
                        self.completed.append(f"{visit.id}/{oi}")
                        oi += 1
                        if oi == len(visit.operations):
                            vi, oi = vi + 1, 0
                break
            self.cursor[worker] = [vi, oi]
            output.append(chosen)
        self.last_step, self.last_actions = step, deepcopy(output)
        return output


def route_distance(queues: Mapping[int, tuple[Visit, ...]], positions: list) -> int:
    total = 0
    for worker, visits in queues.items():
        if worker >= len(positions):
            continue
        x, y = positions[worker]
        for visit in visits:
            tx, ty = visit.target
            total += abs(tx - x) + abs(ty - y) + len(visit.operations)
            x, y = tx, ty
    return total


def deadline_feasible(queues: Mapping[int, tuple[Visit, ...]], obs: Mapping) -> bool:
    """Necessary travel/release bound before expensive resource-aware replay.

    This does not assume feed, seeds or free shed capacity. Passing the bound
    only means the jobs could fit geometrically; the official engine still
    determines their resource effects and the complete economic result.
    """
    farm = obs["farms"][int(obs["player"])]
    positions = [farm["farmer"], *farm.get("hands", [])]
    for worker, visits in queues.items():
        if worker >= len(positions):
            if visits:
                return False
            continue
        x, y = positions[worker]
        clock = int(obs["step"])
        for visit in visits:
            tx, ty = visit.target
            distance = abs(tx - x) + abs(ty - y)
            x, y = tx, ty
            for index, op in enumerate(visit.operations):
                if index == 0 and op.action[0] == "ARRIVE":
                    clock = max(clock, op.release) + max(1, distance)
                else:
                    if index == 0:
                        clock += distance
                    clock = max(clock, op.release) + 1
                if clock - 1 > op.deadline:
                    return False
    return True


def neighbors(queues: Mapping[int, tuple[Visit, ...]], obs: Mapping,
              *, limit: int = 12) -> list[tuple[str, dict[int, tuple[Visit, ...]]]]:
    """Deterministic bounded destroy/reinsert and cross-worker visit swaps.

    Capital and pickup/deposit visits remain in their original queues. Ordinary
    service moves are proposals, not assumed feasible; exact joint replay and
    terminal obligations decide whether one can replace the complete incumbent.
    """
    step = int(obs["step"])
    farm = obs["farms"][int(obs["player"])]
    positions = [farm["farmer"], *farm.get("hands", [])]
    slots = [(w, i, v) for w, row in queues.items() for i, v in enumerate(row)
             if not v.capital and all(o.action[0] in {"WATER", "CARE", "FEED", "HARVEST", "COLLECT_FERTILIZER", "FERTILIZE"}
                                      for o in v.operations)]
    candidates = []
    base_distance = route_distance(queues, positions)
    for worker, index, visit in slots:
        for target in range(len(positions)):
            # Relocating within the same queue is also a bounded reordering.
            for insertion in range(len(queues.get(target, ())) + 1):
                if target == worker and insertion in (index, index + 1):
                    continue
                changed = {w: list(q) for w, q in queues.items()}
                moved = changed[worker].pop(index)
                at = insertion - int(target == worker and insertion > index)
                changed.setdefault(target, []).insert(at, relax(moved, step))
                out = {w: tuple(q) for w, q in changed.items()}
                gain = base_distance - route_distance(out, positions)
                if gain > 0 and deadline_feasible(out, obs):
                    candidates.append((gain, f"reinsert:{visit.id}:{target}:{insertion}", out))
    for a, (wa, ia, va) in enumerate(slots):
        for wb, ib, vb in slots[a + 1:]:
            if wa == wb:
                continue
            changed = {w: list(q) for w, q in queues.items()}
            changed[wa][ia], changed[wb][ib] = relax(vb, step), relax(va, step)
            out = {w: tuple(q) for w, q in changed.items()}
            gain = base_distance - route_distance(out, positions)
            if gain > 0 and deadline_feasible(out, obs):
                candidates.append((gain, f"swap:{va.id}:{vb.id}", out))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return [(name, q) for _, name, q in candidates[:limit]]


def capital_signature(farm: Mapping, private: Mapping) -> tuple:
    """Investment/hiring state, excluding cash and harvested product quantities."""
    tiles = []
    for row in farm["tiles"]:
        for tile in row:
            if not isinstance(tile, dict):
                tiles.append(tile)
            else:
                tiles.append(tuple((key, tile.get(key)) for key in
                                   ("kind", "crop", "planted_day", "animal", "placed_day")))
    return (tuple(tiles), tuple(sorted(private.get("seeds", {}).items())),
            tuple(farm.get("unlocked_quadrants", [])), len(farm.get("hands", [])), farm.get("hires_today", 0))


def outstanding_stock(result: Mapping) -> Counter:
    """Physical unsold units, not a terminal cash valuation."""
    stock = Counter(result["private"]["shed"])
    for inventory in result["private"]["inventories"]:
        stock.update(inventory)
    for row in result["farm"]["tiles"]:
        for tile in row:
            if isinstance(tile, dict):
                product = {"COW": "MILK", "SHEEP": "WOOL", "GOOSE": "EGG"}.get(tile.get("animal"), tile.get("crop"))
                if product:
                    stock[product] += tile.get("yield_units", 0)
    return stock


def preserves_obligations(control: Mapping, candidate: Mapping) -> bool:
    """Conservative unpriced-state dominance, in addition to actual cash gain.

    A short horizon cannot price away feed survival, crop development or unsold
    stock by pretending a free final sale. This deliberately rejects uncertain
    tradeoffs; a richer T04 scenario value can replace this comparator explicitly.
    """
    if capital_signature(control["farm"], control["private"]) != capital_signature(candidate["farm"], candidate["private"]):
        return False
    a, b = outstanding_stock(control), outstanding_stock(candidate)
    if candidate.get("end_step") != 718 and any(b[item] < units for item, units in a.items()):
        return False
    if candidate.get("capital_checkpoints", {}) != control.get("capital_checkpoints", {}):
        return False
    if candidate.get("end_step") == 718:
        return True  # The official game gives unsold terminal stock no cash.
    for ra, rb in zip(control["farm"]["tiles"], candidate["farm"]["tiles"]):
        for ta, tb in zip(ra, rb):
            if not isinstance(ta, dict) or not isinstance(tb, dict):
                continue
            if tb.get("consecutive_unfed", 0) > ta.get("consecutive_unfed", 0):
                return False
            for key in ("pending_care_bonus", "watered_today", "fed_today", "cared_today", "fertilizer_available", "growth"):
                if tb.get(key, 0) < ta.get(key, 0):
                    return False
    return True


@dataclass
class SearchResult:
    label: str
    queues: dict[int, tuple[Visit, ...]]
    value: float
    evaluated: int
    rejected: int
    elapsed_seconds: float
    exhausted: bool
    receipt: dict


def search(incumbent: Mapping[int, tuple[Visit, ...]], observation: Mapping,
           evaluate: Callable, *, max_candidates: int = 2,
           budget_seconds: float = .72) -> SearchResult:
    """Retain only a complete, obligation-preserving exact replay under budget."""
    if max_candidates < 0 or budget_seconds <= 0:
        raise ValueError("Search requires a nonnegative count and positive time budget")
    started = time.perf_counter()
    base = evaluate(incumbent)
    best, receipt, label = dict(incumbent), base, "incumbent"
    evaluated, rejected = 1, 0
    for name, proposal in neighbors(incumbent, observation, limit=max_candidates):
        if time.perf_counter() - started >= budget_seconds:
            break
        outcome = evaluate(proposal)
        evaluated += 1
        if time.perf_counter() - started >= budget_seconds:
            break  # A late completed proposal cannot replace the in-budget incumbent.
        new_misses = Counter(outcome.get("missed_jobs", [])) - Counter(base.get("missed_jobs", []))
        if new_misses or not preserves_obligations(base, outcome):
            rejected += 1
            continue
        if outcome["cash_gain"] > receipt["cash_gain"]:
            best, receipt, label = proposal, outcome, name
    elapsed = time.perf_counter() - started
    return SearchResult(label, best, receipt["cash_gain"], evaluated, rejected,
                        elapsed, elapsed >= budget_seconds, receipt)
