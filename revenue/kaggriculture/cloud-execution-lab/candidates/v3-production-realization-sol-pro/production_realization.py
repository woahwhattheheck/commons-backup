# SPDX-License-Identifier: Apache-2.0
"""Atomic admission for score-effective production-route mutations.

TITAN's action generators are split across unit and market callbacks.  A local
PLANT/WATER edit can therefore be executable while remaining score-null when the
inherited tape never harvests, deposits, or sells the added output.  This module
puts one fail-closed transaction boundary around that entire lifecycle.

The caller supplies an exact official-engine evaluator.  Admission requires an
engine-bound receipt for every declared scenario, complete lot provenance from
an upstream commitment through HARVEST, explicit DROP, and positive-cash SELL,
nonnegative cash troughs, preserved unrelated obligations, and a strict terminal
score gain.  A rejection returns the original base-route object unchanged.

The module never predicts mechanics, reads future observations, or edits a live
action by itself.  It is intended as the commit gate immediately after a route
constructor and official-engine simulator.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Any, Callable, Mapping, Sequence


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_STAGE = {"commit": 0, "harvest": 1, "drop": 2, "sale": 3}


class InvalidLifecycle(ValueError):
    """A route, patch, scenario, or receipt violates the admission contract."""


@dataclass(frozen=True)
class AdmissionConfig:
    """Finite horizon and risk envelope for one atomic route decision."""

    now: int
    terminal_step: int
    rejoin_step: int
    minimum_gain: float = 0.0
    seconds: float | None = 0.15


@dataclass(frozen=True)
class _Candidate:
    route: list[Mapping[str, Any]]
    changed_steps: tuple[int, ...]
    base_sha256: str
    candidate_sha256: str


def _strict_int(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidLifecycle(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise InvalidLifecycle(f"{name} must be >= {minimum}")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise InvalidLifecycle(f"{name} cannot be a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidLifecycle(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise InvalidLifecycle(f"{name} must be finite")
    return result


def _hex64(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise InvalidLifecycle(f"{name} must be a lowercase sha256 hex digest")
    return value


def _validate_json_shape(value: Any, name: str, seen: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidLifecycle(f"{name} must contain finite numbers")
        return
    if isinstance(value, list):
        marker = id(value)
        if marker in seen:
            raise InvalidLifecycle(f"{name} must not contain cycles")
        seen.add(marker)
        try:
            for index, row in enumerate(value):
                _validate_json_shape(row, f"{name}[{index}]", seen)
        finally:
            seen.remove(marker)
        return
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in seen:
            raise InvalidLifecycle(f"{name} must not contain cycles")
        seen.add(marker)
        try:
            for key, row in value.items():
                if not isinstance(key, str):
                    raise InvalidLifecycle(f"{name} object keys must be strings")
                _validate_json_shape(row, f"{name}.{key}", seen)
        finally:
            seen.remove(marker)
        return
    raise InvalidLifecycle(f"{name} must contain only strict JSON values")


def _strict_json_bytes(value: Any, name: str) -> bytes:
    _validate_json_shape(value, name, set())
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise InvalidLifecycle(f"{name} must be strict JSON") from exc
    return encoded


def route_sha256(route: Sequence[Mapping[str, Any]], start: int, end: int) -> str:
    """Digest an inclusive executable route slice using canonical strict JSON."""

    start = _strict_int(start, "digest start", minimum=0)
    end = _strict_int(end, "digest end", minimum=start)
    if isinstance(route, (str, bytes, bytearray)) or not isinstance(route, Sequence):
        raise InvalidLifecycle("route must be a sequence")
    if len(route) <= end:
        raise InvalidLifecycle("route does not cover digest horizon")
    rows = []
    for step in range(start, end + 1):
        row = route[step]
        if not isinstance(row, Mapping):
            raise InvalidLifecycle(f"route[{step}] must be a mapping")
        # Normalize mapping implementations and detach caller aliases.
        try:
            rows.append(deepcopy(dict(row)))
        except Exception as exc:
            raise InvalidLifecycle(f"route[{step}] cannot be copied") from exc
    return hashlib.sha256(_strict_json_bytes(rows, "route slice")).hexdigest()


def _config(config: AdmissionConfig) -> tuple[int, int, int, float, float | None]:
    if not isinstance(config, AdmissionConfig):
        raise InvalidLifecycle("config must be AdmissionConfig")
    now = _strict_int(config.now, "now", minimum=0)
    terminal = _strict_int(config.terminal_step, "terminal_step", minimum=now)
    rejoin = _strict_int(config.rejoin_step, "rejoin_step", minimum=now + 1)
    if rejoin > terminal + 1:
        raise InvalidLifecycle("rejoin_step must be at most terminal_step + 1")
    gain = _finite(config.minimum_gain, "minimum_gain")
    if gain < 0:
        raise InvalidLifecycle("minimum_gain must be nonnegative")
    if config.seconds is None:
        seconds = None
    else:
        seconds = _finite(config.seconds, "seconds")
        if seconds < 0:
            raise InvalidLifecycle("seconds must be nonnegative")
    return now, terminal, rejoin, gain, seconds


def materialize_candidate(
    base_route: Sequence[Mapping[str, Any]],
    patches: Mapping[int, Mapping[str, Any]],
    config: AdmissionConfig,
) -> _Candidate:
    """Apply a sparse pre-rejoin patch to a detached route copy.

    The base route is never mutated.  Patches at or after the declared rejoin are
    rejected, so the candidate action tape is byte-identical to the parent from
    the rejoin step through the terminal executable step.
    """

    now, terminal, rejoin, _gain, _seconds = _config(config)
    if isinstance(base_route, (str, bytes, bytearray)) or not isinstance(base_route, Sequence):
        raise InvalidLifecycle("base_route must be a sequence")
    if len(base_route) <= terminal:
        raise InvalidLifecycle("base_route does not cover terminal_step")
    if not isinstance(patches, Mapping) or not patches:
        raise InvalidLifecycle("patches must be a nonempty mapping")

    # Canonicalize and validate the base horizon before making a candidate.
    base_digest = route_sha256(base_route, now, terminal)
    try:
        candidate: list[Mapping[str, Any]] = list(deepcopy(base_route))
    except Exception as exc:
        raise InvalidLifecycle("base_route cannot be copied") from exc

    requested_steps = []
    for raw_step, row in patches.items():
        step = _strict_int(raw_step, "patch step")
        if not now <= step < rejoin:
            raise InvalidLifecycle("patch step must be inside [now, rejoin_step)")
        if step > terminal:
            raise InvalidLifecycle("patch step exceeds terminal_step")
        if not isinstance(row, Mapping):
            raise InvalidLifecycle("patch row must be a mapping")
        _strict_json_bytes(dict(row), f"patch[{step}]")
        try:
            candidate[step] = deepcopy(dict(row))
        except Exception as exc:
            raise InvalidLifecycle(f"patch[{step}] cannot be copied") from exc
        requested_steps.append(step)

    changed_steps = tuple(
        step for step in sorted(set(requested_steps))
        if _strict_json_bytes(dict(base_route[step]), f"base[{step}]")
        != _strict_json_bytes(dict(candidate[step]), f"candidate[{step}]")
    )
    if not changed_steps:
        raise InvalidLifecycle("patch does not change the executable route")

    # This equality is stronger than object equality: it is a byte-level
    # canonical JSON assertion over the complete inherited suffix.
    inherited_base = route_sha256(base_route, rejoin, terminal) if rejoin <= terminal else None
    inherited_candidate = route_sha256(candidate, rejoin, terminal) if rejoin <= terminal else None
    if inherited_base != inherited_candidate:
        raise InvalidLifecycle("candidate route does not rejoin parent action tape")

    return _Candidate(
        route=candidate,
        changed_steps=changed_steps,
        base_sha256=base_digest,
        candidate_sha256=route_sha256(candidate, now, terminal),
    )


def _scenario_names(scenarios: Sequence[str]) -> tuple[str, ...]:
    if isinstance(scenarios, (str, bytes, bytearray)) or not isinstance(scenarios, Sequence):
        raise InvalidLifecycle("scenarios must be a sequence of names")
    names = []
    for value in scenarios:
        if not isinstance(value, str) or not value.strip():
            raise InvalidLifecycle("scenario names must be nonempty strings")
        names.append(value)
    if not names:
        raise InvalidLifecycle("at least one scenario is required")
    if len(set(names)) != len(names):
        raise InvalidLifecycle("scenario names must be unique")
    return tuple(names)


def _event(event: Any, *, now: int, terminal: int) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise InvalidLifecycle("receipt event must be a mapping")
    kind = event.get("kind")
    if kind not in _STAGE:
        raise InvalidLifecycle("event kind must be commit/harvest/drop/sale")
    step = _strict_int(event.get("step"), "event step")
    if not now <= step <= terminal:
        raise InvalidLifecycle("event step outside executable horizon")
    lot = event.get("lot")
    item = event.get("item")
    if not isinstance(lot, str) or not lot:
        raise InvalidLifecycle("event lot must be a nonempty string")
    if not isinstance(item, str) or not item:
        raise InvalidLifecycle("event item must be a nonempty string")
    quantity = _strict_int(event.get("quantity"), "event quantity", minimum=1)
    explicit = event.get("explicit")
    if kind == "drop" and explicit is not True:
        raise InvalidLifecycle("DROP evidence must be explicitly executed")
    if kind != "drop" and "explicit" in event and not isinstance(explicit, bool):
        raise InvalidLifecycle("event explicit flag must be boolean")
    cash_delta = None
    if kind == "sale":
        cash_delta = _finite(event.get("cash_delta"), "sale cash_delta")
        if cash_delta <= 0:
            raise InvalidLifecycle("sale must realize positive cash")
    elif "cash_delta" in event:
        cash_delta = _finite(event.get("cash_delta"), "event cash_delta")
    return {
        "kind": kind,
        "step": step,
        "lot": lot,
        "item": item,
        "quantity": quantity,
        **({"explicit": True} if kind == "drop" else {}),
        **({"cash_delta": cash_delta} if cash_delta is not None else {}),
    }


def _verify_lots(
    raw_events: Any,
    *,
    now: int,
    terminal: int,
    rejoin: int,
    changed_steps: tuple[int, ...],
) -> dict[str, Any]:
    if not isinstance(raw_events, list) or not raw_events:
        raise InvalidLifecycle("receipt needs lifecycle events")
    events = [_event(row, now=now, terminal=terminal) for row in raw_events]

    # Engine traces are expected in execution order.  Same-step stage order is
    # meaningful because unit actions execute before the market queue.
    order_keys = [(row["step"], _STAGE[row["kind"]]) for row in events]
    if order_keys != sorted(order_keys):
        raise InvalidLifecycle("events must be in engine execution order")

    by_lot: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        by_lot.setdefault(row["lot"], []).append(row)
    if not by_lot:
        raise InvalidLifecycle("receipt needs at least one realized lot")

    total_harvested = 0
    total_realized = 0
    total_cash = 0.0
    compact_lots = []
    for lot in sorted(by_lot):
        rows = by_lot[lot]
        items = {row["item"] for row in rows}
        if len(items) != 1:
            raise InvalidLifecycle("one lot cannot change item identity")
        item = next(iter(items))
        commits = [row for row in rows if row["kind"] == "commit"]
        harvests = [row for row in rows if row["kind"] == "harvest"]
        drops = [row for row in rows if row["kind"] == "drop"]
        sales = [row for row in rows if row["kind"] == "sale"]
        if not commits or not harvests or not drops or not sales:
            raise InvalidLifecycle("every lot needs commit, harvest, explicit drop, and sale")
        if any(row["step"] >= rejoin for row in commits):
            raise InvalidLifecycle("upstream commitments must occur before rejoin_step")
        if not any(row["step"] in changed_steps for row in commits):
            raise InvalidLifecycle("each realized lot needs a commitment on a changed action step")

        first_commit = min(row["step"] for row in commits)
        first_harvest = min(row["step"] for row in harvests)
        first_drop = min(row["step"] for row in drops)
        first_sale = min(row["step"] for row in sales)
        if not first_commit <= first_harvest <= first_drop <= first_sale:
            raise InvalidLifecycle("lifecycle stages are not causally ordered")

        harvested = sum(row["quantity"] for row in harvests)
        dropped = sum(row["quantity"] for row in drops)
        sold = sum(row["quantity"] for row in sales)
        sale_cash = sum(float(row["cash_delta"]) for row in sales)
        if dropped != harvested:
            raise InvalidLifecycle("explicit DROP quantity must equal harvested quantity")
        if sold != harvested:
            raise InvalidLifecycle("sold quantity must equal harvested quantity")
        if sale_cash <= 0:
            raise InvalidLifecycle("realized lot cash must be positive")

        total_harvested += harvested
        total_realized += sold
        total_cash += sale_cash
        compact_lots.append({
            "lot": lot,
            "item": item,
            "commit_steps": sorted({row["step"] for row in commits}),
            "harvested_units": harvested,
            "explicitly_dropped_units": dropped,
            "realized_units": sold,
            "realized_cash": sale_cash,
            "sale_step": max(row["step"] for row in sales),
        })

    return {
        "lots": compact_lots,
        "realized_lots": len(compact_lots),
        "harvested_units": total_harvested,
        "realized_units": total_realized,
        "realized_cash": total_cash,
    }


def _verify_receipt(
    receipt: Any,
    *,
    expected_scenario: str,
    candidate: _Candidate,
    config: AdmissionConfig,
    expected_engine_sha256: str | None,
) -> dict[str, Any]:
    now, terminal, rejoin, minimum_gain, _seconds = _config(config)
    if not isinstance(receipt, Mapping):
        raise InvalidLifecycle("evaluator receipt must be a mapping")
    if receipt.get("complete") is not True:
        raise InvalidLifecycle("scenario evaluation is incomplete")
    if receipt.get("scenario") != expected_scenario:
        raise InvalidLifecycle("receipt scenario does not match request")
    if receipt.get("base_route_sha256") != candidate.base_sha256:
        raise InvalidLifecycle("receipt is not bound to the base route")
    if receipt.get("candidate_route_sha256") != candidate.candidate_sha256:
        raise InvalidLifecycle("receipt is not bound to the candidate route")

    engine_sha256 = _hex64(receipt.get("engine_sha256"), "engine_sha256")
    if expected_engine_sha256 is not None and engine_sha256 != expected_engine_sha256:
        raise InvalidLifecycle("scenario receipts use different engine artifacts")
    trace_sha256 = _hex64(receipt.get("trace_sha256"), "trace_sha256")
    control_base = _hex64(
        receipt.get("rejoin_control_base_sha256"), "rejoin_control_base_sha256"
    )
    control_candidate = _hex64(
        receipt.get("rejoin_control_candidate_sha256"),
        "rejoin_control_candidate_sha256",
    )
    if control_base != control_candidate:
        raise InvalidLifecycle("unrelated control state does not rejoin")
    if receipt.get("existing_obligations_preserved") is not True:
        raise InvalidLifecycle("existing obligations were not preserved")

    base_score = _finite(receipt.get("base_terminal_score"), "base_terminal_score")
    candidate_score = _finite(
        receipt.get("candidate_terminal_score"), "candidate_terminal_score"
    )
    minimum_cash = _finite(receipt.get("candidate_minimum_cash"), "candidate_minimum_cash")
    if minimum_cash < 0:
        raise InvalidLifecycle("candidate cash trough is negative")
    gain = candidate_score - base_score
    if gain <= minimum_gain:
        raise InvalidLifecycle("candidate lacks strict terminal score gain")

    lifecycle = _verify_lots(
        receipt.get("events"),
        now=now,
        terminal=terminal,
        rejoin=rejoin,
        changed_steps=candidate.changed_steps,
    )
    return {
        "scenario": expected_scenario,
        "engine_sha256": engine_sha256,
        "trace_sha256": trace_sha256,
        "base_terminal_score": base_score,
        "candidate_terminal_score": candidate_score,
        "gain": gain,
        "candidate_minimum_cash": minimum_cash,
        **lifecycle,
    }


def admit_realized_patch(
    base_route: Sequence[Mapping[str, Any]],
    patches: Mapping[int, Mapping[str, Any]],
    *,
    config: AdmissionConfig,
    scenarios: Sequence[str],
    evaluate: Callable[
        [Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]], str, float | None],
        Mapping[str, Any],
    ],
) -> tuple[Sequence[Mapping[str, Any]], dict[str, Any]]:
    """Atomically admit a production route only after full realization evidence.

    ``evaluate`` must run the pinned official engine and return one receipt per
    requested scenario.  It receives ``(base_route, candidate_route, scenario,
    deadline)``.  The deadline is an absolute ``time.perf_counter`` value or
    ``None``.  All scenarios must complete and satisfy the same engine digest.

    On every rejection path this function returns *the exact ``base_route``
    object*, not merely an equal copy.  This makes the gate safe to compose with
    a parent action tape and easy to assert in integration tests.
    """

    started = time.perf_counter()
    report: dict[str, Any] = {
        "complete": False,
        "admitted": False,
        "reason": "invalid_input",
        "scenarios": [],
    }
    try:
        now, terminal, rejoin, minimum_gain, seconds = _config(config)
        names = _scenario_names(scenarios)
        if not callable(evaluate):
            raise InvalidLifecycle("evaluate must be callable")
        candidate = materialize_candidate(base_route, patches, config)
        deadline = None if seconds is None else started + seconds
        report.update(
            base_route_sha256=candidate.base_sha256,
            candidate_route_sha256=candidate.candidate_sha256,
            changed_steps=list(candidate.changed_steps),
            now=now,
            terminal_step=terminal,
            rejoin_step=rejoin,
            minimum_gain=minimum_gain,
        )

        receipts = []
        engine_sha256 = None
        for name in names:
            if deadline is not None and time.perf_counter() >= deadline:
                report.update(reason="incomplete_budget", scenarios=[])
                return base_route, report
            try:
                # Evaluators receive disposable snapshots.  A simulator bug may
                # mutate its inputs, but it can never corrupt the parent route or
                # the candidate that this transaction may ultimately commit.
                evaluation_base = deepcopy(base_route)
                evaluation_candidate = deepcopy(candidate.route)
                raw = evaluate(evaluation_base, evaluation_candidate, name, deadline)
            except Exception as exc:
                report.update(
                    reason="evaluator_exception",
                    detail=f"{type(exc).__name__}: {exc}",
                    scenarios=[],
                )
                return base_route, report
            if deadline is not None and time.perf_counter() > deadline:
                report.update(reason="incomplete_budget", scenarios=[])
                return base_route, report
            try:
                verified = _verify_receipt(
                    raw,
                    expected_scenario=name,
                    candidate=candidate,
                    config=config,
                    expected_engine_sha256=engine_sha256,
                )
            except InvalidLifecycle as exc:
                report.update(
                    complete=True,
                    reason="scenario_rejected",
                    rejected_scenario=name,
                    detail=str(exc),
                    scenarios=receipts,
                )
                return base_route, report
            if engine_sha256 is None:
                engine_sha256 = verified["engine_sha256"]
            receipts.append(verified)

        if route_sha256(base_route, now, terminal) != candidate.base_sha256:
            report.update(reason="caller_route_changed_during_evaluation", scenarios=[])
            return base_route, report
        if route_sha256(candidate.route, now, terminal) != candidate.candidate_sha256:
            report.update(reason="candidate_route_changed_during_evaluation", scenarios=[])
            return base_route, report

        worst_gain = min(row["gain"] for row in receipts)
        total_realized = min(row["realized_units"] for row in receipts)
        total_cash = min(row["realized_cash"] for row in receipts)
        report.update(
            complete=True,
            admitted=True,
            reason="strict_realized_terminal_gain",
            engine_sha256=engine_sha256,
            worst_gain=worst_gain,
            worst_realized_units=total_realized,
            worst_realized_cash=total_cash,
            scenarios=receipts,
            elapsed_seconds=time.perf_counter() - started,
        )
        return candidate.route, report
    except InvalidLifecycle as exc:
        report.update(
            complete=True,
            reason="invalid_input",
            detail=str(exc),
            scenarios=[],
            elapsed_seconds=time.perf_counter() - started,
        )
        return base_route, report
    except Exception as exc:
        # Deepcopy and strict-JSON failures from exotic Mapping implementations
        # must never escape into the live agent.
        report.update(
            reason="internal_failure",
            detail=f"{type(exc).__name__}: {exc}",
            scenarios=[],
            elapsed_seconds=time.perf_counter() - started,
        )
        return base_route, report
