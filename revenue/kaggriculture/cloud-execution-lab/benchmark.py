"""Full-game finite-horizon SELL panel using the unmodified existing evaluator.

Passive official-interpreter hooks record observed-state traces and actual sale
receipts. Traces are analysis outputs, never agent runtime inputs.
"""
from __future__ import annotations

import argparse
import collections
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
DEVELOPMENT_SEEDS = {9600803, 9600821, 9600839}
HELDOUT_SEEDS = {9600901, 9600919}


def load_evaluator():
    spec = importlib.util.spec_from_file_location("existing_cloud_eval", HERE / "reference/evaluator/evaluate.py")
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    ev.LOADER = HERE / "reference/evaluator/loader.py"
    base_actor = ev.Actor

    class TimedActor(base_actor):
        def _measure(self, message):
            if message.get("kind") == "action" and "first_call_seconds" not in self.stats:
                self.stats["first_call_seconds"] = message["call_seconds"]
            return super()._measure(message)

        def report(self):
            result = super().report()
            result["cold_start_plus_first_call_seconds"] = (result.get("startup_seconds", 0)
                                                            + result.get("first_call_seconds", 0))
            result["measured_episode_agent_seconds"] = (result.get("startup_seconds", 0)
                                                        + sum(self.stats["rpc_seconds"]))
            result["max_action_including_cold_seconds"] = max(
                result["max_call_seconds"], result["cold_start_plus_first_call_seconds"])
            result["under_one_second_including_cold"] = result["max_action_including_cold_seconds"] < 1.0
            return result

    ev.Actor = TimedActor
    return ev


def run_game(ev, engine, runtime, variant, opponent, seed, seat, trace_path, game_timeout=120):
    original_interpreter, original_commit = engine.interpreter, engine._commit_unit
    original_drop = engine._drop_inventories_to_shed
    farm_ids, private_ids, record = {}, {}, {}
    totals = [{"units": collections.Counter(), "receipts": collections.Counter(),
               "eod_spill_units": collections.Counter()} for _ in range(2)]
    final = {}

    def commit(op, item, price, farm, private, *a, **kw):
        result = original_commit(op, item, price, farm, private, *a, **kw)
        if result:
            player = farm_ids[id(farm)]
            key = op + ":" + item
            totals[player]["units"][key] += 1
            totals[player]["receipts"][key] += price
            entry = record["transactions"].setdefault(f"{player}:{key}",
                    {"seat": player, "op": op, "item": item, "units": 0, "cash": 0, "unit_prices": []})
            entry["units"] += 1
            entry["cash"] += price
            entry["unit_prices"].append(price)
        return result

    def drop(private, capacity):
        before = collections.Counter(private["shed"])
        for inv in private["inventories"]:
            before.update(inv)
        result = original_drop(private, capacity)
        after = collections.Counter(private["shed"])
        for inv in private["inventories"]:
            after.update(inv)
        spill = before - after
        player = private_ids[id(private)]
        totals[player]["eod_spill_units"].update(spill)
        if spill:
            record.setdefault("eod_spills", []).append({"seat": player, "lost": dict(spill)})
        return result

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(trace_path, "wt", encoding="utf-8") as trace:
        def interpreter(state, env):
            live = bool(state[0].observation.get("farms"))
            if live:
                farm_ids.update({id(f): i for i, f in enumerate(state[0].observation.farms)})
                private_ids.update({id(s.observation.private): i for i, s in enumerate(state)})
                record.clear()
                record.update(step=state[0].observation.get("step", 0),
                              candidate_seat=seat,
                              observation=copy.deepcopy(state[seat].observation),
                              actions=[copy.deepcopy(s.action) for s in state],
                              transactions={})
            result = original_interpreter(state, env)
            if live:
                record["transactions"] = list(record["transactions"].values())
                record["post_cash"] = [f["money"] for f in state[0].observation.farms]
                record["post_shed"] = copy.deepcopy(state[seat].observation.private["shed"])
                record["post_market"] = copy.deepcopy(state[0].observation.market)
                record["done"] = all(s.status == "DONE" for s in state)
                trace.write(json.dumps(record, separators=(",", ":")) + "\n")
                if record["done"]:
                    final.update(last_decision=record["step"], own_shed=record["post_shed"],
                                 own_inventory=copy.deepcopy(state[seat].observation.private["inventories"]))
            return result

        engine.interpreter, engine._commit_unit, engine._drop_inventories_to_shed = interpreter, commit, drop
        candidate = str((runtime / (variant + "-adapter.py")).resolve())
        rival = str((runtime / (opponent + "-adapter.py")).resolve())
        pair = [candidate, rival] if seat == 0 else [rival, candidate]
        try:
            game = ev.play(engine, pair, HERE / "reference/engine", ev.LOADER, seed, seat,
                           action_timeout=1.0, startup_timeout=1.0, game_timeout=game_timeout)
        finally:
            engine.interpreter, engine._commit_unit, engine._drop_inventories_to_shed = original_interpreter, original_commit, original_drop
    game.update(variant=variant, opponent=opponent, diagnostics=totals, terminal=final,
                observation_trace=str(trace_path.resolve()), observation_trace_sha256=ev.sha256(trace_path))
    if game["status"] == "complete":
        own, rival = game["scores"][seat], game["scores"][1-seat]
        game.update(own_final_cash=own, rival_final_cash=rival,
                    outcome="W" if own > rival else "L" if own < rival else "T")
    else:
        game["outcome"] = "FAILED"
    return game


