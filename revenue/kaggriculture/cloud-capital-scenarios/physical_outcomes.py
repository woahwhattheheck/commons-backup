# SPDX-License-Identifier: Apache-2.0
"""Bind completed RILL/T04 outcomes to DATE's existing paired-cash ranker.

No simulator or per-order fill reconstruction lives here. Completed whole-queue
cash is kept separate from nominal RouteQuote cash. The exact original own
observation, explicit scenario set, complete route bank and terminal horizon
must match. This is conditional own-cash utility, never rival margin.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from dated_scenarios import _field, _number, _rank_paired


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: Any) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), "integer horizon required")
    return value


def compare_replay(offers: Sequence[Any], observation: Mapping[str, Any],
                   replay: Mapping[str, Any], configuration: Mapping[str, Any], *,
                   scenario_ids: Sequence[str], minimum_gain: float = 0.0,
                   objective: str = "robust", scenario_weights: Mapping[str, Any] | None = None) -> dict:
    """Compare a complete physical scenario matrix; invalid input keeps incumbent.

    `scenario_ids` is the caller's explicit complete scenario bank, not inferred
    from whatever cases survived a timeout. Offers only supply route identities:
    their static market quotations do not overwrite actual executed receipts or
    charge failed fixed purchases a second time. Reuse only with the same live
    pre-action controller family/state that produced this replay. RILL binds the
    observation and offered program hashes, not arbitrary hidden controller state.
    """
    if not offers:
        raise ValueError("at least the incumbent offer is required")
    ids = [str(_field(offer, "route_id")) for offer in offers]
    margin = _number(minimum_gain)
    if len(set(ids)) != len(ids) or margin < 0:
        raise ValueError("distinct routes and a nonnegative improvement margin are required")
    names = tuple(scenario_ids)
    report = {
        "selected": ids[0], "incumbent": ids[0], "changed": False,
        "reason": "execution_report_invalid", "minimum_gain": margin,
        "scope": "completed_conditional_own_cash_over_explicit_scenarios_only",
        "scenarios": [], "candidates": {},
        "minimum_cash_scope": "observed_after_whole_market_queue_not_per_slot",
        "rival_utility": None,
    }
    if objective != "robust" or scenario_weights is not None:
        report["decision_objective"] = objective
    try:
        _require(bool(names) and all(isinstance(n, str) and n for n in names)
                 and len(set(names)) == len(names), "supply distinct explicit scenario ids")
        _require(replay["schema"] == "titan.capital-physical-replay.v1", "unsupported replay schema")
        _require(replay["complete"] is True, "replay is incomplete")
        _require(set(replay["scenarios"]) == set(names), "scenario bank differs")
        start = _integer(observation["step"])
        # Match replay_routes' default without adopting a possibly partial
        # report horizon. Explicit null/invalid/custom values remain checked.
        terminal = _integer(configuration.get("episodeSteps", 720)) - 2
        _require(0 <= start <= terminal, "invalid decision horizon")
        _require(_integer(replay["start_step"]) == start
                 and _integer(replay["end_step"]) == terminal, "replay is not this terminal horizon")
        _require(replay["observation_sha256"] == _digest(observation), "initial observation differs")
        _require(replay["original_route"] == ids[0], "incumbent differs")
        cash = _number(observation["farms"][int(observation["player"])]["money"])
        expected = {(route, name) for route in ids for name in names}
        indexed = {}
        programs = {}
        for case in replay["cases"]:
            key = (case["offered_route"], case["scenario_id"])
            _require(key in expected and key not in indexed, "duplicate or unexpected route/scenario case")
            _require(case["status"] == "complete", "case is incomplete or incompatible")
            _require(case["rival_cash_delta"] is None, "unsupported rival-cash model")
            program = case["program_sha256"]
            _require(isinstance(program, str) and len(program) == 64,
                     "missing offered program identity")
            _require(program == programs.setdefault(key[0], program), "offered program differs across scenarios")
            result = case["result"]
            _require(_integer(result["start_step"]) == start
                     and _integer(result["end_step"]) == terminal, "delegated horizon differs")
            rows = case["market_rows"]
            _require(len(rows) == terminal - start + 1, "incomplete market-queue history")
            previous = minimum = cash
            for step, row in enumerate(rows, start):
                before, after, delta = (_number(row[k]) for k in ("cash_before", "cash_after", "cash_delta"))
                _require(_integer(row["step"]) == step and before == previous,
                         "queue chronology or cash continuity differs")
                _require(after - before == delta, "queue cash delta differs")
                minimum, previous = min(minimum, after), after
            final = _number(case["final_cash"])
            _require(previous == final == _number(result["farm"]["money"]), "final cash differs")
            _require(final - cash == _number(case["cash_gain"]) == _number(result["cash_gain"]),
                     "cash gain differs")
            _require(minimum == _number(case["minimum_after_market_cash"]), "queue minimum differs")
            indexed[key] = {"complete": True, "final_executed_cash": final,
                            "minimum_after_market_cash": minimum}
        _require(set(indexed) == expected, "missing route/scenario case")
        report["scenarios"] = [
            {"name": name, "routes": {route: indexed[(route, name)] for route in ids}}
            for name in names]
        report.update(reason="no_covered_improvement", observation_sha256=replay["observation_sha256"],
                      start_step=start, terminal_step=terminal, offered_program_sha256=programs)
    except (KeyError, TypeError, ValueError, OverflowError, IndexError) as exc:
        report["invalid_input"] = str(exc)
        return report
    return _rank_paired(report, ids, margin, final_key="final_executed_cash",
                        minimum_key="minimum_after_market_cash",
                        budget_key="recorded_queue_cash_nonnegative",
                        improvement_reason="covered_executed_own_cash_improvement",
                        objective=objective, scenario_weights=scenario_weights)
