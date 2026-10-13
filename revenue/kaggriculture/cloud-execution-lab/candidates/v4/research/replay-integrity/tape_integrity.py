"""Read-only tape-audit hooks for the existing TITAN game evaluator.

A replay is a fixed sequence of actions, not an adaptive opponent. This module
separates changed public inputs, changed private production, changed execution
and changed receipts. None alone establishes what an unavailable policy would
have chosen. No actions are rewritten, truncated, repaired, or synthesized.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA = "titan-replay-integrity/1"


class ReplayError(ValueError):
    """Input tape, binding, or audit sequence cannot support the claimed test."""


def encoded(value: Any) -> bytes:
    """Canonical strict JSON; reject NaN/Infinity rather than hashing ambiguity."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ReplayError(f"Non-canonical JSON: {exc}") from exc


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _index(value: Any, *, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ReplayError(f"{name} must be a nonnegative integer")
    return value


def _seat(value: Any) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ReplayError("seat must be integer 0 or 1")
    return value


def observation_parts(observation: Mapping[str, Any], seat: int) -> dict[str, Any]:
    """Only separate fields present in the supplied player's own observation."""
    _seat(seat)
    if not isinstance(observation, Mapping):
        raise ReplayError("observation must be a mapping")
    if type(observation.get("player")) is not int or observation["player"] != seat:
        raise ReplayError("observation/player does not match tape seat")
    farms = observation.get("farms")
    if not isinstance(farms, list) or len(farms) != 2:
        raise ReplayError("exactly two public farms required")
    if not isinstance(farms[seat], Mapping) or not isinstance(observation.get("private"), Mapping):
        raise ReplayError("own farm and own private state required")
    farm = deepcopy(dict(farms[seat]))
    money = farm.pop("money", None)
    result = {
        "own_production": {"farm_without_money": farm,
                           "private": deepcopy(observation["private"])},
        "own_money": money,
        "public_other_farm": deepcopy(farms[1 - seat]),
        "market": deepcopy(observation.get("market")),
        "town": deepcopy(observation.get("town")),
        "clock": {key: observation.get(key) for key in ("step", "day", "hour")},
    }
    encoded(result)
    return result


def first_difference(reference: Any, actual: Any, path: str = "$", *, budget: int = 40) -> dict | None:
    """One deterministic readable witness, with type and missing-key distinction."""
    if budget <= 0:
        if encoded(reference) == encoded(actual):
            return None
        return {"path": path, "reference_sha256": fingerprint(reference),
                "actual_sha256": fingerprint(actual), "depth_limited": True}
    if type(reference) is not type(actual):
        return {"path": path, "reference": deepcopy(reference), "actual": deepcopy(actual),
                "reference_type": type(reference).__name__, "actual_type": type(actual).__name__}
    if isinstance(reference, dict):
        for key in sorted(set(reference) | set(actual)):
            if key not in reference or key not in actual:
                return {"path": f"{path}.{key}", "reference_present": key in reference,
                        "actual_present": key in actual,
                        "reference": deepcopy(reference.get(key)), "actual": deepcopy(actual.get(key))}
            found = first_difference(reference[key], actual[key], f"{path}.{key}", budget=budget - 1)
            if found is not None:
                return found
        return None
    if isinstance(reference, list):
        for i, (left, right) in enumerate(zip(reference, actual)):
            found = first_difference(left, right, f"{path}[{i}]", budget=budget - 1)
            if found is not None:
                return found
        if len(reference) != len(actual):
            return {"path": f"{path}.length", "reference": len(reference), "actual": len(actual)}
        return None
    return None if encoded(reference) == encoded(actual) else {"path": path, "reference": reference, "actual": actual}


class FrozenTape:
    """Sequential raw-action source. Repeated/out-of-order/missing calls fail."""
    def __init__(self, frames: Sequence[Mapping], seat: int, *, expected_binding: Mapping,
                 actual_binding: Mapping):
        self.seat = _seat(seat)
        if fingerprint(expected_binding) != fingerprint(actual_binding):
            raise ReplayError("engine/configuration binding mismatch")
        if not frames:
            raise ReplayError("empty tape")
        self._frames = []
        for expected_step, frame in enumerate(frames):
            if type(frame.get("step")) is not int or frame["step"] != expected_step:
                raise ReplayError("tape steps must be contiguous from zero")
            actions = frame.get("actions")
            if not isinstance(actions, list) or len(actions) != 2 or any(not isinstance(a, dict) for a in actions):
                raise ReplayError("each frame needs two raw action objects")
            encoded(frame)
            self._frames.append({"step": expected_step, "actions": deepcopy(actions)})
        self.next_step = 0

    def action(self, step: int) -> dict:
        _index(step, name="step")
        if step != self.next_step:
            raise ReplayError("out-of-order/repeated tape callback")
        if step >= len(self._frames):
            raise ReplayError("tape exhausted; no implicit PASS padding")
        self.next_step += 1
        return deepcopy(self._frames[step]["actions"][self.seat])

    def finish(self) -> None:
        if self.next_step != len(self._frames):
            raise ReplayError("game terminated before consuming complete tape")


class TapeAudit:
    """Streaming side-effect-free audit of one replayed seat's actual transitions."""
    def __init__(self, seat: int):
        self.seat = _seat(seat)
        self.counts = Counter()
        self.first = {}
        self.next_step = 0
        self._digest = hashlib.sha256()

    def _compare(self, key: str, reference: Any, actual: Any, step: int):
        if encoded(reference) == encoded(actual):
            return
        self.counts[key] += 1
        if key not in self.first:
            self.first[key] = {"step": step, **first_difference(reference, actual)}

    def observe(self, reference_frame: Mapping, actual_frame: Mapping) -> None:
        step = actual_frame.get("step")
        _index(step, name="step")
        _index(reference_frame.get("step"), name="reference step")
        if step != self.next_step or reference_frame.get("step") != step:
            raise ReplayError("audit frames must be aligned and contiguous")
        left = reference_frame["actions"][self.seat]
        right = actual_frame["actions"][self.seat]
        if encoded(left) != encoded(right):
            raise ReplayError("replayed action differs from reference raw action")
        before = []
        after = []
        for frame in (reference_frame, actual_frame):
            before.append(observation_parts(frame["before"][self.seat], self.seat))
            after.append(observation_parts(frame["after"][self.seat], self.seat))
        for key in before[0]:
            self._compare(f"input/{key}", before[0][key], before[1][key], step)
        for key in ("own_production", "own_money"):
            self._compare(f"output/{key}", after[0][key], after[1][key], step)
        self._compare("execution/market", reference_frame["receipts"][self.seat],
                      actual_frame["receipts"][self.seat], step)
        self._compare("status", reference_frame["status"][self.seat],
                      actual_frame["status"][self.seat], step)
        self._digest.update(encoded({"step": step, "input": before[1],
                                     "output": after[1], "action": right,
                                     "receipts": actual_frame["receipts"][self.seat],
                                     "status": actual_frame["status"][self.seat]}) + b"\n")
        self.next_step += 1

    def report(self) -> dict:
        return {"schema": SCHEMA, "seat": self.seat, "callbacks": self.next_step,
                "changed_callbacks": dict(sorted(self.counts.items())), "first": deepcopy(self.first),
                "actual_side_trace_sha256": self._digest.hexdigest(),
                "interpretation": "Fixed-action replay diagnostic, not a win rate against the original adaptive policy."}


class MarketRecorder:
    """Transparent official-function wrappers: actual commits, not requested lots."""
    def __init__(self, engine, state):
        self.engine = engine
        self.state = state
        self.receipts = [{}, {}]
        self._original = {}
        self._installed = False

    def _row(self, farm, key):
        farms = self.state[0].observation.farms
        seat = next((i for i, candidate in enumerate(farms) if candidate is farm), None)
        if seat is None:
            raise ReplayError("receipt farm not bound to a current engine seat")
        return self.receipts[seat].setdefault(key, {"attempts": 0, "filled": 0, "cash_delta": 0})

    def __enter__(self):
        if self._installed:
            raise ReplayError("recorder cannot be nested/re-entered")
        names = ("_commit_unit", "_do_hire", "_do_buy_land")
        self._original = {name: getattr(self.engine, name) for name in names}
        self._installed = True
        def commit(op, item, price, farm, private, market, shed_capacity=100):
            row = self._row(farm, f"{op}:{item}")
            before = farm["money"]
            result = self._original["_commit_unit"](op, item, price, farm, private, market, shed_capacity)
            row["attempts"] += 1
            row["filled"] += int(bool(result))
            row["cash_delta"] += farm["money"] - before
            return result
        def hire(farm, private, board_size, mult=None):
            row = self._row(farm, "HIRE")
            before_money, before_hands = farm["money"], len(farm["hands"])
            result = (self._original["_do_hire"](farm, private, board_size) if mult is None
                      else self._original["_do_hire"](farm, private, board_size, mult))
            row["attempts"] += 1
            row["filled"] += len(farm["hands"]) - before_hands
            row["cash_delta"] += farm["money"] - before_money
            return result
        def land(farm, board_size):
            row = self._row(farm, "BUY_LAND")
            before = farm["money"]
            result = self._original["_do_buy_land"](farm, board_size)
            row["attempts"] += 1
            row["filled"] += int(farm["money"] < before)
            row["cash_delta"] += farm["money"] - before
            return result
        self.engine._commit_unit = commit
        self.engine._do_hire = hire
        self.engine._do_buy_land = land
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, original in self._original.items():
            setattr(self.engine, name, original)
        self._installed = False
        return False
