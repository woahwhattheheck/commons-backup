# SPDX-License-Identifier: Apache-2.0
"""Exact fixed-suffix counterfactuals for late Kaggriculture service actions.

The evaluator starts from one retained player-visible observation.  The supplied
record must also contain both players' authored actions and the evaluator's
per-unit SELL receipt ledger through the final executable decision.  No agent is
called and no route is reconstructed from an isolated observation.

The opponent's hidden state is not guessed.  This component is deliberately
limited to suffixes where every remaining market order is SELL and no end-of-day
boundary occurs.  In that domain, the opponent's future market availability is
exactly the count of its retained per-unit SELL receipts; opponent unit state
cannot affect our farm or the shared market by any other route.  A baseline
replay must reproduce the retained next observations and terminal result before
any counterfactual is accepted.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

SERVICE_OPERATIONS = frozenset(("FEED", "CARE", "WATER", "FERTILIZE"))
DEFAULT_FIRST_DECISION = 700
DEFAULT_FINAL_DECISION = 718


class RecordError(ValueError):
    """The retained record cannot support this exact fixed-suffix comparison."""


class Struct(dict):
    """Small dict/attribute adapter for the unmodified interpreter."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    __setattr__ = dict.__setitem__


def canonical(value: Any) -> str:
    """Lossless ordered JSON used for source-bound fingerprints."""
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"), sort_keys=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _integer(value: Any, name: str, lower: int = 0) -> int:
    if type(value) is not int or value < lower:
        raise RecordError(f"{name} must be an integer >= {lower}")
    return value


def unit_actions(action: Mapping[str, Any]) -> tuple[Any, ...]:
    if not isinstance(action, Mapping):
        raise RecordError("each authored action must be a mapping")
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        raise RecordError("hands must be a list")
    return (action.get("farmer", ["PASS"]), *hands)


def service_occurrences(action: Mapping[str, Any]) -> tuple[tuple[int, str], ...]:
    out: list[tuple[int, str]] = []
    for index, command in enumerate(unit_actions(action)):
        if isinstance(command, list) and command and command[0] in SERVICE_OPERATIONS:
            out.append((index, command[0]))
    return tuple(out)


def omit_unit_action(action: Mapping[str, Any], unit_index: int) -> dict[str, Any]:
    """Replace exactly one farmer/hand command with PASS, preserving all slots."""
    _integer(unit_index, "unit_index")
    out = deepcopy(dict(action))
    if unit_index == 0:
        out["farmer"] = ["PASS"]
        return out
    hands = out.get("hands", [])
    if not isinstance(hands, list) or unit_index - 1 >= len(hands):
        raise RecordError("selected hand is absent")
    hands[unit_index - 1] = ["PASS"]
    return out


