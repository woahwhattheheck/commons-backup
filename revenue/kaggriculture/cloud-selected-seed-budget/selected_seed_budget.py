# SPDX-License-Identifier: Apache-2.0
"""Seed-purchase bounds for explicitly supplied complete selected continuations.

No controller is imported or called. No future purchase is credited as stock.
The caller supplies the actual post-unit seed inventory and ALL remaining own
continuations. Incomplete or stale contracts leave the selected action unchanged.
This bounds seed demand, not route feasibility, cash improvement, or game strength.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

CROPS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"))
MAX_BRANCHES = 16
MAX_ROWS = 12000
VERSION = 1


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _context(observation: Mapping[str, Any],
             configuration: Mapping[str, Any] | None) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Resolve a redundant public clock without changing caller-owned inputs.

    A supplied, non-null step retains precedence and the original strict integer
    contract. Otherwise day/hour and the configured period must identify it;
    missing or malformed clocks are not silently interpreted as a new match.
    """
    if not isinstance(observation, Mapping):
        raise ValueError("observation must be a mapping")
    if configuration is None:
        configuration = {}
    if not isinstance(configuration, Mapping):
        raise ValueError("configuration must be a mapping or None")
    if observation.get("step") is not None:
        _integer(observation["step"], "step")
        return observation, configuration
    day = _integer(observation["day"], "day")
    hour = _integer(observation["hour"], "hour")
    period = _integer(configuration.get("turnsPerDay", 24), "turnsPerDay", 1)
    if hour >= period:
        raise ValueError("hour must be below turnsPerDay")
    normalized = dict(observation)
    normalized["step"] = day * period + hour
    return normalized, configuration


