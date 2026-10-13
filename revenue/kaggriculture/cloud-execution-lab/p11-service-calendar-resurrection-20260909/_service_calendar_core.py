# SPDX-License-Identifier: Apache-2.0
"""Deterministic finite-horizon obligation scheduler for TITAN P11.

This module is deliberately standalone and default-off.  It does not import the
canonical TITAN controller or mutate a route.  Instead it certifies whether a
candidate bundle of obligations can fit inside an explicitly supplied resource
calendar.  Callers get the three P11 outputs (`ready`, `overdue`, and
`structural_conflicts`) plus a source-bound schedule certificate.

The model is intentionally conservative:

* every dependency must be explicit;
* actors and machines are capacity constrained per turn;
* cash, inventory, and room are checked in engine phase order;
* production in a phase cannot pay for consumption in that same phase;
* effects with settlement lag must settle by the terminal turn; and
* bounded search fails closed rather than guessing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "titan-p11-service-calendar/v1"
DEFAULT_PHASE_ORDER = (
    "pre",
    "buy",
    "pickup",
    "place",
    "service",
    "harvest",
    "drop",
    "sell",
    "post",
)


class CalendarInputError(ValueError):
    """Raised when a payload cannot be interpreted without guessing."""


def _integer(value: Any, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalendarInputError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise CalendarInputError(f"{name} must be >= {minimum}")
    return value


def _name(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalendarInputError(f"{name} must be a non-empty string")
    return value.strip()


def _pairs(
    value: Mapping[str, Any] | Sequence[Sequence[Any]] | None,
    name: str,
    *,
    minimum: int | None = None,
    omit_zero: bool = False,
) -> tuple[tuple[str, int], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        rows = list(value.items())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = []
        for index, row in enumerate(value):
            if (
                not isinstance(row, Sequence)
                or isinstance(row, (str, bytes, bytearray))
                or len(row) != 2
            ):
                raise CalendarInputError(f"{name}[{index}] must be a [name, units] pair")
            rows.append((row[0], row[1]))
    else:
        raise CalendarInputError(f"{name} must be an object or list of pairs")

    normalized: dict[str, int] = {}
    for raw_key, raw_amount in rows:
        key = _name(raw_key, f"{name} key")
        if key in normalized:
            raise CalendarInputError(f"{name} contains duplicate key {key!r}")
        amount = _integer(raw_amount, f"{name}.{key}", minimum)
        if omit_zero and amount == 0:
            continue
        normalized[key] = amount
    return tuple(sorted(normalized.items()))


def _mapping(pairs: Iterable[tuple[str, int]]) -> dict[str, int]:
    return dict(pairs)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, order=True)
class Reservation:
    """Capacity already committed by the canonical route."""

    turn: int
    resource: str
    units: int = 1

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], name: str) -> "Reservation":
        if not isinstance(value, Mapping):
            raise CalendarInputError(f"{name} must be an object")
        return cls(
            turn=_integer(value.get("turn"), f"{name}.turn", 0),
            resource=_name(value.get("resource"), f"{name}.resource"),
            units=_integer(value.get("units", 1), f"{name}.units", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"turn": self.turn, "resource": self.resource, "units": self.units}


@dataclass(frozen=True)
class CalendarState:
    """Observed resource snapshot and finite planning horizon."""

    current_turn: int
    terminal_turn: int
    cash: int = 0
    inventory: tuple[tuple[str, int], ...] = ()
    room_used: tuple[tuple[str, int], ...] = ()
    room_capacity: tuple[tuple[str, int], ...] = ()
    actor_capacity: tuple[tuple[str, int], ...] = ()
    machine_capacity: tuple[tuple[str, int], ...] = ()
    actor_reservations: tuple[Reservation, ...] = ()
    machine_reservations: tuple[Reservation, ...] = ()
    completed: tuple[str, ...] = ()
    phase_order: tuple[str, ...] = DEFAULT_PHASE_ORDER

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CalendarState":
        if not isinstance(value, Mapping):
            raise CalendarInputError("state must be an object")
        phases_value = value.get("phase_order", DEFAULT_PHASE_ORDER)
        if (
            not isinstance(phases_value, Sequence)
            or isinstance(phases_value, (str, bytes, bytearray))
            or not phases_value
        ):
            raise CalendarInputError("state.phase_order must be a non-empty list")
        phases = tuple(_name(item, f"state.phase_order[{index}]") for index, item in enumerate(phases_value))
        if len(set(phases)) != len(phases):
            raise CalendarInputError("state.phase_order contains duplicates")

        completed_value = value.get("completed", ())
        if (
            not isinstance(completed_value, Sequence)
            or isinstance(completed_value, (str, bytes, bytearray))
        ):
            raise CalendarInputError("state.completed must be a list")
        completed = tuple(sorted({_name(item, "state.completed entry") for item in completed_value}))

        actor_reservations_value = value.get("actor_reservations", ())
        machine_reservations_value = value.get("machine_reservations", ())
        if not isinstance(actor_reservations_value, Sequence) or isinstance(
            actor_reservations_value, (str, bytes, bytearray)
        ):
            raise CalendarInputError("state.actor_reservations must be a list")
        if not isinstance(machine_reservations_value, Sequence) or isinstance(
            machine_reservations_value, (str, bytes, bytearray)
        ):
            raise CalendarInputError("state.machine_reservations must be a list")

        state = cls(
            current_turn=_integer(value.get("current_turn"), "state.current_turn", 0),
            terminal_turn=_integer(value.get("terminal_turn"), "state.terminal_turn", 0),
            cash=_integer(value.get("cash", 0), "state.cash", 0),
            inventory=_pairs(value.get("inventory"), "state.inventory", minimum=0, omit_zero=True),
            room_used=_pairs(value.get("room_used"), "state.room_used", minimum=0, omit_zero=True),
            room_capacity=_pairs(value.get("room_capacity"), "state.room_capacity", minimum=0),
            actor_capacity=_pairs(value.get("actor_capacity"), "state.actor_capacity", minimum=0),
            machine_capacity=_pairs(value.get("machine_capacity"), "state.machine_capacity", minimum=0),
            actor_reservations=tuple(
                sorted(
                    Reservation.from_dict(row, f"state.actor_reservations[{index}]")
                    for index, row in enumerate(actor_reservations_value)
                )
            ),
            machine_reservations=tuple(
                sorted(
                    Reservation.from_dict(row, f"state.machine_reservations[{index}]")
                    for index, row in enumerate(machine_reservations_value)
                )
            ),
            completed=completed,
            phase_order=phases,
        )
        if state.current_turn > state.terminal_turn:
            raise CalendarInputError("state.current_turn must not exceed state.terminal_turn")
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_turn": self.current_turn,
            "terminal_turn": self.terminal_turn,
            "cash": self.cash,
            "inventory": _mapping(self.inventory),
            "room_used": _mapping(self.room_used),
            "room_capacity": _mapping(self.room_capacity),
            "actor_capacity": _mapping(self.actor_capacity),
            "machine_capacity": _mapping(self.machine_capacity),
            "actor_reservations": [row.to_dict() for row in self.actor_reservations],
            "machine_reservations": [row.to_dict() for row in self.machine_reservations],
            "completed": list(self.completed),
            "phase_order": list(self.phase_order),
        }


@dataclass(frozen=True)
class Obligation:
    """One explicitly bounded action obligation.

    Resource deltas settle at the action phase when ``settlement_lag`` is zero.
    With positive lag, they settle at the end of the later turn.  Negative deltas
    consume resources; positive deltas produce resources or occupy room.
    """

    key: str
    kind: str
    earliest_turn: int
    latest_turn: int
    phase: str
    depends_on: tuple[str, ...] = ()
    actor_demand: tuple[tuple[str, int], ...] = ()
    machine_demand: tuple[tuple[str, int], ...] = ()
    cash_delta: int = 0
    inventory_delta: tuple[tuple[str, int], ...] = ()
    room_delta: tuple[tuple[str, int], ...] = ()
    settlement_lag: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], index: int = 0) -> "Obligation":
        if not isinstance(value, Mapping):
            raise CalendarInputError(f"obligations[{index}] must be an object")
        prefix = f"obligations[{index}]"
        deps_value = value.get("depends_on", ())
        if not isinstance(deps_value, Sequence) or isinstance(deps_value, (str, bytes, bytearray)):
            raise CalendarInputError(f"{prefix}.depends_on must be a list")
        deps = tuple(sorted({_name(item, f"{prefix}.depends_on entry") for item in deps_value}))
        return cls(
            key=_name(value.get("key"), f"{prefix}.key"),
            kind=_name(value.get("kind", "service"), f"{prefix}.kind"),
            earliest_turn=_integer(value.get("earliest_turn"), f"{prefix}.earliest_turn", 0),
            latest_turn=_integer(value.get("latest_turn"), f"{prefix}.latest_turn", 0),
            phase=_name(value.get("phase", "service"), f"{prefix}.phase"),
            depends_on=deps,
            actor_demand=_pairs(value.get("actor_demand"), f"{prefix}.actor_demand", minimum=1),
            machine_demand=_pairs(value.get("machine_demand"), f"{prefix}.machine_demand", minimum=1),
            cash_delta=_integer(value.get("cash_delta", 0), f"{prefix}.cash_delta"),
            inventory_delta=_pairs(value.get("inventory_delta"), f"{prefix}.inventory_delta", omit_zero=True),
            room_delta=_pairs(value.get("room_delta"), f"{prefix}.room_delta", omit_zero=True),
            settlement_lag=_integer(value.get("settlement_lag", 0), f"{prefix}.settlement_lag", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "earliest_turn": self.earliest_turn,
            "latest_turn": self.latest_turn,
            "phase": self.phase,
            "depends_on": list(self.depends_on),
            "actor_demand": _mapping(self.actor_demand),
            "machine_demand": _mapping(self.machine_demand),
            "cash_delta": self.cash_delta,
            "inventory_delta": _mapping(self.inventory_delta),
            "room_delta": _mapping(self.room_delta),
            "settlement_lag": self.settlement_lag,
        }


@dataclass(frozen=True, order=True)
class Conflict:
    code: str
    obligation: str = ""
    resource: str = ""
    turn: int = -1
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code}
        if self.obligation:
            result["obligation"] = self.obligation
        if self.resource:
            result["resource"] = self.resource
        if self.turn >= 0:
            result["turn"] = self.turn
        if self.detail:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True)
class ScheduledSlot:
    turn: int
    phase: str
    settles_turn: int
    settles_phase: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "phase": self.phase,
            "settles_turn": self.settles_turn,
            "settles_phase": self.settles_phase,
        }


@dataclass(frozen=True)
class CalendarDecision:
    admitted: bool
    ready: tuple[str, ...]
    overdue: tuple[str, ...]
    structural_conflicts: tuple[Conflict, ...]
    schedule: tuple[tuple[str, ScheduledSlot], ...]
    remaining_slack: tuple[tuple[str, int], ...]
    source_hash: str
    certificate_hash: str
    search_nodes: int
    schema: str = SCHEMA

    def to_dict(self, *, include_certificate_hash: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema,
            "admitted": self.admitted,
            "ready": list(self.ready),
            "overdue": list(self.overdue),
            "structural_conflicts": [row.to_dict() for row in self.structural_conflicts],
            "schedule": {key: slot.to_dict() for key, slot in self.schedule},
            "remaining_slack": _mapping(self.remaining_slack),
            "source_hash": self.source_hash,
            "search_nodes": self.search_nodes,
        }
        if include_certificate_hash:
            result["certificate_hash"] = self.certificate_hash
        return result


@dataclass
class _Search:
    state: CalendarState
    obligations: dict[str, Obligation]
    order: tuple[str, ...]
    minimum_turn: dict[str, int]
    maximum_turn: dict[str, int]
    phase_rank: dict[str, int]
    max_nodes: int
    actor_load: dict[tuple[int, str], int] = field(default_factory=lambda: defaultdict(int))
    machine_load: dict[tuple[int, str], int] = field(default_factory=lambda: defaultdict(int))
    assignment: dict[str, int] = field(default_factory=dict)
    nodes: int = 0
    limit_hit: bool = False
    best_resource_conflicts: tuple[Conflict, ...] | None = None
    first_dead_end: Conflict | None = None

    def action_ordinal(self, obligation: Obligation, turn: int) -> int:
        return turn * len(self.phase_rank) + self.phase_rank[obligation.phase]

    def settlement_ordinal(self, obligation: Obligation, turn: int) -> int:
        if obligation.settlement_lag:
            return (turn + obligation.settlement_lag) * len(self.phase_rank) + len(self.phase_rank) - 1
        return self.action_ordinal(obligation, turn)

    def _capacity_ok(self, obligation: Obligation, turn: int) -> tuple[bool, str, str]:
        actor_capacity = _mapping(self.state.actor_capacity)
        machine_capacity = _mapping(self.state.machine_capacity)
        for resource, units in obligation.actor_demand:
            if self.actor_load[(turn, resource)] + units > actor_capacity[resource]:
                return False, "actor_capacity", resource
        for resource, units in obligation.machine_demand:
            if self.machine_load[(turn, resource)] + units > machine_capacity[resource]:
                return False, "machine_capacity", resource
        return True, "", ""

    def _dependency_ok(self, obligation: Obligation, turn: int) -> bool:
        action = self.action_ordinal(obligation, turn)
        completed = set(self.state.completed)
        for parent_key in obligation.depends_on:
            if parent_key in completed:
                continue
            parent = self.obligations[parent_key]
            parent_turn = self.assignment.get(parent_key)
            if parent_turn is None or self.settlement_ordinal(parent, parent_turn) >= action:
                return False
        return True

    def _record_resource_conflicts(self, conflicts: tuple[Conflict, ...]) -> None:
        if not conflicts:
            return
        if self.best_resource_conflicts is None:
            self.best_resource_conflicts = conflicts
            return
        old = _canonical([row.to_dict() for row in self.best_resource_conflicts])
        new = _canonical([row.to_dict() for row in conflicts])
        if new < old:
            self.best_resource_conflicts = conflicts

    def solve(self, index: int = 0) -> dict[str, int] | None:
        if self.nodes >= self.max_nodes:
            self.limit_hit = True
            return None
        self.nodes += 1
        if index == len(self.order):
            conflicts = _simulate_resources(self.state, self.obligations, self.assignment, self.phase_rank)
            if conflicts:
                self._record_resource_conflicts(conflicts)
                return None
            return dict(self.assignment)

        key = self.order[index]
        obligation = self.obligations[key]
        attempted = False
        blocked: tuple[str, str, int] | None = None
        for turn in range(self.minimum_turn[key], self.maximum_turn[key] + 1):
            if not self._dependency_ok(obligation, turn):
                blocked = ("dependency_order", "", turn)
                continue
            capacity_ok, code, resource = self._capacity_ok(obligation, turn)
            if not capacity_ok:
                blocked = (code, resource, turn)
                continue
            attempted = True
            self.assignment[key] = turn
            for resource, units in obligation.actor_demand:
                self.actor_load[(turn, resource)] += units
            for resource, units in obligation.machine_demand:
                self.machine_load[(turn, resource)] += units
            result = self.solve(index + 1)
            if result is not None:
                return result
            for resource, units in obligation.actor_demand:
                self.actor_load[(turn, resource)] -= units
            for resource, units in obligation.machine_demand:
                self.machine_load[(turn, resource)] -= units
            del self.assignment[key]
            if self.limit_hit:
                return None

        if not attempted and self.first_dead_end is None:
            code, resource, turn = blocked or ("no_legal_slot", "", self.minimum_turn[key])
            self.first_dead_end = Conflict(
                "no_legal_slot",
                key,
                resource,
                turn,
                f"blocked_by={code}; window={self.minimum_turn[key]}..{self.maximum_turn[key]}",
            )
        return None


def _normalize_obligations(values: Sequence[Mapping[str, Any] | Obligation]) -> tuple[Obligation, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise CalendarInputError("obligations must be a list")
    result: list[Obligation] = []
    for index, value in enumerate(values):
        result.append(value if isinstance(value, Obligation) else Obligation.from_dict(value, index))
    return tuple(sorted(result, key=lambda row: row.key))


def _precheck(
    state: CalendarState, obligations: tuple[Obligation, ...]
) -> tuple[
    dict[str, Obligation],
    tuple[str, ...],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    tuple[Conflict, ...],
]:
    conflicts: set[Conflict] = set()
    phase_rank = {name: index for index, name in enumerate(state.phase_order)}
    actor_capacity = _mapping(state.actor_capacity)
    machine_capacity = _mapping(state.machine_capacity)
    room_capacity = _mapping(state.room_capacity)
    room_used = _mapping(state.room_used)

    keys = [row.key for row in obligations]
    for key in sorted({key for key in keys if keys.count(key) > 1}):
        conflicts.add(Conflict("duplicate_obligation", key))
    by_key = {row.key: row for row in obligations}
    completed = set(state.completed)

    for resource, used in room_used.items():
        if resource not in room_capacity:
            conflicts.add(Conflict("unknown_room", resource=resource))
        elif used > room_capacity[resource]:
            conflicts.add(
                Conflict(
                    "initial_room_overflow",
                    resource=resource,
                    detail=f"used={used}; capacity={room_capacity[resource]}",
                )
            )

    reservation_actor: dict[tuple[int, str], int] = defaultdict(int)
    reservation_machine: dict[tuple[int, str], int] = defaultdict(int)
    for row in state.actor_reservations:
        reservation_actor[(row.turn, row.resource)] += row.units
        if row.resource not in actor_capacity:
            conflicts.add(Conflict("unknown_actor", resource=row.resource, turn=row.turn))
        elif reservation_actor[(row.turn, row.resource)] > actor_capacity[row.resource]:
            conflicts.add(
                Conflict(
                    "reserved_actor_overflow",
                    resource=row.resource,
                    turn=row.turn,
                    detail=(
                        f"reserved={reservation_actor[(row.turn, row.resource)]}; "
                        f"capacity={actor_capacity[row.resource]}"
                    ),
                )
            )
    for row in state.machine_reservations:
        reservation_machine[(row.turn, row.resource)] += row.units
        if row.resource not in machine_capacity:
            conflicts.add(Conflict("unknown_machine", resource=row.resource, turn=row.turn))
        elif reservation_machine[(row.turn, row.resource)] > machine_capacity[row.resource]:
            conflicts.add(
                Conflict(
                    "reserved_machine_overflow",
                    resource=row.resource,
                    turn=row.turn,
                    detail=(
                        f"reserved={reservation_machine[(row.turn, row.resource)]}; "
                        f"capacity={machine_capacity[row.resource]}"
                    ),
                )
            )

    for row in obligations:
        if row.earliest_turn > row.latest_turn:
            conflicts.add(
                Conflict(
                    "invalid_window",
                    row.key,
                    detail=f"earliest={row.earliest_turn}; latest={row.latest_turn}",
                )
            )
        if row.phase not in phase_rank:
            conflicts.add(Conflict("unknown_phase", row.key, row.phase))
        for parent in row.depends_on:
            if parent == row.key:
                conflicts.add(Conflict("self_dependency", row.key))
            elif parent not in by_key and parent not in completed:
                conflicts.add(Conflict("missing_dependency", row.key, parent))
        for resource, units in row.actor_demand:
            if resource not in actor_capacity:
                conflicts.add(Conflict("unknown_actor", row.key, resource))
            elif units > actor_capacity[resource]:
                conflicts.add(
                    Conflict(
                        "actor_demand_exceeds_capacity",
                        row.key,
                        resource,
                        detail=f"demand={units}; capacity={actor_capacity[resource]}",
                    )
                )
        for resource, units in row.machine_demand:
            if resource not in machine_capacity:
                conflicts.add(Conflict("unknown_machine", row.key, resource))
            elif units > machine_capacity[resource]:
                conflicts.add(
                    Conflict(
                        "machine_demand_exceeds_capacity",
                        row.key,
                        resource,
                        detail=f"demand={units}; capacity={machine_capacity[resource]}",
                    )
                )
        for resource, _ in row.room_delta:
            if resource not in room_capacity:
                conflicts.add(Conflict("unknown_room", row.key, resource))

    active = {key: row for key, row in by_key.items() if key not in completed}
    indegree = {key: 0 for key in active}
    children: dict[str, list[str]] = {key: [] for key in active}
    for key, row in active.items():
        for parent in row.depends_on:
            if parent in active:
                indegree[key] += 1
                children[parent].append(key)

    ready = sorted(key for key, degree in indegree.items() if degree == 0)
    topo: list[str] = []
    while ready:
        key = ready.pop(0)
        topo.append(key)
        for child in sorted(children[key]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(topo) != len(active):
        cyclic = sorted(key for key, degree in indegree.items() if degree > 0)
        for key in cyclic:
            conflicts.add(Conflict("dependency_cycle", key))

    minimum_turn: dict[str, int] = {}
    maximum_turn: dict[str, int] = {}
    if not conflicts:
        phases = len(phase_rank)
        for key in topo:
            row = active[key]
            turn = max(state.current_turn, row.earliest_turn)
            parent_completion = -1
            for parent_key in row.depends_on:
                if parent_key in active:
                    parent = active[parent_key]
                    parent_turn = minimum_turn[parent_key]
                    if parent.settlement_lag:
                        ordinal = (parent_turn + parent.settlement_lag) * phases + phases - 1
                    else:
                        ordinal = parent_turn * phases + phase_rank[parent.phase]
                    parent_completion = max(parent_completion, ordinal)
            while turn * phases + phase_rank[row.phase] <= parent_completion:
                turn += 1
            minimum_turn[key] = turn
            maximum_turn[key] = min(row.latest_turn, state.terminal_turn - row.settlement_lag)
            if maximum_turn[key] < state.current_turn:
                # Reported in `overdue` or terminal diagnostics later.
                continue
            if minimum_turn[key] > maximum_turn[key]:
                code = "terminal_unsettled" if row.latest_turn >= state.current_turn else "deadline_elapsed"
                conflicts.add(
                    Conflict(
                        code,
                        key,
                        turn=minimum_turn[key],
                        detail=(
                            f"earliest_feasible={minimum_turn[key]}; "
                            f"latest_settling_action={maximum_turn[key]}; lag={row.settlement_lag}"
                        ),
                    )
                )

        # Backward dependency propagation catches parents that cannot finish
        # before a child's last legal action.
        for key in reversed(topo):
            if key not in maximum_turn:
                continue
            row = active[key]
            latest = maximum_turn[key]
            for child_key in children[key]:
                child = active[child_key]
                child_latest = maximum_turn[child_key] * phases + phase_rank[child.phase]
                while latest >= state.current_turn:
                    completion = (
                        (latest + row.settlement_lag) * phases + phases - 1
                        if row.settlement_lag
                        else latest * phases + phase_rank[row.phase]
                    )
                    if completion < child_latest:
                        break
                    latest -= 1
            maximum_turn[key] = latest
            if minimum_turn[key] > latest:
                conflicts.add(
                    Conflict(
                        "dependency_window_empty",
                        key,
                        turn=minimum_turn[key],
                        detail=f"earliest={minimum_turn[key]}; propagated_latest={latest}",
                    )
                )

    # Necessary interval-capacity condition (a small Hall-style check).  This
    # catches shared-worker and shared-machine overcommit before enumeration.
    if not conflicts:
        for kind, capacities, reservations, demand_attr in (
            ("actor", actor_capacity, reservation_actor, "actor_demand"),
            ("machine", machine_capacity, reservation_machine, "machine_demand"),
        ):
            resources = sorted(
                {
                    resource
                    for row in active.values()
                    for resource, _ in getattr(row, demand_attr)
                }
            )
            for resource in resources:
                jobs = [
                    (minimum_turn[row.key], maximum_turn[row.key], dict(getattr(row, demand_attr))[resource])
                    for row in active.values()
                    if resource in dict(getattr(row, demand_attr))
                ]
                endpoints = sorted({point for start, end, _ in jobs for point in (start, end)})
                found = False
                for start in endpoints:
                    for end in endpoints:
                        if end < start:
                            continue
                        required = sum(units for left, right, units in jobs if left >= start and right <= end)
                        available = sum(
                            max(0, capacities[resource] - reservations.get((turn, resource), 0))
                            for turn in range(start, end + 1)
                        )
                        if required > available:
                            conflicts.add(
                                Conflict(
                                    f"{kind}_window_overload",
                                    resource=resource,
                                    turn=start,
                                    detail=f"window={start}..{end}; demand={required}; capacity={available}",
                                )
                            )
                            found = True
                            break
                    if found:
                        break

    # Stable topological order, prioritizing tight windows while preserving all
    # parent-before-child constraints.
    order: list[str] = []
    if len(topo) == len(active):
        indegree2 = {key: 0 for key in active}
        for key, row in active.items():
            indegree2[key] = sum(1 for parent in row.depends_on if parent in active)
        frontier = [key for key, degree in indegree2.items() if degree == 0]
        while frontier:
            frontier.sort(
                key=lambda key: (
                    maximum_turn.get(key, -1) - minimum_turn.get(key, 0),
                    maximum_turn.get(key, -1),
                    key,
                )
            )
            key = frontier.pop(0)
            order.append(key)
            for child in sorted(children[key]):
                indegree2[child] -= 1
                if indegree2[child] == 0:
                    frontier.append(child)

    return active, tuple(order), minimum_turn, maximum_turn, phase_rank, tuple(sorted(conflicts))


def _simulate_resources(
    state: CalendarState,
    obligations: Mapping[str, Obligation],
    assignment: Mapping[str, int],
    phase_rank: Mapping[str, int],
) -> tuple[Conflict, ...]:
    phases = len(phase_rank)
    events: dict[int, list[Obligation]] = defaultdict(list)
    for key, turn in assignment.items():
        row = obligations[key]
        ordinal = (
            (turn + row.settlement_lag) * phases + phases - 1
            if row.settlement_lag
            else turn * phases + phase_rank[row.phase]
        )
        events[ordinal].append(row)

    cash = state.cash
    inventory = defaultdict(int, _mapping(state.inventory))
    room = defaultdict(int, _mapping(state.room_used))
    capacity = _mapping(state.room_capacity)

    for ordinal in sorted(events):
        turn, rank = divmod(ordinal, phases)
        phase = state.phase_order[rank]
        rows = sorted(events[ordinal], key=lambda row: row.key)
        conflicts: list[Conflict] = []

        cash_demand = -sum(min(0, row.cash_delta) for row in rows)
        if cash < cash_demand:
            conflicts.append(
                Conflict(
                    "cash_shortfall",
                    obligation=",".join(row.key for row in rows if row.cash_delta < 0),
                    resource="cash",
                    turn=turn,
                    detail=f"phase={phase}; required={cash_demand}; available={cash}",
                )
            )

        item_demands: dict[str, int] = defaultdict(int)
        for row in rows:
            for resource, delta in row.inventory_delta:
                if delta < 0:
                    item_demands[resource] += -delta
        for resource in sorted(item_demands):
            if inventory[resource] < item_demands[resource]:
                conflicts.append(
                    Conflict(
                        "inventory_shortfall",
                        obligation=",".join(
                            row.key for row in rows if dict(row.inventory_delta).get(resource, 0) < 0
                        ),
                        resource=resource,
                        turn=turn,
                        detail=(
                            f"phase={phase}; required={item_demands[resource]}; "
                            f"available={inventory[resource]}"
                        ),
                    )
                )

        room_releases: dict[str, int] = defaultdict(int)
        room_additions: dict[str, int] = defaultdict(int)
        for row in rows:
            for resource, delta in row.room_delta:
                if delta < 0:
                    room_releases[resource] += -delta
                else:
                    room_additions[resource] += delta
        for resource in sorted(set(room_releases) | set(room_additions)):
            if room[resource] < room_releases[resource]:
                conflicts.append(
                    Conflict(
                        "room_underflow",
                        resource=resource,
                        turn=turn,
                        detail=(
                            f"phase={phase}; release={room_releases[resource]}; "
                            f"occupied={room[resource]}"
                        ),
                    )
                )
            # Fail closed: capacity released in this same phase is not reused.
            if room[resource] + room_additions[resource] > capacity[resource]:
                conflicts.append(
                    Conflict(
                        "room_overflow",
                        resource=resource,
                        turn=turn,
                        detail=(
                            f"phase={phase}; occupied={room[resource]}; "
                            f"incoming={room_additions[resource]}; capacity={capacity[resource]}"
                        ),
                    )
                )

        if conflicts:
            return tuple(sorted(conflicts))

        cash += sum(row.cash_delta for row in rows)
        for row in rows:
            for resource, delta in row.inventory_delta:
                inventory[resource] += delta
            for resource, delta in row.room_delta:
                room[resource] += delta

    return ()


def _ready_now(
    state: CalendarState,
    obligations: Mapping[str, Obligation],
) -> tuple[str, ...]:
    completed = set(state.completed)
    actor_capacity = _mapping(state.actor_capacity)
    machine_capacity = _mapping(state.machine_capacity)
    actor_reserved: dict[str, int] = defaultdict(int)
    machine_reserved: dict[str, int] = defaultdict(int)
    for row in state.actor_reservations:
        if row.turn == state.current_turn:
            actor_reserved[row.resource] += row.units
    for row in state.machine_reservations:
        if row.turn == state.current_turn:
            machine_reserved[row.resource] += row.units
    inventory = _mapping(state.inventory)
    room = _mapping(state.room_used)
    room_capacity = _mapping(state.room_capacity)

    ready: list[str] = []
    for key in sorted(obligations):
        row = obligations[key]
        if not row.earliest_turn <= state.current_turn <= row.latest_turn:
            continue
        if any(parent not in completed for parent in row.depends_on):
            continue
        if row.settlement_lag and state.current_turn + row.settlement_lag > state.terminal_turn:
            continue
        if any(
            actor_reserved[resource] + units > actor_capacity.get(resource, -1)
            for resource, units in row.actor_demand
        ):
            continue
        if any(
            machine_reserved[resource] + units > machine_capacity.get(resource, -1)
            for resource, units in row.machine_demand
        ):
            continue
        if row.cash_delta < 0 and state.cash < -row.cash_delta:
            continue
        if any(delta < 0 and inventory.get(resource, 0) < -delta for resource, delta in row.inventory_delta):
            continue
        if any(
            delta > 0 and room.get(resource, 0) + delta > room_capacity.get(resource, -1)
            for resource, delta in row.room_delta
        ):
            continue
        ready.append(key)
    return tuple(ready)


def _decision(
    *,
    admitted: bool,
    ready: tuple[str, ...],
    overdue: tuple[str, ...],
    conflicts: Iterable[Conflict],
    schedule: Mapping[str, int],
    obligations: Mapping[str, Obligation],
    state: CalendarState,
    source_hash: str,
    search_nodes: int,
) -> CalendarDecision:
    phase_rank = {name: index for index, name in enumerate(state.phase_order)}
    rows: list[tuple[str, ScheduledSlot]] = []
    slack: list[tuple[str, int]] = []
    for key in sorted(schedule):
        row = obligations[key]
        turn = schedule[key]
        settles_turn = turn + row.settlement_lag
        settles_phase = state.phase_order[-1] if row.settlement_lag else row.phase
        rows.append((key, ScheduledSlot(turn, row.phase, settles_turn, settles_phase)))
        slack.append((key, row.latest_turn - turn))
    placeholder = CalendarDecision(
        admitted=admitted,
        ready=ready,
        overdue=overdue,
        structural_conflicts=tuple(sorted(set(conflicts))),
        schedule=tuple(rows),
        remaining_slack=tuple(slack),
        source_hash=source_hash,
        certificate_hash="",
        search_nodes=search_nodes,
    )
    certificate_hash = _hash(placeholder.to_dict(include_certificate_hash=False))
    return CalendarDecision(
        admitted=placeholder.admitted,
        ready=placeholder.ready,
        overdue=placeholder.overdue,
        structural_conflicts=placeholder.structural_conflicts,
        schedule=placeholder.schedule,
        remaining_slack=placeholder.remaining_slack,
        source_hash=placeholder.source_hash,
        certificate_hash=certificate_hash,
        search_nodes=placeholder.search_nodes,
    )


def admit_bundle(
    state: CalendarState | Mapping[str, Any],
    obligations: Sequence[Obligation | Mapping[str, Any]],
    *,
    max_nodes: int = 250_000,
) -> CalendarDecision:
    """Return a deterministic, source-bound schedule admission certificate.

    ``admitted`` means the complete bundle has at least one exact schedule under
    the supplied finite model.  The function never mutates ``state`` or the
    obligation sequence.  A search limit is a hard rejection, not an optimistic
    answer.
    """

    parsed_state = state if isinstance(state, CalendarState) else CalendarState.from_dict(state)
    parsed_obligations = _normalize_obligations(obligations)
    max_nodes = _integer(max_nodes, "max_nodes", 1)
    source = {
        "schema": SCHEMA,
        "state": parsed_state.to_dict(),
        "obligations": [row.to_dict() for row in parsed_obligations],
        "max_nodes": max_nodes,
    }
    source_hash = _hash(source)

    active, order, minimum, maximum, phase_rank, precheck = _precheck(
        parsed_state, parsed_obligations
    )
    overdue = tuple(
        sorted(
            row.key
            for row in parsed_obligations
            if row.key not in set(parsed_state.completed) and row.latest_turn < parsed_state.current_turn
        )
    )
    ready = _ready_now(parsed_state, active)
    conflicts = list(precheck)
    for key in overdue:
        conflicts.append(
            Conflict(
                "deadline_elapsed",
                key,
                turn=parsed_state.current_turn,
                detail=f"latest={active[key].latest_turn}; current={parsed_state.current_turn}",
            )
        )

    if conflicts:
        return _decision(
            admitted=False,
            ready=ready,
            overdue=overdue,
            conflicts=conflicts,
            schedule={},
            obligations=active,
            state=parsed_state,
            source_hash=source_hash,
            search_nodes=0,
        )

    search = _Search(
        state=parsed_state,
        obligations=active,
        order=order,
        minimum_turn=minimum,
        maximum_turn=maximum,
        phase_rank=phase_rank,
        max_nodes=max_nodes,
    )
    for row in parsed_state.actor_reservations:
        search.actor_load[(row.turn, row.resource)] += row.units
    for row in parsed_state.machine_reservations:
        search.machine_load[(row.turn, row.resource)] += row.units
    schedule = search.solve()

    if schedule is None:
        if search.limit_hit:
            conflicts.append(
                Conflict(
                    "search_limit_exceeded",
                    detail=f"visited={search.nodes}; max_nodes={max_nodes}; fail_closed=true",
                )
            )
        elif search.best_resource_conflicts:
            conflicts.extend(search.best_resource_conflicts)
        elif search.first_dead_end:
            conflicts.append(search.first_dead_end)
        else:
            conflicts.append(Conflict("no_feasible_schedule"))

    return _decision(
        admitted=schedule is not None,
        ready=ready,
        overdue=overdue,
        conflicts=conflicts,
        schedule=schedule or {},
        obligations=active,
        state=parsed_state,
        source_hash=source_hash,
        search_nodes=search.nodes,
    )


def admit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """JSON-facing adapter used by the CLI and downstream integration seams."""

    if not isinstance(payload, Mapping):
        raise CalendarInputError("payload must be an object")
    allowed = {"state", "obligations", "max_nodes"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CalendarInputError(f"unknown payload fields: {', '.join(unknown)}")
    decision = admit_bundle(
        payload.get("state"),
        payload.get("obligations", ()),
        max_nodes=payload.get("max_nodes", 250_000),
    )
    return decision.to_dict()


def recurring_obligations(
    *,
    key_prefix: str,
    kind: str,
    first_turn: int,
    every_turns: int,
    occurrences: int,
    tolerance: int,
    phase: str = "service",
    actor_demand: Mapping[str, int] | None = None,
    machine_demand: Mapping[str, int] | None = None,
    cash_delta: int = 0,
    inventory_delta: Mapping[str, int] | None = None,
    room_delta: Mapping[str, int] | None = None,
    settlement_lag: int = 0,
) -> tuple[Obligation, ...]:
    """Expand an explicit recurrence into independently certifiable obligations."""

    prefix = _name(key_prefix, "key_prefix")
    kind = _name(kind, "kind")
    first_turn = _integer(first_turn, "first_turn", 0)
    every_turns = _integer(every_turns, "every_turns", 1)
    occurrences = _integer(occurrences, "occurrences", 1)
    tolerance = _integer(tolerance, "tolerance", 0)
    settlement_lag = _integer(settlement_lag, "settlement_lag", 0)
    result: list[Obligation] = []
    previous = ""
    for index in range(occurrences):
        due = first_turn + index * every_turns
        key = f"{prefix}:{index + 1:03d}"
        result.append(
            Obligation(
                key=key,
                kind=kind,
                earliest_turn=max(0, due - tolerance),
                latest_turn=due + tolerance,
                phase=phase,
                depends_on=(previous,) if previous else (),
                actor_demand=_pairs(actor_demand, "actor_demand", minimum=1),
                machine_demand=_pairs(machine_demand, "machine_demand", minimum=1),
                cash_delta=_integer(cash_delta, "cash_delta"),
                inventory_delta=_pairs(inventory_delta, "inventory_delta", omit_zero=True),
                room_delta=_pairs(room_delta, "room_delta", omit_zero=True),
                settlement_lag=settlement_lag,
            )
        )
        previous = key
    return tuple(result)


__all__ = [
    "CalendarDecision",
    "CalendarInputError",
    "CalendarState",
    "Conflict",
    "DEFAULT_PHASE_ORDER",
    "Obligation",
    "Reservation",
    "SCHEMA",
    "ScheduledSlot",
    "admit_bundle",
    "admit_payload",
    "recurring_obligations",
]
