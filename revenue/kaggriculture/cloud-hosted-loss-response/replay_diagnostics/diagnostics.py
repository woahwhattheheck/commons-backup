"""Observable loss diagnostics; compose ROWAN's reconciled official-engine trace.

No competitor program is loaded. scan_noop_harvests uses only the supplied
player observation and authoritative base action. The separate counterfactual
uses recorded simultaneous opponent actions for OFFLINE evaluation only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRACE_PATH = ROOT / "cloud-frontier-trace/analyze.py"
SCHEMA_VERSION = 1


def load_trace_module(path: Path = TRACE_PATH):
    spec = importlib.util.spec_from_file_location("t13_rowan_trace", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load existing trace: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seat(seat: int) -> int:
    if isinstance(seat, bool) or not isinstance(seat, int) or seat not in (0, 1):
        raise ValueError("own_seat must be 0 or 1")
    return seat


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Cash and threshold values must be finite numbers")
    return value


def _inventory(private: dict) -> Counter:
    result = Counter(private["shed"])
    for inv in private["inventories"]:
        result.update(inv)
    return result


def _difference(before: dict, after: dict) -> dict:
    return {k: after.get(k, 0) - before.get(k, 0)
            for k in sorted(set(before) | set(after)) if after.get(k, 0) != before.get(k, 0)}


def _snapshot_differences(left: dict, right: dict, fields: tuple) -> dict:
    # A missing product and an explicitly recorded zero are equal quantities.
    return {f: [left[f], right[f]] for f in fields
            if (Counter(left[f]) != Counter(right[f]) if f == "held_yield"
                else left[f] != right[f])}


def _effects(row: dict, own: int) -> dict:
    if row["audit"]["status"] != "RECONCILED":
        return {"status": row["audit"]["status"], "cash_by_cause": None}
    sums = [Counter(), Counter()]
    for event in row["audit"]["events"]:
        if "cash_delta" not in event:
            continue
        key = event["kind"]
        if key == "trade":
            key += ":" + event["op"] + ":" + event["item"]
        sums[event["seat"]][key] += event["cash_delta"]
    return {"status": "RECONCILED", "cash_by_cause": [dict(c) for c in sums],
            "own_minus_rival_by_cause": _difference(sums[1-own], sums[own]),
            "cash_residual": row.get("cash_residual")}


def summarize_trace(trace: dict, own_seat: int, *, material_cash: float = 100,
                    top_n: int = 8) -> dict:
    """Reduce an existing trace into first differences and attributable cash shocks.

    A first difference is descriptive, NOT a causal explanation of the final loss.
    Mismatched transitions never supply inferred execution or zero residuals.
    """
    own = _seat(own_seat)
    threshold = _number(material_cash)
    if threshold <= 0 or not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError("material_cash and top_n must be positive")
    if len(trace.get("terminal", [])) != 2 or len(trace.get("opening", [])) != 2:
        raise ValueError("Expected two-player opening and terminal snapshots")
    start = [_number(f["cash"]) for f in trace["opening"]]
    end = [_number(f["cash"]) for f in trace["terminal"]]
    first = {key: None for key in ("cash_gap", "material_deficit", "action", "portfolio", "held_yield", "production_event")}
    adverse = []
    cash = start[:]
    opening_margin = cash[own] - cash[1-own]
    if opening_margin:
        first["cash_gap"] = {"action_step": None, "phase": "opening", "margin": opening_margin}
    if opening_margin <= -threshold:
        first["material_deficit"] = {"action_step": None, "phase": "opening", "margin": opening_margin}
    for key, fields in (("portfolio", ("animals", "crops", "land", "hands")), ("held_yield", ("held_yield",))):
        diffs = _snapshot_differences(trace["opening"][0], trace["opening"][1], fields)
        if diffs:
            first[key] = {"frame": 0, "action_step": None, "phase": "opening",
                          "differences_by_seat": copy.deepcopy(diffs)}
    status_counts = Counter()
    for row in trace["transitions"]:
        step = row["action_step"]
        changes = [_number(v) for v in row["observed_cash_delta"]]
        if len(changes) != 2:
            raise ValueError("Expected two observed cash deltas")
        cash = [cash[s] + changes[s] for s in (0, 1)]
        margin = cash[own] - cash[1-own]
        delta = changes[own] - changes[1-own]
        status_counts[row["audit"]["status"]] += 1
        snapshot = {"frame": row["frame"], "action_step": step, "margin": margin,
                    "margin_delta": delta, "cash": cash[:], "actions": copy.deepcopy(row["actions"]),
                    "effects": _effects(row, own)}
        if first["cash_gap"] is None and margin != 0:
            first["cash_gap"] = snapshot
        if first["material_deficit"] is None and margin <= -threshold:
            first["material_deficit"] = snapshot
        if first["action"] is None and row["actions"][own] != row["actions"][1-own]:
            first["action"] = {"frame": row["frame"], "action_step": step, "actions": copy.deepcopy(row["actions"])}
        farms = row["farms_after"]
        for key, fields in (("portfolio", ("animals", "crops", "land", "hands")), ("held_yield", ("held_yield",))):
            diffs = _snapshot_differences(farms[0], farms[1], fields)
            if diffs and first[key] is None:
                first[key] = {"frame": row["frame"], "action_step": step, "differences_by_seat": copy.deepcopy(diffs)}
        if first["production_event"] is None and row["audit"]["status"] == "RECONCILED":
            added = [Counter(), Counter()]
            for e in row["audit"]["events"]:
                if e["kind"].startswith("_daily_refresh"):
                    added[e["seat"]].update({p: n for p, n in e["yield_delta"].items() if n > 0})
            if added[0] != added[1]:
                first["production_event"] = {"frame": row["frame"], "action_step": step,
                    "added_held_yield_by_seat": [dict(c) for c in added]}
        if delta < 0:
            adverse.append(snapshot)
    residual = [end[s] - cash[s] for s in (0, 1)]
    return {"schema_version": SCHEMA_VERSION, "own_seat": own,
            "episode_id_from_replay": trace.get("episode_id"), "source": trace.get("source", {}),
            "engine_ref": trace["engine_ref"], "action_alignment": trace["action_alignment"],
            "terminal_cash_by_seat": end, "terminal_margin": end[own] - end[1-own],
            "material_cash_threshold": threshold, "first_observed_differences": first,
            "largest_adverse_cash_transitions": sorted(adverse, key=lambda r: (r["margin_delta"], r["action_step"]))[:top_n],
            "transition_statuses": dict(status_counts), "observed_cash_telescope_residual": residual,
            "verified_transition_totals": trace["verified_transition_totals"],
            "limitations": ["First differences and local cash shocks do not establish a cause of the terminal loss.",
                "Only RECONCILED rows supply executed-effect attribution; other rows retain observed deltas only.",
                "Recorded opponent actions/private inventories are offline evidence, never runtime inputs.",
                "Added held yield is not unconstrained production or a realized future sale.",
                *trace.get("limitations", [])]}


def _owned_phase(obs: dict, action: dict, engine, cfg: dict):
    """Use the official unit primitive in official order, including atomic PLANT."""
    own = _seat(obs["player"])
    farm, private = copy.deepcopy(obs["farms"][own]), copy.deepcopy(obs["private"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []  # Same normalization as the official interpreter.
    units = [action.get("farmer", ["PASS"]), *hands]
    demand = Counter(a[1] for a in units if isinstance(a, list) and len(a) > 1 and a[0] == "PLANT")
    blocked = {crop for crop, n in demand.items() if n > private.get("seeds", {}).get(crop, 0)}
    records = []
    turns = max(1, int(cfg.get("turnsPerDay", 24)))
    size = int(cfg.get("boardSize", len(farm["tiles"])))
    for index, requested in enumerate(units):
        old_f, old_p = copy.deepcopy(farm), copy.deepcopy(private)
        effective = ["PASS"] if isinstance(requested, list) and len(requested) > 1 and requested[0] == "PLANT" and requested[1] in blocked else requested
        engine._apply_unit_action(farm, private, index, effective, size, int(obs["step"]) // turns, turns, int(cfg.get("shedCapacity", 100)))
        records.append({"worker": index, "requested": copy.deepcopy(requested),
                        "effective": copy.deepcopy(effective), "changed": (old_f, old_p) != (farm, private)})
    return farm, private, records


def scan_noop_harvests(observation: dict, base_action: dict, engine, configuration: dict | None = None) -> list[dict]:
    """Return same-position HARVEST alternatives to actual inert unit actions.

    Requires no rival data, price prediction, route tape or future state. It
    evaluates every candidate from the SAME authoritative base action, not a
    chain of optimistic individual harvests. Caller retains policy selection.
    """
    cfg = configuration or {}
    baseline_farm, baseline_private, records = _owned_phase(observation, base_action, engine, cfg)
    baseline_inventory = _inventory(baseline_private)
    alternatives = []
    for record in records:
        index = record["worker"]
        if record["changed"] or record["effective"] != record["requested"]:
            continue  # Do not replace requests cancelled by joint seed validation.
        alternative = copy.deepcopy(base_action)
        if index == 0:
            alternative["farmer"] = ["HARVEST"]
        else:
            alternative["hands"][index-1] = ["HARVEST"]
        farm, private, _ = _owned_phase(observation, alternative, engine, cfg)
        gains = _difference(baseline_inventory, _inventory(private))
        if not gains or min(gains.values()) < 0 or max(gains.values()) <= 0:
            continue
        if (farm["farmer"], farm["hands"], private["seeds"]) != (baseline_farm["farmer"], baseline_farm["hands"], baseline_private["seeds"]):
            continue
        alternatives.append({"worker": index, "replaced": record["requested"], "action": alternative,
            "additional_inventory_after_all_units": gains,
            "preserved": ["all worker positions", "market order indices", "seed consumption", "all other unit requests"],
            "status": "OWNED_UNIT_PHASE_FEASIBLE_NOT_POLICY_PROMOTION",
            "limitation": "Market funding, later harvest displacement, shed overflow, care and full-game value still require evaluation."})
    return alternatives


def counterfactual_transition(replay: dict, frame_index: int, own_seat: int, replacement: dict,
                              engine, ev, trace_module=None) -> dict:
    """One exact recorded co-action comparison; NEVER a rerun of a hidden seed."""
    own = _seat(own_seat)
    tm = trace_module or load_trace_module()
    if not 1 <= frame_index < len(replay["steps"]):
        raise ValueError("frame_index must identify a transition, not the opening")
    before = tm.observations(replay["steps"][frame_index-1])
    after = tm.observations(replay["steps"][frame_index])
    actions = [r.get("action") or {} for r in tm.frame_rows(replay["steps"][frame_index])]
    cfg = {k: v.get("default") if isinstance(v, dict) else v for k, v in engine.specification["configuration"].items()}
    cfg.update(replay.get("configuration", {}))
    step = before[0].get("step", frame_index-1)
    audit = tm.audit_transition(engine, ev, before, after, actions, cfg, step, replay.get("info", {}))
    if audit["status"] != "RECONCILED":
        return {"status": "BASELINE_" + audit["status"], "frame": frame_index, "audit": audit}
    alternative = copy.deepcopy(actions)
    alternative[own] = copy.deepcopy(replacement)
    shared = ev.structify(copy.deepcopy(before[0]))
    state = []
    for seat, obs in enumerate(before):
        visible = ev.structify(copy.deepcopy(obs))
        visible.farms, visible.market, visible.town = shared.farms, shared.market, shared.town
        visible.step = step
        state.append(ev.Struct(observation=visible, action=alternative[seat], status="ACTIVE", reward=0))
    # This is offline reconstruction only. Unknown boundary draws are not claimed.
    env = ev.Struct(configuration=ev.structify(cfg), done=False, info=copy.deepcopy(replay.get("info", {})))
    engine.interpreter(state, env)
    cash = [f["money"] for f in shared.farms]
    observed_cash = [f["money"] for f in after[0]["farms"]]
    deltas = [cash[s]-observed_cash[s] for s in (0, 1)]
    return {"status": "RECORDED_COACTION_COUNTERFACTUAL", "frame": frame_index, "action_step": step,
            "own_seat": own, "baseline_reconciled": True, "baseline_actions": actions,
            "alternative_actions": alternative, "cash_delta_vs_observed_by_seat": deltas,
            "relative_cash_delta": deltas[own]-deltas[1-own],
            "own_inventory_delta": _difference(tm.contents(after[own]["private"]), tm.contents(state[own].observation.private)),
            "own_held_yield_delta": _difference(tm.farm_snapshot(after[0]["farms"][own])["held_yield"], tm.farm_snapshot(shared.farms[own])["held_yield"]),
            "excluded_random_boundary_fields": audit["excluded_random_boundary_fields"],
            "limitation": "One observed opponent co-action, not a runtime opponent forecast or a full-game/hosted improvement."}


def analyze_file(path: Path, engine_dir: Path, *, own_seat: int, episode_id: int,
                 our_submission_id: int | None = None, expected_cash: tuple | None = None,
                 material_cash: float = 100, max_witnesses: int = 16) -> tuple[dict, list]:
    tm = load_trace_module()
    replay, source = tm.load_replay(path)
    embedded_id = replay.get("info", {}).get("EpisodeId")
    if embedded_id is not None and str(embedded_id) != str(episode_id):
        raise ValueError("Requested episode does not match replay EpisodeId")
    _seat(own_seat)
    if isinstance(episode_id, bool) or not isinstance(episode_id, int) or episode_id < 1:
        raise ValueError("episode_id must be a positive integer")
    if isinstance(max_witnesses, bool) or not isinstance(max_witnesses, int) or max_witnesses < 0:
        raise ValueError("max_witnesses must be a nonnegative integer")
    if expected_cash is not None:
        if len(expected_cash) != 2:
            raise ValueError("expected_cash must contain own,rival")
        for cash in expected_cash:
            _number(cash)
    ev = tm.evaluator()
    engine, hashes = ev.get_engine(engine_dir)
    source.update(engine_sha256=hashes, trace_sha256=hashlib.sha256(TRACE_PATH.read_bytes()).hexdigest(),
                  diagnostics_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    trace = tm.analyze(replay, engine, ev, source)
    terminal = [f["cash"] for f in trace["terminal"]]
    if expected_cash is not None and tuple(terminal[s] for s in (own_seat, 1-own_seat)) != tuple(expected_cash):
        raise ValueError("Provider seat/cash binding differs from replay terminal cash")
    result = summarize_trace(trace, own_seat, material_cash=material_cash)
    result["binding"] = {"requested_episode_id": episode_id, "embedded_episode_id": embedded_id,
        "own_seat": own_seat, "our_submission_id_from_provider_record": our_submission_id,
        "terminal_cash_checked": expected_cash is not None,
        "basis": "caller-supplied provider record; embedded EpisodeId and terminal cash checked when present; no submission identity inferred from cash alone"}
    witnesses = []
    alternatives_found = 0
    cfg = trace["configuration"]
    for index in range(1, len(replay["steps"])):
        before = tm.observations(replay["steps"][index-1])
        if "private" not in before[own_seat]:
            continue
        rows = tm.frame_rows(replay["steps"][index])
        action = rows[own_seat].get("action") or {}
        alternatives = scan_noop_harvests(before[own_seat], action, engine, cfg)
        alternatives_found += len(alternatives)
        for option in alternatives:
            if len(witnesses) >= max_witnesses:
                break
            cf = counterfactual_transition(replay, index, own_seat, option["action"], engine, ev, tm)
            witnesses.append({"frame": index, "candidate": option, "counterfactual": cf,
                              "before": replay["steps"][index-1], "after": replay["steps"][index]})
    result["noop_harvest_scan"] = {"alternatives_found": alternatives_found,
        "retained_witnesses": len(witnesses), "retention": "first chronological alternatives, bounded; not a ranking of full-game value",
        "cases": [{"frame": w["frame"], "candidate": w["candidate"], "counterfactual": w["counterfactual"]} for w in witnesses]}
    return result, witnesses


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("replay", type=Path)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument(
        "--own-seat", type=int, choices=(0, 1),
        required=True,
    )
    p.add_argument("--episode-id", type=int, required=True)
    p.add_argument("--our-submission-id", type=int)
    p.add_argument("--expected-cash", help="own,rival terminal cash from the provider record")
    p.add_argument("--material-cash", type=float, default=100)
    p.add_argument("--max-witnesses", type=int, default=16)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        expected = None if args.expected_cash is None else tuple(float(v) for v in args.expected_cash.split(","))
        report, witnesses = analyze_file(args.replay, args.engine_dir, own_seat=args.own_seat,
            episode_id=args.episode_id, our_submission_id=args.our_submission_id, expected_cash=expected,
            material_cash=args.material_cash, max_witnesses=args.max_witnesses)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        p.exit(2, f"Replay diagnostics failed: {exc}\n")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "diagnostics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "witnesses.json.gz").write_bytes(gzip.compress(json.dumps(witnesses, sort_keys=True, allow_nan=False).encode("utf-8"), mtime=0))
    print(json.dumps({k: report[k] for k in ("binding", "terminal_margin", "transition_statuses", "observed_cash_telescope_residual")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