def frame_map(record: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    frames = record.get("final_day")
    if not isinstance(frames, list):
        raise RecordError("record has no final_day frame list")
    result: dict[int, Mapping[str, Any]] = {}
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise RecordError("frame must be a mapping")
        step = _integer(frame.get("step"), "frame step")
        if step in result:
            raise RecordError("duplicate frame step")
        actions = frame.get("actions")
        if not isinstance(actions, list) or len(actions) != 2:
            raise RecordError("each frame needs two authored actions")
        if not isinstance(frame.get("observation"), Mapping):
            raise RecordError("frame has no observation")
        if not isinstance(frame.get("configuration"), Mapping):
            raise RecordError("frame has no configuration")
        result[step] = frame
    return result


def sale_counts(record: Mapping[str, Any]) -> Counter[tuple[int, int, str]]:
    """Count exact successful SELL units retained by evaluator instrumentation."""
    counts: Counter[tuple[int, int, str]] = Counter()
    rows = record.get("final_day_receipts")
    if not isinstance(rows, list):
        raise RecordError("record has no per-unit final_day_receipts")
    for row in rows:
        if not isinstance(row, Mapping) or row.get("op") != "SELL":
            continue
        step = _integer(row.get("step"), "receipt step")
        player = _integer(row.get("player"), "receipt player")
        item = row.get("item")
        cash = row.get("cash")
        if player not in (0, 1) or not isinstance(item, str):
            raise RecordError("malformed SELL receipt identity")
        if type(cash) not in (int, float) or not math.isfinite(float(cash)):
            raise RecordError("malformed SELL receipt cash")
        counts[(step, player, item)] += 1
    return counts


def _market_orders(action: Mapping[str, Any]) -> tuple[Any, ...]:
    market = action.get("market", [])
    if not isinstance(market, list):
        raise RecordError("market queue must be a list")
    return tuple(market)


def validate_suffix(record: Mapping[str, Any], start_step: int,
                    final_step: int = DEFAULT_FINAL_DECISION) -> tuple[
                        dict[int, Mapping[str, Any]], int, Counter[tuple[int, int, str]]
                    ]:
    """Prove that an observation-only suffix has the required exact boundaries."""
    _integer(start_step, "start_step")
    _integer(final_step, "final_step")
    if start_step > final_step:
        raise RecordError("start_step exceeds final_step")
    frames = frame_map(record)
    missing = [step for step in range(start_step, final_step + 1) if step not in frames]
    if missing:
        raise RecordError(f"missing retained frame {missing[0]}")
    seat = _integer(record.get("candidate_seat"), "candidate_seat")
    if seat not in (0, 1):
        raise RecordError("candidate_seat must be 0 or 1")
    configuration = frames[start_step]["configuration"]
    episode_steps = _integer(configuration.get("episodeSteps", 720), "episodeSteps", 2)
    turns_per_day = _integer(configuration.get("turnsPerDay", 24), "turnsPerDay", 1)
    if final_step != episode_steps - 2:
        raise RecordError("final_step is not the final executable decision")
    # At an end-of-day boundary hidden opponent production/deposit could affect
    # its later sale availability for reasons absent from our observation.
    if any((step + 1) % turns_per_day == 0
           for step in range(start_step, final_step + 1)):
        raise RecordError("suffix crosses an end-of-day hidden-state boundary")
    for step in range(start_step, final_step + 1):
        for player in (0, 1):
            for order in _market_orders(frames[step]["actions"][player]):
                if order and (not isinstance(order, list) or order[0] != "SELL"):
                    raise RecordError(
                        f"non-SELL future market order at step {step}: {order!r}"
                    )
    return frames, seat, sale_counts(record)


@dataclass(frozen=True)
class Replay:
    start_step: int
    final_step: int
    candidate_seat: int
    farms: tuple[dict[str, Any], dict[str, Any]]
    private: dict[str, Any]
    market: dict[str, Any]
    town: dict[str, Any]
    snapshots: tuple[dict[str, Any], ...]

    @property
    def cash(self) -> tuple[float, float]:
        return (float(self.farms[0]["money"]), float(self.farms[1]["money"]))


def replay_suffix(engine: Any, record: Mapping[str, Any], start_step: int, *,
                  omit_unit: int | None = None,
                  final_step: int = DEFAULT_FINAL_DECISION) -> Replay:
    """Run authored actions to terminal, optionally omitting one current service.

    Opponent unit actions are replaced by PASS because their hidden local state
    cannot affect our farm or shared market in the validated suffix.  Before each
    step its synthetic shed is populated with exactly the successful units in
    the retained SELL ledger, preserving its baseline quantity while allowing
    changed shared prices.  The candidate's complete observed farm/private state
    and all of its authored future actions execute normally in the official
    interpreter.
    """
    frames, seat, counts = validate_suffix(record, start_step, final_step)
    opponent = 1 - seat
    first = frames[start_step]
    observation = deepcopy(first["observation"])
    configuration = deepcopy(dict(first["configuration"]))
    farms = deepcopy(observation["farms"])
    market = deepcopy(observation["market"])
    town = deepcopy(observation["town"])
    private = deepcopy(observation["private"])
    privates: list[dict[str, Any] | None] = [None, None]
    privates[seat] = private
    snapshots: list[dict[str, Any]] = []

    for step in range(start_step, final_step + 1):
        frame = frames[step]
        other = engine._new_private()
        for item in engine.PRODUCTS:
            quantity = counts[(step, opponent, item)]
            if quantity:
                other["shed"][item] = quantity
        privates[opponent] = other

        actions = deepcopy(frame["actions"])
        actions[opponent] = {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in farms[opponent].get("hands", [])],
            "market": deepcopy(actions[opponent].get("market", [])),
        }
        if step == start_step and omit_unit is not None:
            actions[seat] = omit_unit_action(actions[seat], omit_unit)

        states: list[Struct] = []
        for player in (0, 1):
            own_observation = Struct(
                step=step,
                player=player,
                private=privates[player],
                farms=farms,
                market=market,
                town=town,
                day=step // int(configuration.get("turnsPerDay", 24)),
                hour=step % int(configuration.get("turnsPerDay", 24)),
            )
            states.append(Struct(observation=own_observation, action=actions[player],
                                 status="ACTIVE", reward=0.0))
        env = Struct(configuration=Struct(configuration), done=False,
                     info={"seed": _integer(record.get("seed"), "seed")})
        engine.interpreter(states, env)
        private = states[seat].observation.private
        privates[seat] = private
        farms = states[0].observation.farms
        market = states[0].observation.market
        town = states[0].observation.town
        snapshots.append({
            "after_step": step,
            "candidate_farm": deepcopy(farms[seat]),
            "candidate_private": deepcopy(private),
            "market": deepcopy(market),
            "town": deepcopy(town),
            "cash": [float(farms[0]["money"]), float(farms[1]["money"])],
        })

    return Replay(start_step, final_step, seat,
                  (deepcopy(farms[0]), deepcopy(farms[1])),
                  deepcopy(private), deepcopy(market), deepcopy(town),
                  tuple(snapshots))