def _stock(value: Mapping[str, int], name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result = {}
    for crop, quantity in value.items():
        if crop not in CROPS:
            raise ValueError(f"Unknown crop in {name}: {crop}")
        result[crop] = _integer(quantity, name)
    return result


def _rules(configuration: Mapping[str, Any]) -> tuple[int, int]:
    return (_integer(configuration.get("episodeSteps", 720), "episodeSteps", 2) - 2,
            _integer(configuration.get("maxMarketOrdersPerTurn", 10), "maxMarketOrdersPerTurn", 1))


def _binding(observation, configuration, selected_action, post_unit_seeds) -> str:
    step = _integer(observation["step"], "step")
    seat = _integer(observation["player"], "player")
    if seat not in (0, 1):
        raise ValueError("player must be 0 or 1")
    # Bind visible public state and only the actor's own private state.
    context = {"step": step, "player": seat, "rules": _rules(configuration),
               "public_farms": observation["farms"],
               "public_market": observation.get("market"), "public_town": observation.get("town"),
               "day": observation.get("day"), "hour": observation.get("hour"),
               "own_private": observation["private"],
               "action": selected_action, "post_unit_seeds": _stock(post_unit_seeds, "post_unit_seeds")}
    return hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SeedDemandContract:
    version: int
    observed_step: int
    final_step: int
    context_sha256: str
    complete: bool
    reason: str
    # Immutable per-branch counts, not a sampled/weighted expected demand.
    branch_demands: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    reserves: tuple[tuple[str, int], ...]

    def bounds(self) -> dict[str, int]:
        result = dict(self.reserves)
        for crop in CROPS:
            n = max((dict(counts).get(crop, 0) for _, counts in self.branch_demands), default=0)
            result[crop] = result.get(crop, 0) + n
        return result


def compile_demand(observation: Mapping[str, Any], configuration: Mapping[str, Any] | None,
                   selected_action: Mapping[str, Any], *, post_unit_seeds: Mapping[str, int],
                   continuations: Mapping[str, Sequence[Mapping[str, Any]]], complete: bool,
                   reserves: Mapping[str, int] | None = None) -> SeedDemandContract:
    """Compile every dated PLANT request strictly AFTER current units through DONE.

    Each branch must explicitly cover step+1 .. episodeSteps-2, including PASS
    rows. Count requests even on blocked/occupied tiles or nonexistent workers:
    their possible no-op status is not a license to underfund another branch.
    Future BUY_SEED orders do not reduce demand. complete=True is the caller's
    assertion of branch coverage; the compiler cannot prove that assertion.
    """
    observation, configuration = _context(observation, configuration)
    final, _ = _rules(configuration)
    step = _integer(observation["step"], "step")
    if step > final:
        raise ValueError("Observation is beyond the last executable decision")
    context = _binding(observation, configuration, selected_action, post_unit_seeds)
    reserve = tuple(sorted(_stock(reserves or {}, "reserves").items()))

    def result(ok, reason, branches=()):
        return SeedDemandContract(VERSION, step, final, context, ok, reason, tuple(branches), reserve)

    if complete is not True:
        return result(False, "caller_continuation_incomplete")
    if not isinstance(continuations, Mapping) or not continuations:
        return result(False, "no_explicit_continuation")
    if len(continuations) > MAX_BRANCHES:
        return result(False, "branch_budget_exceeded")
    if (final - step) * len(continuations) > MAX_ROWS:
        return result(False, "row_budget_exceeded")
    branches = []
    for name, rows in continuations.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Each continuation needs a nonempty name")
        if not isinstance(rows, (list, tuple)) or len(rows) != final - step:
            return result(False, "continuation_horizon_incomplete")
        counts = Counter()
        for expected_step, row in enumerate(rows, step + 1):
            if not isinstance(row, Mapping) or type(row.get("step")) is not int or row["step"] != expected_step:
                return result(False, "continuation_steps_not_contiguous")
            action = row.get("action")
            if not isinstance(action, Mapping):
                return result(False, "continuation_action_missing")
            hands = action.get("hands", [])
            if not isinstance(hands, list):
                # The engine normalizes this to no hands, but a partial producer
                # packet should not silently become a complete demand contract.
                return result(False, "continuation_hands_malformed")
            for unit in [action.get("farmer", ["PASS"]), *hands]:
                if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT":
                    if unit[1] not in CROPS:
                        return result(False, "unknown_plant_crop")
                    counts[unit[1]] += 1
        branches.append((name, tuple(sorted(counts.items()))))
    return result(True, "complete_explicit_continuations", branches)


def transform(observation: Mapping[str, Any], configuration: Mapping[str, Any] | None,
              selected_action: Mapping[str, Any], *, post_unit_seeds: Mapping[str, int],
              contract: SeedDemandContract | None) -> dict[str, Any]:
    """Return action + diagnostic changes; untouched action is the fallback.

    Only positive integer BUY_SEED quantities in executable slots are trimmed.
    Empty replacements retain the slot. Each order starts from OBSERVED stock,
    never the requested quantity of an earlier possibly cash-limited purchase.
    Repeated affordable orders can therefore still overbuy; this is conservative.
    """
    out = {"action": deepcopy(selected_action), "status": "UNCHANGED", "changes": [],
           "reason": "missing_or_incomplete_contract"}
    if not isinstance(contract, SeedDemandContract) or not contract.complete:
        return out
    try:
        observation, configuration = _context(observation, configuration)
        stock = _stock(post_unit_seeds, "post_unit_seeds")
        final, max_orders = _rules(configuration)
        binding = _binding(observation, configuration, selected_action, stock)
    except (ValueError, TypeError, KeyError, IndexError):
        out["reason"] = "invalid_current_context"
        return out
    if (contract.version != VERSION or contract.context_sha256 != binding
            or contract.observed_step != observation["step"] or contract.final_step != final):
        out["reason"] = "stale_or_different_context"
        return out
    market = out["action"].get("market", [])
    if not isinstance(market, list):
        out["reason"] = "selected_market_not_a_list"
        return out
    bounds = contract.bounds()
    for slot, order in enumerate(market[:max_orders]):
        if (not isinstance(order, list) or len(order) < 3 or order[0] != "BUY_SEED"
                or order[1] not in CROPS or type(order[2]) is not int or order[2] <= 0):
            continue
        crop, requested = order[1], order[2]
        retained = min(requested, max(0, bounds[crop] - stock.get(crop, 0)))
        if retained == requested:
            continue
        if retained:
            replacement = deepcopy(order)
            replacement[2] = retained
        else:
            replacement = []
        market[slot] = replacement
        out["changes"].append({"slot": slot, "crop": crop, "requested": requested,
                               "retained": retained, "post_unit_stock": stock.get(crop, 0),
                               "remaining_request_bound_plus_reserve": bounds[crop]})
    out.update(status="TRANSFORMED" if out["changes"] else "UNCHANGED",
               reason="complete_demand_bound", remaining_request_bounds=bounds)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="JSON containing own observation, selected action, and continuations")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    contract = compile_demand(case["observation"], case.get("configuration", {}), case["selected_action"],
                              post_unit_seeds=case["post_unit_seeds"],
                              continuations=case.get("continuations", {}), complete=case.get("complete", False),
                              reserves=case.get("reserves"))
    result = transform(case["observation"], case.get("configuration", {}), case["selected_action"],
                       post_unit_seeds=case["post_unit_seeds"], contract=contract)
    result["contract"] = asdict(contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "changes": len(result["changes"]),
                      "contract_complete": contract.complete}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