def summarize(games):
    result = {}
    for variant in sorted({g["variant"] for g in games}):
        subset = [g for g in games if g["variant"] == variant]
        outcomes = collections.Counter(g["outcome"] for g in subset)
        result[variant] = {"W": outcomes["W"], "T": outcomes["T"], "L": outcomes["L"],
                           "failed": outcomes["FAILED"], "games": len(subset),
                           "max_action_including_cold_seconds": max(
                               (g["actors"][g["candidate_seat"]]["max_action_including_cold_seconds"]
                                for g in subset if len(g.get("actors", [])) == 2), default=0)}
    baseline = {(g["seed"], g["opponent"], g["candidate_seat"]): g for g in games if g["variant"] == "baseline"}
    flips = []
    for g in games:
        b = baseline.get((g["seed"], g["opponent"], g["candidate_seat"]))
        if g["variant"] != "baseline" and b and b["status"] == g["status"] == "complete":
            flips.append({"variant": g["variant"], "seed": g["seed"], "opponent": g["opponent"],
                          "seat": g["candidate_seat"], "baseline": b["outcome"], "candidate": g["outcome"],
                          "flipped": b["outcome"] != g["outcome"],
                          "own_cash_delta": g["own_final_cash"] - b["own_final_cash"],
                          "rival_cash_delta": g["rival_final_cash"] - b["rival_final_cash"]})
    return {"W_T_L_first": result, "paired_outcomes": flips}