def validate_baseline(record: Mapping[str, Any], replay: Replay) -> int:
    """Require exact retained next-state and terminal correspondence.

    Returns the number of exact transition snapshots checked.  We compare the
    candidate's complete farm/private state, shared market/town, and both cash
    balances.  Opponent noncash farm/private state is intentionally not claimed.
    """
    frames = frame_map(record)
    seat = replay.candidate_seat
    checked = 0
    for snapshot in replay.snapshots:
        step = snapshot["after_step"]
        if step < replay.final_step:
            next_observation = frames[step + 1]["observation"]
            expected = {
                "candidate_farm": next_observation["farms"][seat],
                "candidate_private": next_observation["private"],
                "market": next_observation["market"],
                "town": next_observation["town"],
                "cash": [float(next_observation["farms"][0]["money"]),
                         float(next_observation["farms"][1]["money"])],
            }
        else:
            terminal = record.get("terminal")
            if not isinstance(terminal, Mapping):
                raise RecordError("record has no terminal state")
            expected = {
                "candidate_farm": terminal["farms"][seat],
                "candidate_private": terminal["private"][seat],
                # Terminal archive omits market/town; the previous public fields
                # have no subsequent action.  They remain exact replay output.
                "market": snapshot["market"],
                "town": snapshot["town"],
                "cash": [float(terminal["farms"][0]["money"]),
                         float(terminal["farms"][1]["money"])],
            }
        actual = {key: snapshot[key] for key in expected}
        if canonical(actual) != canonical(expected):
            raise RecordError(f"baseline replay diverges after step {step}")
        checked += 1
    scores = record.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        raise RecordError("record has no two-player score")
    if any(not math.isclose(replay.cash[i], float(scores[i]), abs_tol=1e-9)
           for i in (0, 1)):
        raise RecordError("baseline terminal cash differs from recorded scores")
    return checked


