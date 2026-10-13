#!/usr/bin/env python3
"""Validate and render Commons factor-lane registry rows.

D4 contract: every row carries the five-field factor report
(canonical parent, durable carrier, terminal state, next gate, intended
production consumer). Composition edges are explicit and REJECTED propagates
transitively to every lane that composed the rejected lane.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

VERSION = 1
TERMINAL_STATES = frozenset(
    {
        "NOT_EXECUTED",
        "RUNNING",
        "BLOCKED",
        "PASSED",
        "REJECTED",
        "SHIPPED",
        "SUPERSEDED",
    }
)
_REQUIRED = (
    "canonical_parent",
    "durable_carrier",
    "terminal_state",
    "next_gate",
    "production_consumer",
)
_ALLOWED_ROW_KEYS = frozenset({"id", "composes", *_REQUIRED})


class RegistryError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


def _strict_string(value: Any, field: str, lane_id: str | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise RegistryError(
            "INVALID_FIELD",
            f"{field} must be a non-empty string",
            lane=lane_id,
            field=field,
        )
    return value.strip()


@dataclass(frozen=True)
class Lane:
    id: str
    canonical_parent: str
    durable_carrier: str
    terminal_state: str
    next_gate: str
    production_consumer: str
    composes: tuple[str, ...] = ()

    def declared(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canonical_parent": self.canonical_parent,
            "durable_carrier": self.durable_carrier,
            "terminal_state": self.terminal_state,
            "next_gate": self.next_gate,
            "production_consumer": self.production_consumer,
            "composes": list(self.composes),
        }


@dataclass(frozen=True)
class EffectiveLane:
    lane: Lane
    effective_state: str
    rejected_by: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        out = self.lane.declared()
        out["effective_state"] = self.effective_state
        out["rejected_by"] = list(self.rejected_by)
        return out


def _parse_lane(raw: Any) -> Lane:
    if not isinstance(raw, dict):
        raise RegistryError("INVALID_ROW", "each lane row must be an object")
    extra = sorted(set(raw) - _ALLOWED_ROW_KEYS)
    if extra:
        raise RegistryError("UNKNOWN_FIELDS", "lane row contains unknown fields", fields=extra)

    lane_id = _strict_string(raw.get("id"), "id")
    missing = [key for key in _REQUIRED if key not in raw]
    if missing:
        raise RegistryError("MISSING_FIELDS", "lane row is missing required factor fields", lane=lane_id, fields=missing)

    state = _strict_string(raw["terminal_state"], "terminal_state", lane_id).upper()
    if state not in TERMINAL_STATES:
        raise RegistryError(
            "INVALID_TERMINAL_STATE",
            "terminal_state is not a recognized exact state",
            lane=lane_id,
            state=state,
            allowed=sorted(TERMINAL_STATES),
        )

    composes_raw = raw.get("composes", [])
    if type(composes_raw) is not list:
        raise RegistryError("INVALID_COMPOSES", "composes must be a list", lane=lane_id)
    composes: list[str] = []
    for value in composes_raw:
        dep = _strict_string(value, "composes", lane_id)
        if dep == lane_id:
            raise RegistryError("SELF_COMPOSITION", "lane cannot compose itself", lane=lane_id)
        composes.append(dep)
    if len(composes) != len(set(composes)):
        raise RegistryError("DUPLICATE_COMPOSITION", "composes contains duplicate lane ids", lane=lane_id)

    return Lane(
        id=lane_id,
        canonical_parent=_strict_string(raw["canonical_parent"], "canonical_parent", lane_id),
        durable_carrier=_strict_string(raw["durable_carrier"], "durable_carrier", lane_id),
        terminal_state=state,
        next_gate=_strict_string(raw["next_gate"], "next_gate", lane_id),
        production_consumer=_strict_string(raw["production_consumer"], "production_consumer", lane_id),
        composes=tuple(composes),
    )


def load_registry(payload: Any) -> dict[str, Lane]:
    if not isinstance(payload, dict):
        raise RegistryError("INVALID_REGISTRY", "registry must be a JSON object")
    if set(payload) != {"version", "lanes"}:
        raise RegistryError(
            "INVALID_REGISTRY_KEYS",
            "registry must contain exactly version and lanes",
            keys=sorted(payload),
        )
    if type(payload["version"]) is not int or payload["version"] != VERSION:
        raise RegistryError("UNSUPPORTED_VERSION", "registry version must be exact integer 1", version=payload["version"])
    if type(payload["lanes"]) is not list:
        raise RegistryError("INVALID_LANES", "lanes must be a list")

    lanes: dict[str, Lane] = {}
    for raw in payload["lanes"]:
        lane = _parse_lane(raw)
        if lane.id in lanes:
            raise RegistryError("DUPLICATE_LANE", "lane id appears more than once", lane=lane.id)
        lanes[lane.id] = lane

    unknown = sorted({dep for lane in lanes.values() for dep in lane.composes if dep not in lanes})
    if unknown:
        raise RegistryError("UNKNOWN_COMPOSITION", "composes references unknown lane ids", lanes=unknown)

    _assert_acyclic(lanes)
    return lanes


def _assert_acyclic(lanes: dict[str, Lane]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(lane_id: str, stack: tuple[str, ...]) -> None:
        if lane_id in visited:
            return
        if lane_id in visiting:
            try:
                start = stack.index(lane_id)
            except ValueError:
                start = 0
            cycle = list(stack[start:] + (lane_id,))
            raise RegistryError("COMPOSITION_CYCLE", "composition graph contains a cycle", cycle=cycle)
        visiting.add(lane_id)
        for dep in lanes[lane_id].composes:
            visit(dep, stack + (lane_id,))
        visiting.remove(lane_id)
        visited.add(lane_id)

    for lane_id in sorted(lanes):
        visit(lane_id, ())


def effective_registry(lanes: dict[str, Lane]) -> dict[str, EffectiveLane]:
    memo: dict[str, tuple[str, ...]] = {}

    def rejected_roots(lane_id: str) -> tuple[str, ...]:
        if lane_id in memo:
            return memo[lane_id]
        lane = lanes[lane_id]
        roots: set[str] = set()
        if lane.terminal_state == "REJECTED":
            roots.add(lane_id)
        for dep in lane.composes:
            roots.update(rejected_roots(dep))
        result = tuple(sorted(roots))
        memo[lane_id] = result
        return result

    out: dict[str, EffectiveLane] = {}
    for lane_id in sorted(lanes):
        lane = lanes[lane_id]
        rejected = rejected_roots(lane_id)
        if lane.terminal_state == "REJECTED":
            state = "REJECTED"
        elif rejected:
            state = "REJECTED_UPSTREAM"
        else:
            state = lane.terminal_state
        out[lane_id] = EffectiveLane(lane=lane, effective_state=state, rejected_by=rejected)
    return out


def render_registry(lanes: dict[str, Lane]) -> dict[str, Any]:
    effective = effective_registry(lanes)
    return {
        "version": VERSION,
        "lanes": [effective[lane_id].as_dict() for lane_id in sorted(effective)],
        "counts": {
            state: sum(1 for row in effective.values() if row.effective_state == state)
            for state in sorted({row.effective_state for row in effective.values()})
        },
    }


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RegistryError("DUPLICATE_JSON_KEY", "JSON object contains a duplicate key", key=key)
        out[key] = value
    return out


def read_registry(path: str) -> dict[str, Lane]:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise RegistryError("INVALID_JSON", "registry is not strict JSON", line=exc.lineno, column=exc.colno) from exc
    return load_registry(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", help="registry JSON path, or - for stdin")
    parser.add_argument("--lane", help="emit one effective lane by exact id")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    try:
        lanes = read_registry(args.registry)
        rendered = render_registry(lanes)
        if args.lane is not None:
            match = next((row for row in rendered["lanes"] if row["id"] == args.lane), None)
            if match is None:
                raise RegistryError("LANE_NOT_FOUND", "requested lane id is not registered", lane=args.lane)
            rendered = {"version": VERSION, "lane": match}
    except (RegistryError, OSError) as exc:
        if isinstance(exc, RegistryError):
            out = exc.as_dict()
        else:
            out = {"ok": False, "error": "IO_ERROR", "message": str(exc)}
        json.dump(out, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 2

    rendered["ok"] = True
    json.dump(rendered, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
