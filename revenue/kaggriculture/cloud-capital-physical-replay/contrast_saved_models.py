# SPDX-License-Identifier: Apache-2.0
"""Compare saved physical and nominal route outcomes without executing either model.

Queue-cash differences are bookkeeping across different trajectories, not causal
per-product effects. The existing observation normalizer binds the shared input.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def cash(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        raise ValueError("This recorded comparison requires finite whole game cash")
    return int(value)


def indexed(orders):
    return [[slot, order] for slot, order in enumerate(orders) if order]


def effective(queue):
    # Keep ORIGINAL slot indices. An omitted zero request does not compact the
    # slots of a later order, and an emitted request is still not a fill receipt.
    return [[slot, order] for slot, order in queue if order[0] != "PASS" and
            not (len(order) >= 3 and cash(order[2]) <= 0)]


def compare_reports(physical, nominal, normalized_input):
    if physical.get("complete") is not True or nominal.get("complete") is not True:
        raise ValueError("Supply two completed reports; partial cases have no comparison")
    replay = physical["replay"]
    if replay.get("complete") is not True or nominal["flow"].get("complete") is not True:
        raise ValueError("Underlying case bank is incomplete")
    obs = normalized_input["observation"]
    if digest(normalized_input) != nominal["input_sha256"] or digest(obs) != replay["observation_sha256"]:
        raise ValueError("Reports describe different original inputs")
    if obs != physical["validation"]["input_row"]["observation"]:
        raise ValueError("Physical source observation differs")
    first, last = replay["start_step"], replay["end_step"]
    if first != nominal["step"] or nominal["seat"] != obs["player"]:
        raise ValueError("Comparison clock or seat differs")
    nominal_cases = {}
    for group in nominal["flow"]["rows"]:
        for row in group:
            key = (row["route_id"], row["scenario"])
            if key in nominal_cases or row.get("complete") is not True:
                raise ValueError("Duplicate or incomplete nominal case")
            nominal_cases[key] = row
    scenarios = {s["name"]: s for s in nominal["scenario_specifications"]}
    if len(scenarios) != len(nominal["scenario_specifications"]) or set(scenarios) != set(replay["scenarios"]):
        raise ValueError("Scenario coverage differs")
    for name, source in replay["scenarios"].items():
        spec = scenarios[name]
        additions = {str(int(k) + 1): v for k, v in source.get("new_shops", {}).items()}
        if additions != spec.get("shop_additions", {}) or source.get("market_deltas") or source.get("new_weeds"):
            raise ValueError("Declared future events are not the same comparison")
    output, seen = [], set()
    for physical_case in replay["cases"]:
        key = physical_case["offered_route"], physical_case["scenario_id"]
        if key in seen or key not in nominal_cases or physical_case.get("status") != "complete":
            raise ValueError("Duplicate, missing or incomplete physical case")
        seen.add(key)
        source = nominal_cases[key]
        if physical_case["program_sha256"] != nominal["program_sha256"][key[0]]:
            raise ValueError("Offered program identity differs")
        by_step, slots = defaultdict(list), set()
        for row in source["trace"]:
            slot_key = row["step"], row["slot"]
            if not first <= row["step"] <= last or slot_key in slots:
                raise ValueError("Nominal trace has an out-of-window or duplicate slot")
            slots.add(slot_key)
            by_step[row["step"]].append(row)
        rows = physical_case["market_rows"]
        if [row["step"] for row in rows] != list(range(first, last + 1)):
            raise ValueError("Physical queue trace is incomplete or unordered")
        initial = cash(obs["farms"][obs["player"]]["money"])
        if cash(source["initial_cash"]) != initial:
            raise ValueError("Opening cash differs")
        nc = pc = initial
        ledger, first_queue, first_effective, first_cash = [], None, None, None
        changed_sum = unchanged_sum = changed = effective_changed = 0
        for row in rows:
            step = row["step"]
            records = sorted(by_step[step], key=lambda x: x["slot"])
            nq = [[r["slot"], r["order"]] for r in records]
            pq = indexed(row["orders"])
            nd = sum(cash(r["own_delta"]) for r in records)
            pd = cash(row["cash_delta"])
            if cash(row["cash_before"]) != pc or cash(row["cash_after"]) != pc + pd:
                raise ValueError("Physical whole-queue cash does not reconcile")
            nc += nd
            pc += pd
            qchanged, echanged = pq != nq, effective(pq) != effective(nq)
            changed += qchanged
            effective_changed += echanged
            delta = pd - nd
            if qchanged: changed_sum += delta
            else: unchanged_sum += delta
            witness = {"step": step, "nominal_indexed_orders": nq,
                       "physical_indexed_orders": pq, "physical_shed_before": row["private_before"]["shed"],
                       "physical_shed_after": row["private_after"]["shed"],
                       "nominal_cash_delta": nd, "physical_cash_delta": pd,
                       "cash_delta_difference": delta, "cumulative_cash_difference": pc - nc}
            if qchanged and first_queue is None: first_queue = witness
            if echanged and first_effective is None: first_effective = witness
            if delta and first_cash is None: first_cash = witness
            ledger.append({"step": step, "nominal_cash_delta": nd, "physical_cash_delta": pd,
                "delta": delta, "cumulative": pc - nc, "same_indexed_queue": not qchanged})
        if nc != cash(source["final_marked_cash"]) or pc != cash(physical_case["final_cash"]):
            raise ValueError("Terminal cash does not reconcile with saved queues")
        if sum(r["delta"] for r in ledger) != pc - nc or changed_sum + unchanged_sum != pc - nc:
            raise AssertionError("Cash bridge failed")
        output.append({"route": key[0], "scenario": key[1], "queues": len(ledger),
            "nominal_final_cash": nc, "physical_final_cash": pc, "physical_minus_nominal": pc - nc,
            "changed_indexed_queues": changed, "changed_effective_queues": effective_changed,
            "cash_difference_on_changed_queue_rows": changed_sum,
            "cash_difference_on_unchanged_queue_rows": unchanged_sum,
            "first_indexed_queue_difference": first_queue, "first_effective_queue_difference": first_effective,
            "first_cash_difference": first_cash, "rows": ledger})
    if seen != set(nominal_cases):
        raise ValueError("Physical and nominal case coverage differ")
    return {"schema": "titan.saved-model-contrast.v1", "complete": True,
        "input_sha256": nominal["input_sha256"], "observation_sha256": replay["observation_sha256"],
        "nominal_source_pins": nominal["source_pins"], "physical_source_pins": physical["validation"]["source_pins"],
        "cases": output, "engine_calls": 0, "actor_calls": 0, "new_games": 0,
        "scope": "exact cash bookkeeping over saved conditional trajectories; not causal per-order attribution"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("physical", "nominal", "normalizer", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    raw = args.normalizer.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != "24f8bd4cac2e88c609f309aa241eca8f3d1e05ee":
        raise ValueError("Use the original shared observation normalizer")
    spec = importlib.util.spec_from_file_location("rill_existing_normalizer", args.normalizer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    physical = json.loads(args.physical.read_text())
    nominal = json.loads(args.nominal.read_text())
    row = physical["validation"]["input_row"]
    result = compare_reports(physical, nominal, module.actor_input(row, row["seat"]))
    result["input_files"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in (("physical", args.physical), ("nominal", args.nominal))}
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"complete": result["complete"], "cases": [{k: v for k, v in c.items()
          if k not in ("rows", "first_indexed_queue_difference", "first_effective_queue_difference", "first_cash_difference")}
          for c in result["cases"]]}, indent=2))


if __name__ == "__main__":
    main()