@dataclass(frozen=True)
class Counterfactual:
    record: str
    arm: str
    opponent: str
    seed: int
    seat: int
    step: int
    unit: int
    operation: str
    own_cash_delta: float
    rival_cash_delta: float
    own_state_delta_sha256: str
    shared_market_delta_sha256: str

    @property
    def margin_delta(self) -> float:
        return self.own_cash_delta - self.rival_cash_delta

    def compact(self) -> dict[str, Any]:
        result = asdict(self)
        result["margin_delta"] = self.margin_delta
        return result


def _delta(before: Any, after: Any) -> Any:
    """Ordered, JSON-safe structural delta used only for evidence hashing."""
    if type(before) is not type(after):
        return {"before": before, "after": after}
    if isinstance(before, dict):
        rows = []
        keys = list(before) + [key for key in after if key not in before]
        for key in keys:
            if key not in before or key not in after:
                rows.append([key, {"before": before.get(key), "after": after.get(key)}])
                continue
            change = _delta(before[key], after[key])
            if change is not None:
                rows.append([key, change])
        return rows or None
    if isinstance(before, list):
        if len(before) != len(after):
            return {"before": before, "after": after}
        rows = []
        for index, (left, right) in enumerate(zip(before, after)):
            change = _delta(left, right)
            if change is not None:
                rows.append([index, change])
        return rows or None
    return None if before == after else {"before": before, "after": after}


def occurrence_fingerprint(record: Mapping[str, Any], record_name: str,
                           step: int, unit: int,
                           final_step: int = DEFAULT_FINAL_DECISION) -> str:
    """Deduplicate exact observation/action/receipt suffixes, not seed labels."""
    frames, seat, _ = validate_suffix(record, step, final_step)
    receipts = [row for row in record["final_day_receipts"]
                if row.get("op") == "SELL" and int(row["step"]) >= step]
    payload = {
        "seat": seat,
        "step": step,
        "unit": unit,
        "observation": frames[step]["observation"],
        "configuration": frames[step]["configuration"],
        "actions": [frames[current]["actions"]
                    for current in range(step, final_step + 1)],
        "sell_receipts": receipts,
    }
    return digest(payload)