def audit_parent_preservation(ev, trace_path):
    """Replay observed states through an independent intact parent, after play."""
    parent = ev.import_file(HERE / "reference/next-panel/vendor/arlene.py",
                            "passive_parent_preservation")
    report = {"method": "Post-game replay of the candidate's observation sequence through a fresh unchanged Arlene instance; excluded from episode timing and never a runtime input. Nonempty non-SELL orders must preserve both values and original market-order indices; empty no-op slots are ignored.",
              "checked_actions": 0, "unit_mismatches": 0, "non_sell_order_mismatches": 0,
              "non_sell_index_mismatches": 0,
              "examples": []}
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            expected = parent.agent(copy.deepcopy(record["observation"]))
            actual = record["actions"][record["candidate_seat"]]
            units_equal = (actual.get("farmer") == expected.get("farmer")
                           and actual.get("hands") == expected.get("hands"))
            def non_sells(action):
                return [(index, order) for index, order in enumerate(action.get("market", []))
                        if order and not (isinstance(order, list) and order[0] == "SELL")]
            actual_non_sells, expected_non_sells = non_sells(actual), non_sells(expected)
            orders_equal = [order for _, order in actual_non_sells] == [order for _, order in expected_non_sells]
            indices_equal = [index for index, _ in actual_non_sells] == [index for index, _ in expected_non_sells]
            report["checked_actions"] += 1
            report["unit_mismatches"] += not units_equal
            report["non_sell_order_mismatches"] += not orders_equal
            report["non_sell_index_mismatches"] += not indices_equal
            if (not units_equal or not orders_equal or not indices_equal) and len(report["examples"]) < 8:
                report["examples"].append({"step": record["step"], "actual": actual,
                                           "parent_on_same_observation": expected,
                                           "actual_non_sell_positions": actual_non_sells,
                                           "expected_non_sell_positions": expected_non_sells})
    report["passed"] = report["unit_mismatches"] == report["non_sell_order_mismatches"] == report["non_sell_index_mismatches"] == 0
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=HERE / "runtime")
    parser.add_argument("--variants", default="baseline,candidate,naive")
    parser.add_argument("--opponents", default="arlene,apex")
    parser.add_argument("--seeds", default="9600803,9600821,9600839")
    parser.add_argument("--seats", default="0,1")
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--game-timeout", type=float, default=120)
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    seeds, seats = list(map(int, args.seeds.split(","))), list(map(int, args.seats.split(",")))
    if not set(seeds) <= DEVELOPMENT_SEEDS | HELDOUT_SEEDS:
        raise ValueError("Seeds must be from this assignment's named panel")
    if set(seeds) & HELDOUT_SEEDS and args.freeze_manifest is None:
        raise ValueError("Held-out panel requires the recorded pre-run source freeze")
    if not set(seats) <= {0, 1}:
        raise ValueError("Seats must be 0 or1")
    ev = load_evaluator()
    freeze = json.loads(args.freeze_manifest.read_text()) if args.freeze_manifest else None
    if freeze is not None:
        frozen_files = freeze.get("files")
        if not isinstance(frozen_files, dict) or not frozen_files:
            raise ValueError("Source freeze needs a nonempty files mapping of relative paths to SHA256")
        for filename, detail in frozen_files.items():
            expected = detail["sha256"] if isinstance(detail, dict) else detail
            path = HERE / filename
            if ev.sha256(path) != expected:
                raise ValueError(f"Frozen source changed before evaluation: {filename}")
    engine, hashes = ev.get_engine(HERE / "reference/engine", ev.LOADER)
    output = args.output.resolve()
    report = {"engine_reference": ev.ENGINE_REF, "engine_sha256": hashes,
              "evaluator_sha256": ev.sha256(ev.__file__), "benchmark_sha256": ev.sha256(__file__),
              "runtime_manifest": json.loads((args.runtime / "manifest.json").read_text()),
              "method": "Unmodified existing process-isolated evaluator and official pinned interpreter; passive receipt/spill/trace hooks. Full720-state configuration, 719actions, last decision718. Local-test W/T/L, not leaderboard rating.",
              "limits": {"action_rpc_seconds": 1, "startup_seconds": 1, "game_wall_seconds_including_cold": args.game_timeout,
                         "overage_seconds": 0, "first_action": "Source loading and policy initialization occur in first timed action; process startup also measured and added to strict cold maximum."},
              "freeze": freeze,
              "games": []}
    for seed in seeds:
        for opponent in args.opponents.split(","):
            for seat in seats:
                for variant in args.variants.split(","):
                    trace = output.parent / (output.stem + "-traces") / f"{variant}-{opponent}-{seed}-seat{seat}.jsonl.gz"
                    game = run_game(ev, engine, args.runtime, variant, opponent, seed, seat, trace, args.game_timeout)
                    if variant != "baseline" and game["status"] == "complete":
                        game["parent_preservation"] = audit_parent_preservation(ev, trace)
                    report["games"].append(game)
                    report["summary"] = summarize(report["games"])
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(report, indent=2) + "\n")
                    print(json.dumps({k: game.get(k) for k in ("variant", "opponent", "seed", "candidate_seat", "outcome", "own_final_cash", "rival_final_cash", "wall_seconds", "failure")}), flush=True)
                    if args.stop_on_failure and game["status"] != "complete":
                        raise SystemExit(1)
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
