# SPDX-License-Identifier: Apache-2.0
"""Analyze existing executor rows without treating draw counts as random outcomes.

No policy import, simulator, network access, new games, seed selection or ranking
filter. Every successful paired cell contributes to the total-policy aggregate.
The path log contains counts, not weed coordinates or complete RNG state.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any


class InvalidResult(ValueError):
    """A result cannot support the requested paired analysis."""


def number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise InvalidResult(f"{name} must be a finite number")
    return float(value)


def day_index(path: Any) -> dict[int, dict] | None:
    if path is None:
        return None
    if not isinstance(path, list):
        raise InvalidResult("path must be a list or absent")
    result = {}
    for day in path:
        if not isinstance(day, dict) or type(day.get("day")) is not int or day["day"] < 0:
            raise InvalidResult("invalid path day")
        if day["day"] in result:
            raise InvalidResult("duplicate path day")
        farms = day.get("farms")
        if not isinstance(farms, list) or len(farms) != 2:
            raise InvalidResult("a path day must contain both farms")
        for farm in farms:
            if not isinstance(farm, dict):
                raise InvalidResult("invalid path farm")
            for key in ("empty_tiles_drawn", "weeds_spawned"):
                if type(farm.get(key)) is not int or farm[key] < 0:
                    raise InvalidResult(f"invalid {key}")
        if type(day.get("draws_before_shop")) is not int or day["draws_before_shop"] < 0:
            raise InvalidResult("invalid draws_before_shop")
        if day["draws_before_shop"] != sum(f["empty_tiles_drawn"] for f in farms):
            raise InvalidResult("draw total disagrees with recorded farm counts")
        if "shop_unlocked" not in day or not (day["shop_unlocked"] is None or isinstance(day["shop_unlocked"], str)):
            raise InvalidResult("missing or invalid shop event")
        result[day["day"]] = day
    return result


def compare_paths(control: Any, candidate: Any) -> dict:
    """Separate recorded input counts from recorded shop/weed-count outcomes.

    Equal weed counts do NOT prove equal weed coordinates. Even an exact match
    in every field does not certify identical full states or RNG streams.
    """
    a, b = day_index(control), day_index(candidate)
    result = dict(status="missing", days_compared=[], missing_control_days=[],
                  missing_candidate_days=[], changed_counter_days=[],
                  changed_logged_event_days=[], counter_only_days=[],
                  equal_logged_event_days=[], exact_record_difference_days=[],
                  spatial_weed_equivalence="not_recorded", rng_state_equivalence="not_recorded")
    if a is None or b is None:
        return result
    common = sorted(a.keys() & b.keys())
    result.update(status="complete_for_recorded_days", days_compared=common,
                  missing_control_days=sorted(b.keys() - a.keys()),
                  missing_candidate_days=sorted(a.keys() - b.keys()))
    if not common or a.keys() != b.keys():
        result["status"] = "incomplete_recorded_days"
    for day in common:
        x, y = a[day], b[day]
        counts_changed = (x["draws_before_shop"] != y["draws_before_shop"] or
                          [f["empty_tiles_drawn"] for f in x["farms"]] !=
                          [f["empty_tiles_drawn"] for f in y["farms"]])
        events_changed = (x["shop_unlocked"] != y["shop_unlocked"] or
                          [f["weeds_spawned"] for f in x["farms"]] !=
                          [f["weeds_spawned"] for f in y["farms"]])
        if x != y:
            result["exact_record_difference_days"].append(day)
        if counts_changed:
            result["changed_counter_days"].append(day)
        result["changed_logged_event_days" if events_changed else "equal_logged_event_days"].append(day)
        if counts_changed and not events_changed:
            result["counter_only_days"].append(day)
    return result


def outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "T"


def summarize(pairs: list[dict]) -> dict:
    return dict(pairs=len(pairs),
                mean_delta={k: mean(p["delta"][k] for p in pairs) if pairs else None
                            for k in ("own_cash", "rival_cash", "margin")},
                control_outcomes=dict(Counter(p["control_outcome"] for p in pairs)),
                candidate_outcomes=dict(Counter(p["candidate_outcome"] for p in pairs)),
                outcome_transitions=dict(Counter(p["control_outcome"] + "->" + p["candidate_outcome"] for p in pairs)))


def analyze(data: dict, control_arm: str = "control", candidate_arm: str = "candidate") -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise InvalidResult("input must contain a rows list")
    if not control_arm or not candidate_arm or control_arm == candidate_arm:
        raise InvalidResult("two distinct arm names are required")
    indexed = {}
    ignored_arms = Counter()
    for row in data["rows"]:
        if not isinstance(row, dict):
            raise InvalidResult("each result row must be a mapping")
        arm = row.get("arm")
        if not isinstance(arm, str):
            raise InvalidResult("row arm must be a string")
        if arm not in (control_arm, candidate_arm):
            ignored_arms[arm] += 1
            continue
        seed, seat, opponent = row.get("seed"), row.get("seat"), row.get("opponent")
        if type(seed) is not int or type(seat) is not int or seat not in (0, 1) or not isinstance(opponent, str) or not opponent:
            raise InvalidResult("invalid cell identity")
        key = (seed, seat, opponent, arm)
        if key in indexed:
            raise InvalidResult(f"duplicate cell: {key}")
        indexed[key] = row
    cells = sorted({key[:3] for key in indexed})
    pairs, missing, failed = [], [], []
    for cell in cells:
        a = indexed.get((*cell, control_arm))
        b = indexed.get((*cell, candidate_arm))
        identity = dict(seed=cell[0], seat=cell[1], opponent=cell[2])
        if a is None or b is None:
            missing.append(dict(**identity, absent=control_arm if a is None else candidate_arm))
            continue
        if a.get("error") is not None or b.get("error") is not None:
            failed.append(dict(**identity, control_error=a.get("error"), candidate_error=b.get("error")))
            continue
        # These are launcher hashes, not proof of an entire dependency closure.
        metadata = [r.get("opponent_id", {}) for r in (a, b)]
        if not all(isinstance(item, dict) for item in metadata):
            raise InvalidResult("opponent_id must be a mapping when provided")
        pins = [item.get("sha256") for item in metadata]
        if "rounds" in a or "rounds" in b:
            if any(type(r.get("rounds")) is not int or r["rounds"] <= 0 for r in (a, b)) or a["rounds"] != b["rounds"]:
                raise InvalidResult("paired rows must record the same positive round count")
        if pins[0] != pins[1]:
            raise InvalidResult(f"opponent launcher identity differs in cell {cell}")
        cash = [{k: number(r.get(k), k) for k in ("own_cash", "rival_cash")} for r in (a, b)]
        for r, value in zip((a, b), cash):
            value["margin"] = value["own_cash"] - value["rival_cash"]
            if "margin" in r and not math.isclose(number(r["margin"], "margin"), value["margin"], rel_tol=0, abs_tol=1e-9):
                raise InvalidResult("recorded margin disagrees with own minus rival cash")
        path = compare_paths(a.get("path"), b.get("path"))
        pairs.append(dict(**identity, control=cash[0], candidate=cash[1],
                          delta={k: cash[1][k] - cash[0][k] for k in cash[0]},
                          control_outcome=outcome(cash[0]["margin"]),
                          candidate_outcome=outcome(cash[1]["margin"]),
                          zero_rival_control=cash[0]["rival_cash"] == 0,
                          opponent_launcher_sha256=pins[0],
                          path_diagnostics=path,
                          reported_path_divergent_days=b.get("path_divergent_days")))
    event_same = [p for p in pairs if p["path_diagnostics"]["status"] == "complete_for_recorded_days" and not p["path_diagnostics"]["changed_logged_event_days"]]
    event_changed = [p for p in pairs if p["path_diagnostics"]["changed_logged_event_days"]]
    path_unknown = [p for p in pairs if p["path_diagnostics"]["status"] != "complete_for_recorded_days"]
    return dict(schema="titan.recorded-comparison.v1", control_arm=control_arm,
                candidate_arm=candidate_arm, trace_scope=data.get("trace_scope", "recorded_days_only; completeness_not_certified"),
                input_provenance=data.get("provenance"),
                recorded_entrypoints={k: data.get(k) for k in ("control", "candidate")},
                total_policy=summarize(pairs),
                diagnostics=dict(equal_logged_events=summarize(event_same),
                                 changed_logged_events=summarize(event_changed),
                                 incomplete_paths=summarize(path_unknown),
                                 zero_rival_control_pairs=sum(p["zero_rival_control"] for p in pairs)),
                missing_cells=missing, failed_cells=failed, ignored_arms=dict(ignored_arms),
                pairs=pairs, source_closure_verified=False,
                limitations=["All successful pairs remain in total_policy, including event-divergent pairs.",
                             "Path strata are descriptive, post-action subsets, not randomized comparisons.",
                             "Equal logged event counts do not establish equal spatial weeds, full states or RNG streams.",
                             "Equal final cash across seats does not establish independent samples.",
                             "Missing and failed cells are explicit, never zero-filled or silently scored as wins."])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--control", default="control")
    parser.add_argument("--candidate", default="candidate")
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        report = analyze(json.loads(raw), args.control, args.candidate)
        report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    except (OSError, json.JSONDecodeError, InvalidResult, TypeError) as error:
        parser.exit(2, f"Invalid recorded comparison: {error}\n")
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 2 if report["missing_cells"] or report["failed_cells"] or not report["total_policy"]["pairs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