def scan_records(engine: Any, named_records: Iterable[tuple[str, Mapping[str, Any]]], *,
                 first_step: int = DEFAULT_FIRST_DECISION,
                 final_step: int = DEFAULT_FINAL_DECISION) -> dict[str, Any]:
    """Validate all baselines and omit each selected service once.

    The returned report is compact and contains no observation, action or private
    state.  The occurrence rows identify original records but only hash terminal
    deltas.  A caller that needs detailed private evidence should retain it in
    its controlled source archive rather than publish it through this API.
    """
    _integer(first_step, "first_step")
    _integer(final_step, "final_step")
    rows: list[Counterfactual] = []
    fingerprints: Counter[str] = Counter()
    baseline_cache: dict[tuple[str, int], Replay] = {}
    baseline_starts = baseline_checks = 0
    source_records = 0

    for record_name, record in named_records:
        if not isinstance(record_name, str) or not isinstance(record, Mapping):
            raise RecordError("named records must be (string, mapping) pairs")
        source_records += 1
        frames = frame_map(record)
        seat = _integer(record.get("candidate_seat"), "candidate_seat")
        occurrences: list[tuple[int, int, str]] = []
        for step in range(first_step, final_step + 1):
            if step not in frames:
                continue
            for unit, operation in service_occurrences(frames[step]["actions"][seat]):
                occurrences.append((step, unit, operation))
        starts = sorted({step for step, _, _ in occurrences})
        for step in starts:
            baseline = replay_suffix(engine, record, step, final_step=final_step)
            baseline_checks += validate_baseline(record, baseline)
            baseline_starts += 1
            baseline_cache[(record_name, step)] = baseline
        for step, unit, operation in occurrences:
            baseline = baseline_cache[(record_name, step)]
            changed = replay_suffix(engine, record, step, omit_unit=unit,
                                    final_step=final_step)
            own = seat
            rival = 1 - seat
            own_state_before = {
                "farm": baseline.farms[own], "private": baseline.private,
            }
            own_state_after = {
                "farm": changed.farms[own], "private": changed.private,
            }
            state_delta = _delta(own_state_before, own_state_after)
            market_delta = _delta(baseline.market, changed.market)
            rows.append(Counterfactual(
                record_name,
                str(record.get("arm", "")),
                str(record.get("opponent", "")),
                _integer(record.get("seed"), "seed"),
                seat, step, unit, operation,
                float(changed.farms[own]["money"] - baseline.farms[own]["money"]),
                float(changed.farms[rival]["money"] - baseline.farms[rival]["money"]),
                digest(state_delta), digest(market_delta),
            ))
            fingerprints[occurrence_fingerprint(record, record_name, step, unit,
                                                final_step)] += 1

    operation_counts = Counter(row.operation for row in rows)
    step_counts = Counter(row.step for row in rows)
    own_deltas = [row.own_cash_delta for row in rows]
    rival_deltas = [row.rival_cash_delta for row in rows]
    margin_deltas = [row.margin_delta for row in rows]
    row_payload = [row.compact() for row in rows]
    return {
        "schema": "titan.backward-terminal-service.v1",
        "source_records": source_records,
        "baseline_starts": baseline_starts,
        "baseline_transition_checks": baseline_checks,
        "baseline_mismatches": 0,
        "candidate_occurrences": len(rows),
        "distinct_exact_candidates": len(fingerprints),
        "duplicate_occurrence_groups": sum(count > 1 for count in fingerprints.values()),
        "operations": dict(sorted(operation_counts.items())),
        "steps": {str(key): step_counts[key] for key in sorted(step_counts)},
        "own_cash_effects": {
            "positive": sum(value > 0 for value in own_deltas),
            "zero": sum(value == 0 for value in own_deltas),
            "negative": sum(value < 0 for value in own_deltas),
            "minimum": min(own_deltas) if own_deltas else None,
            "maximum": max(own_deltas) if own_deltas else None,
        },
        "rival_cash_effects": {
            "positive": sum(value > 0 for value in rival_deltas),
            "zero": sum(value == 0 for value in rival_deltas),
            "negative": sum(value < 0 for value in rival_deltas),
            "minimum": min(rival_deltas) if rival_deltas else None,
            "maximum": max(rival_deltas) if rival_deltas else None,
        },
        "margin_effects": {
            "positive": sum(value > 0 for value in margin_deltas),
            "zero": sum(value == 0 for value in margin_deltas),
            "negative": sum(value < 0 for value in margin_deltas),
            "minimum": min(margin_deltas) if margin_deltas else None,
            "maximum": max(margin_deltas) if margin_deltas else None,
        },
        "operation_ranges": {
            operation: {
                "own_cash_min": min(row.own_cash_delta for row in rows
                                    if row.operation == operation),
                "own_cash_max": max(row.own_cash_delta for row in rows
                                    if row.operation == operation),
                "rival_cash_min": min(row.rival_cash_delta for row in rows
                                      if row.operation == operation),
                "rival_cash_max": max(row.rival_cash_delta for row in rows
                                      if row.operation == operation),
            }
            for operation in sorted(operation_counts)
        },
        "counterfactual_rows_sha256": digest(row_payload),
        "candidate_fingerprints_sha256": digest(sorted(fingerprints.items())),
        "conclusion": (
            "preserve_all_observed_service_actions"
            if rows and all(row.own_cash_delta < 0 and row.margin_delta < 0 for row in rows)
            else "mixed_or_incomplete"
        ),
        "scope": (
            "Previously consumed development records; fixed authored suffix; "
            "exact per-unit opponent SELL availability; no agent calls, new games, "
            "probability model, current-policy promotion or hidden-state inference."
        ),
    }
