"""Serial native capture + fixed-tape sale-clock intervention audit.

This is not an adaptive candidate evaluation or the unrecovered sellby15 policy.
Run each seat in a fresh process; no package source or feature flags are changed.
"""
import argparse
import base64
import copy
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import zlib

import sale_window as sw

MANIFEST_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
PRODUCTS = ("MILK", "WOOL", "STRAWBERRY", "MELON")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def authenticate(root, manifest):
    data = Path(manifest).read_bytes()
    require(hashlib.sha256(data).hexdigest() == MANIFEST_SHA256, "manifest identity mismatch")
    files = json.loads(data)["runtime"]
    require(len(files) == 109, "unexpected runtime manifest size")
    for name, record in files.items():
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()), "unsafe manifest path")
        b = path.read_bytes()
        require(len(b) == record["bytes"] and hashlib.sha256(b).hexdigest() == record["sha256"],
                "runtime source mismatch: " + name)
    return {"runtime_members_verified": len(files), "manifest_sha256": MANIFEST_SHA256,
            "archive_identity": ARCHIVE_SHA256,
            "native_main_sha256": hashlib.sha256((root / "main.py").read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256((root / "TITAN-CONFIG.json").read_bytes()).hexdigest()}


def capture(engine, Struct, root, seed, seat):
    sys.path.insert(0, str(root.resolve()))
    spec = importlib.util.spec_from_file_location("harvestclock_native", root / "main.py")
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    state, env = sw.initialize(engine, Struct, seed)
    initial = copy.deepcopy((state, env))
    tape, statuses, times = [], Counter(), []
    for step in range(env.configuration.episodeSteps):
        acts = []
        for player in (0, 1):
            state[player].observation.step = step
            obs = copy.deepcopy(state[player].observation)
            if player == seat:
                started = time.perf_counter()
                a = native.agent(obs, env.configuration)
                times.append(time.perf_counter() - started)
                statuses[getattr(native._INSTANCE, "diagnostics", {}).get("status", "unavailable")] += 1
            else:
                # The source starter uses unseeded Random internally. Record its
                # actual outputs, then replay precisely this tape; do not claim
                # the seed alone determines future captures of the opponent.
                a = engine.starter_agent(obs)
            require(isinstance(a, dict), "non-dict action")
            acts.append(copy.deepcopy(a))
            state[player].action = copy.deepcopy(a)
        tape.append(acts)
        engine.interpreter(state, env)
        if all(s.status == "DONE" for s in state):
            break
    require(all(s.status == "DONE" for s in state) and len(tape) == 719, "incomplete native episode")
    return initial, tape, {"seed": seed, "seat": seat, "steps": len(tape),
                          "money": [s.reward for s in state], "statuses": dict(statuses),
                          "native_call_seconds": times, "state_sha256": sw.digest(state),
                          "env_sha256": sw.digest(env), "tape_sha256": sw.digest(tape)}


def summarize(arm):
    return {k: v for k, v in arm.items() if k != "reports"}


def timing_witness(result, seat, source, source_row, target, target_row):
    def record(arm, step, row):
        turn = next(t for t in result[arm]["reports"] if t["step"] == step)
        found = next((r for r in turn["rows"] if r["seat"] == seat and r["row"] == row), None)
        return {"row": copy.deepcopy(found), "market_entry_shed": turn["market_entry_shed"][seat]}
    before = record("baseline", source, source_row)
    after = record("candidate", target, target_row)
    source_units = before["row"]["sold"] if before["row"] else 0
    target_units = after["row"]["sold"] if after["row"] else 0
    classification = ("SUPPRESSED_SALE_NOT_RETIMED" if not target_units else
                      "REALIZED_RETIMING" if source_units == target_units else "PARTIAL_OR_CHANGED_FILL")
    return {"classification": classification, "source_filled_units": source_units,
            "destination_filled_units": target_units, "baseline_source": before,
            "candidate_destination": after}


def audit(engine, initial, tape, seat):
    state, env = initial
    baseline = sw.replay(engine, state, env, tape, 0)
    cap = max(1, int(env.configuration.maxMarketOrdersPerTurn))
    census = Counter()
    first = {}
    for turn in baseline["reports"]:
        for row in turn["rows"]:
            if row["seat"] != seat:
                continue
            parsed = row["parsed"]
            if not parsed or parsed.get("type") != "SELL":
                continue
            item = parsed["item"]
            census["exposed_sell_rows"] += 1
            census["filled_sell_rows"] += int(row["sold"] > 0)
            census["filled_units"] += row["sold"]
            # Predeclared independent residual panel: first ACTUALLY FILLED row
            # per product on days 14..16 inclusive. No outcome-based selection.
            if item in PRODUCTS and 14 * 24 <= turn["step"] < 17 * 24 and row["sold"]:
                first.setdefault(item, (turn["step"], row["row"]))
    outcomes = []
    for item in PRODUCTS:
        if item not in first:
            outcomes.append({"item": item, "status": "NO_FILLED_SOURCE_IN_WINDOW"})
            continue
        source, row = first[item]
        for offset in (-1, 1):
            target = source + offset
            market = tape[target][seat].get("market", [])
            target_row = next((i for i, value in enumerate(market[:cap]) if value == ["PASS"]), len(market))
            if target_row >= cap:
                outcomes.append({"item": item, "source": source, "offset": offset,
                                 "status": "NO_FREE_EXPOSED_DESTINATION"})
                continue
            moved = sw.shift_sale(tape, seat, source, row, target, target_row)
            result = sw.compare(engine, state, env, tape, moved, 0, seat)
            result["timing_witness"] = timing_witness(result, seat, source, row, target, target_row)
            result["baseline"] = summarize(result["baseline"])
            result["candidate"] = summarize(result["candidate"])
            result.update(item=item, source=source, source_row=row, target=target,
                          target_row=target_row, offset=offset, status="EXECUTED_OPEN_LOOP")
            outcomes.append(result)
    return baseline, dict(census), outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--seat", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    provenance = authenticate(args.native, args.manifest)
    engine, Struct = sw.load_engine(args.reference)
    initial, tape, native = capture(engine, Struct, args.native, args.seed, args.seat)
    baseline, census, outcomes = audit(engine, initial, tape, args.seat)
    for field in ("state_sha256", "env_sha256", "tape_sha256"):
        require(baseline[field] == native[field], "instrumented replay changes native endpoint: " + field)
    require(baseline["money"] == native["money"], "native reward replay mismatch")
    payload = json.dumps(tape, sort_keys=True, separators=(",", ":")).encode()
    report = {"schema": "titan.sale-window-native-audit.v1", "provenance": provenance,
              "source_pins": sw.PINS, "native": native, "census": census,
              "baseline": summarize(baseline), "observer_replay_exact": True,
              "open_loop_interventions": outcomes,
              "trace": {"encoding": "base64(zlib(UTF-8 JSON))",
                        "data": base64.b64encode(zlib.compress(payload, 9)).decode(),
                        "uncompressed_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
              "limits": ["Historical r04_sellby15 donor and -$86 gate are not recovered or tested.",
                         "Native capture is pinned b567, not latest composed V4.",
                         "Counterfactuals replay fixed future actions, not adaptive agents.",
                         "Seed17/both seats/starter is not a held-out competitive gate.",
                         "Starter RNG and native wall-clock budgets can change newly captured tapes.",
                         "No default, production, archive, workflow, or Kaggle change."]}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"seat": args.seat, "steps": native["steps"], "statuses": native["statuses"],
                      "money": native["money"], "census": census,
                      "outcomes": [{k: x.get(k) for k in ("item", "offset", "status", "terminal_margin_delta")}
                                   for x in outcomes]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
