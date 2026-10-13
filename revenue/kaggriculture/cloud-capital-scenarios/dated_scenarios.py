# SPDX-License-Identifier: Apache-2.0
"""Dated cash-scenario callback for HAZEL's complete RouteQuote offers.

No scenario is generated here. Callers supply total signed cash settlements for
EVERY future SELL and BUY_PRODUCT row, separately for each route and scenario.
Other costs and market-slot order come from the supplied RouteQuote. Quantities,
fixed costs and successful execution remain assumptions of that quotation: this
is nominal ordered-budget comparison, not a physical-feasibility certificate,
a calibrated forecast, or a guarantee over omitted worlds.

The opt-in completed-replay path uses the same ranking rule on RILL/T04 executed
terminal own cash. It does not reinterpret whole-queue receipts as per-slot fills.
The robust objective remains default; expected_cash and minimax_regret are explicit
opt-in decision assumptions, not calibrated probabilities or game-win claims.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

VARIABLE = frozenset(("SELL", "BUY_PRODUCT"))
FIXED = frozenset(("BUY_ANIMAL", "BUY_SEED", "BUY_LAND", "HIRE", "PASS"))


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("cash values cannot be booleans")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("cash values must be finite")
    return result


def _field(offer: Any, name: str) -> Any:
    return offer[name] if isinstance(offer, Mapping) else getattr(offer, name)


@dataclass(frozen=True)
class CashScenario:
    """Route id -> (step, slot) -> total signed settlement, not a unit price.

    SELL totals must be nonnegative and BUY_PRODUCT totals nonpositive. Zero
    explicitly represents no receipt/no purchase. Missing is UNKNOWN, not zero.
    Scenarios must describe alternative continuations of the SAME public state.
    """
    name: str
    flows: Mapping[str, Mapping[tuple[int, int], float]]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CashScenario":
        routes = {}
        for route_id, rows in value["flows"].items():
            indexed = {}
            for row in rows:
                key = (row["step"], row["slot"])
                if key in indexed:
                    raise ValueError(f"duplicate scenario row: {route_id} {key}")
                indexed[key] = row["delta"]
            routes[route_id] = indexed
        return cls(str(value["name"]), routes)


def _rows(offer: Any, now: int) -> tuple[Mapping[str, Any], ...]:
    rows = tuple(_field(offer, "orders"))
    last = (now, -1)
    for row in rows:
        step, slot = row["step"], row["slot"]
        if (not isinstance(step, int) or isinstance(step, bool)
                or not isinstance(slot, int) or isinstance(slot, bool)
                or slot < 0 or (step, slot) <= last):
            raise ValueError("offer rows must have unique, chronological integer step/slot keys")
        order = row["order"]
        if not order or order[0] not in VARIABLE | FIXED:
            raise ValueError("unsupported or empty route order")
        delta = _number(row["delta"])
        if order[0] in FIXED and (delta > 0 or (order[0] == "PASS" and delta != 0)):
            raise ValueError("fixed purchase/labor rows cannot create cash")
        last = (step, slot)
    return rows


def _price(route_id: str, rows: Sequence[Mapping[str, Any]], start: float,
           scenario: CashScenario) -> dict[str, Any]:
    flows = scenario.flows.get(route_id, {})
    cash = minimum = start
    first_negative = None
    missing, invalid = [], []
    priced = 0
    for row in rows:
        key = (row["step"], row["slot"])
        op = row["order"][0]
        if op in VARIABLE:
            if key not in flows:
                missing.append(list(key))
                continue
            try:
                delta = _number(flows[key])
                if (op == "SELL" and delta < 0) or (op == "BUY_PRODUCT" and delta > 0):
                    raise ValueError("settlement sign disagrees with order")
            except (TypeError, ValueError, OverflowError):
                invalid.append(list(key))
                continue
            priced += 1
        else:
            delta = _number(row["delta"])
        cash += delta
        if not math.isfinite(cash):
            invalid.append(list(key))
            break
        minimum = min(minimum, cash)
        if cash < 0 and first_negative is None:
            first_negative = list(key)
    complete = not missing and not invalid
    return {
        "complete": complete,
        "final_nominal_cash": cash if complete else None,
        "minimum_nominal_cash": minimum if complete else None,
        "first_negative": first_negative if complete else None,
        "priced_variable_rows": priced,
        "missing_rows": missing,
        "invalid_rows": invalid,
    }


def compare_routes(offers: Sequence[Any], observation: Mapping[str, Any],
                   scenarios: Sequence[CashScenario], *, minimum_gain: float = 0.0,
                   objective: str = "robust", scenario_weights: Mapping[str, Any] | None = None
                   ) -> dict[str, Any]:
    """Maximize the worst PAIRED cash gain over every supplied scenario.

    Offer zero is the incumbent. Alternatives require complete coverage for
    themselves AND the incumbent in every scenario and a nonnegative ordered
    nominal budget throughout. Ties retain the incumbent/earlier offered route.
    A missing scenario input cannot be discarded to improve the comparison.
    """
    if not offers:
        raise ValueError("at least the incumbent offer is required")
    margin = _number(minimum_gain)
    if margin < 0:
        raise ValueError("minimum_gain must be nonnegative")
    ids = [str(_field(offer, "route_id")) for offer in offers]
    if len(set(ids)) != len(ids):
        raise ValueError("route ids must be unique")
    names = [scenario.name for scenario in scenarios]
    if len(set(names)) != len(names):
        raise ValueError("scenario names must be unique")
    now = observation["step"]
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise ValueError("observation step must be a nonnegative integer")
    start = _number(observation["farms"][int(observation["player"])]["money"])
    route_rows = [_rows(offer, now) for offer in offers]
    report = {
        "selected": ids[0], "incumbent": ids[0], "changed": False,
        "reason": "no_scenarios" if not scenarios else "no_covered_improvement",
        "scope": "nominal_ordered_budget_over_supplied_scenarios_only",
        "minimum_gain": margin, "scenarios": [], "candidates": {},
    }
    for scenario in scenarios:
        report["scenarios"].append({
            "name": scenario.name,
            "routes": {key: _price(key, rows, start, scenario)
                       for key, rows in zip(ids, route_rows)},
        })
    return _rank_paired(report, ids, margin, objective=objective, scenario_weights=scenario_weights)


def _rank_paired(report: dict, ids: Sequence[str], margin: float, *,
                 final_key: str = "final_nominal_cash",
                 minimum_key: str = "minimum_nominal_cash",
                 budget_key: str = "nominal_budget_nonnegative",
                 improvement_reason: str = "covered_nominal_improvement",
                 objective: str = "robust", scenario_weights: Mapping[str, Any] | None = None) -> dict:
    """One paired-cash ordering rule, with explicit input-specific budget labels."""
    alternate_objective = objective != "robust" or scenario_weights is not None
    if alternate_objective:
        report["decision_objective"] = objective
        report["probabilities_calibrated"] = False
        report["rival_utility"] = None
    if not report["scenarios"]:
        return report
    if any(not item["routes"][ids[0]]["complete"] for item in report["scenarios"]):
        report["reason"] = "incumbent_scenario_incomplete"
        return report
    best_gain = margin
    for key in ids[1:]:
        values = [item["routes"][key] for item in report["scenarios"]]
        complete = all(value["complete"] for value in values)
        gains = [] if not complete else [
            item["routes"][key][final_key]
            - item["routes"][ids[0]][final_key]
            for item in report["scenarios"]]
        complete = complete and all(math.isfinite(gain) for gain in gains)
        funded = complete and all(value[minimum_key] >= 0 for value in values)
        worst = min(gains) if complete else None
        report["candidates"][key] = {
            "complete": complete, budget_key: funded,
            "worst_paired_gain": worst,
        }
        if not alternate_objective and funded and worst > best_gain + 1e-9:
            best_gain = worst
            report.update(selected=key, changed=True, reason=improvement_reason)
    if alternate_objective:
        return _rank_objective(report, ids, margin, final_key, minimum_key, budget_key,
                               objective, scenario_weights)
    return report


def _rank_objective(report, ids, margin, final_key, minimum_key, budget_key,
                    objective, scenario_weights):
    """Opt-in pure-route objectives over the already validated cash matrix.

    Regret compares with the best eligible whole route in each scenario, but
    returns ONE route for every scenario, not an oracle contingent action.
    Expected cash uses declared weights, never frequencies inferred from cases.
    All scenarios, including zero-weight ones, must remain covered and funded.
    Arithmetic is exact over decimal representations of the validated values;
    it does not recover precision already lost by the input's cash conversion.
    """
    try:
        if objective not in ("expected_cash", "minimax_regret"):
            raise ValueError("choose robust, expected_cash or minimax_regret explicitly")
        names = [item["name"] for item in report["scenarios"]]
        if len(set(names)) != len(names):
            raise ValueError("scenario identities must be unique")
        baseline_values = [item["routes"][ids[0]] for item in report["scenarios"]]
        if any(value[minimum_key] < 0 for value in baseline_values):
            report["reason"] = "incumbent_budget_unsupported"
            return report
        eligible = [ids[0]] + [key for key in ids[1:]
                    if report["candidates"][key][budget_key]]
        matrix = {key: tuple(Fraction(str(item["routes"][key][final_key]))
                             for item in report["scenarios"]) for key in eligible}
        report["eligible_routes"] = eligible
        report["objective_values"] = {}
        report["objective_arithmetic"] = "exact_rational_over_validated_cash_values"
        required_gain = Fraction(str(margin))
        scores = {}
        if objective == "expected_cash":
            if not isinstance(scenario_weights, Mapping) or set(scenario_weights) != set(names):
                raise ValueError("expected_cash needs one explicit weight for EVERY named scenario")
            weights = []
            for name in names:
                value = scenario_weights[name]
                if isinstance(value, bool) or not isinstance(value, (int, float, str, Fraction)):
                    raise ValueError("weights must be finite rational values, not booleans")
                weights.append(Fraction(str(value)) if isinstance(value, float) else Fraction(value))
            if any(w < 0 for w in weights) or sum(weights) != 1:
                raise ValueError("weights must be nonnegative and sum EXACTLY to one")
            report["scenario_weights"] = {name: str(w) for name, w in zip(names, weights)}
            report["weight_scope"] = "caller_assumptions_over_this_complete_bank_not_inferred_probabilities"
            expected = {key: sum((w * cash for w, cash in zip(weights, values)), Fraction(0))
                        for key, values in matrix.items()}
            for key, value in expected.items():
                scores[key] = value - expected[ids[0]]
                report["objective_values"][key] = {
                    "expected_own_cash": str(value),
                    "expected_paired_gain": str(scores[key])}
            reason = "declared_expected_own_cash_improvement"
        else:
            if scenario_weights is not None:
                raise ValueError("minimax_regret does not use scenario weights")
            best = tuple(max(values[j] for values in matrix.values()) for j in range(len(names)))
            regret = {key: tuple(upper - cash for upper, cash in zip(best, values))
                      for key, values in matrix.items()}
            maxima = {key: max(values) for key, values in regret.items()}
            report["scenario_weights"] = None
            report["regret_comparator"] = "best_eligible_whole_route_per_scenario_for_scoring_only"
            report["scenario_best_own_cash"] = {name: str(v) for name, v in zip(names, best)}
            for key, values in regret.items():
                scores[key] = maxima[ids[0]] - maxima[key]
                report["objective_values"][key] = {
                    "scenario_regret": {name: str(v) for name, v in zip(names, values)},
                    "worst_regret": str(maxima[key]),
                    "worst_regret_reduction": str(scores[key])}
            reason = "declared_minimax_regret_improvement"
        # Exact ties retain incumbent or the earlier offered alternative.
        best_gain = required_gain
        for key in eligible[1:]:
            if scores[key] > best_gain:
                best_gain = scores[key]
                report.update(selected=key, changed=True, reason=reason)
        return report
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        report.update(selected=ids[0], changed=False, reason="objective_input_invalid",
                      invalid_objective_input=str(exc))
        return report


class DatedSelector:
    """Pass this directly to choose_before_action(..., selector=selector).

    Build it anew from the current public-state scenarios at the checkpoint.
    last_report preserves the scenario comparison; HAZEL's existing outer report
    still describes its original quote screen and does not embed this report.
    """
    def __init__(self, scenarios: Sequence[CashScenario], *, minimum_gain: float = 0.0,
                 objective: str = "robust", scenario_weights: Mapping[str, Any] | None = None):
        self.scenarios = tuple(scenarios)
        self.minimum_gain = minimum_gain
        self.objective = objective
        self.scenario_weights = dict(scenario_weights) if isinstance(scenario_weights, Mapping) else scenario_weights
        self.last_report: dict[str, Any] | None = None
        self._completed_replay = None

    @classmethod
    def from_completed_replay(cls, replay: Mapping[str, Any],
                              configuration: Mapping[str, Any], *,
                              scenario_ids: Sequence[str], minimum_gain: float = 0.0,
                              objective: str = "robust", scenario_weights: Mapping[str, Any] | None = None):
        """Opt-in RILL input bridge; no simulation and no inferred scenario subset.

        The report is read-only input, not copied or mutated. Validation runs on
        every invocation against the current observation, offer IDs and supplied
        horizon. Retain the original replay beside last_report for provenance.
        The supplied configuration must belong to the same replay execution.
        """
        selector = cls((), minimum_gain=minimum_gain, objective=objective, scenario_weights=scenario_weights)
        selector._completed_replay = (replay, dict(configuration), tuple(scenario_ids))
        return selector

    def __call__(self, offers: Sequence[Any], observation: Mapping[str, Any]) -> str:
        if self._completed_replay is None:
            self.last_report = compare_routes(offers, observation, self.scenarios,
                                              minimum_gain=self.minimum_gain,
                                              objective=self.objective, scenario_weights=self.scenario_weights)
        else:
            from physical_outcomes import compare_replay
            replay, configuration, names = self._completed_replay
            self.last_report = compare_replay(offers, observation, replay, configuration,
                                              scenario_ids=names, minimum_gain=self.minimum_gain,
                                              objective=self.objective, scenario_weights=self.scenario_weights)
        return self.last_report["selected"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON: offers, observation, scenarios; optional minimum_gain")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = compare_routes(data["offers"], data["observation"],
                                [CashScenario.from_dict(s) for s in data["scenarios"]],
                                minimum_gain=data.get("minimum_gain", 0),
                                objective=data.get("objective", "robust"),
                                scenario_weights=data.get("scenario_weights"))
    except (OSError, KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
