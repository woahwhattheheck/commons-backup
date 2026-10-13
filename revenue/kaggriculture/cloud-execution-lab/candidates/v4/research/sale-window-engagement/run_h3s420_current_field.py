#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current-native H3/S420 execution gate for the one composed TITAN V4.

This is an execution/measurement harness, not production wiring.  It runs each
arm/seat/opponent in a fresh process, records returned native actions and
H3/S420 diagnostics, then replays the exact captured action tape through the
source-pinned official interpreter so SELL fills/cash are measured from actual
commits rather than candidate estimates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

import sale_window as sw

CHALLENGER_SHA256 = "9fa42931d195553aecf78da33a2170b5bdc17cc6df714e06bc79e86e566ef201"
CHALLENGER_NAMES = ("orchard", "dairy", "poultry", "fiber", "roots")


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "git_blob": git_blob(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_opponent(engine, name: str, challenger_path: Path | None) -> Callable[[Any, Any], dict]:
    if name == "starter":
        return engine.starter_agent
    if name not in CHALLENGER_NAMES:
        raise ValueError(f"unknown opponent: {name}")
    if challenger_path is None:
        raise ValueError("challenger path required for non-starter opponent")
    data = challenger_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != CHALLENGER_SHA256:
        raise ValueError("reactive challenger source identity mismatch")
    challenger = load_module("h3s420_reactive_challenger", challenger_path)
    return challenger.agent if name == "orchard" else getattr(challenger, name)


def aggregate_sell_observer(replay: dict[str, Any], seat: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "authored_sell_rows": 0,
        "filled_sell_rows": 0,
        "filled_units": 0,
        "sale_cash": 0,
        "by_item": {},
    }
    by_item: dict[str, dict[str, int]] = defaultdict(lambda: {
        "authored_rows": 0, "filled_rows": 0, "filled_units": 0, "sale_cash": 0,
    })
    for turn in replay["reports"]:
        for row in turn["rows"]:
            if row["seat"] != seat:
                continue
            parsed = row.get("parsed")
            if not isinstance(parsed, dict) or parsed.get("type") != "SELL":
                continue
            item = str(parsed.get("item"))
            sold = int(row.get("sold", 0))
            cash = int(row.get("sale_cash", 0))
            result["authored_sell_rows"] += 1
            result["filled_sell_rows"] += int(sold > 0)
            result["filled_units"] += sold
            result["sale_cash"] += cash
            by_item[item]["authored_rows"] += 1
            by_item[item]["filled_rows"] += int(sold > 0)
            by_item[item]["filled_units"] += sold
            by_item[item]["sale_cash"] += cash
    result["by_item"] = dict(sorted(by_item.items()))
    return result


def run_one(args: argparse.Namespace) -> dict[str, Any]:
    runtime = args.runtime.resolve()
    reference = runtime / "checks" / "reference"
    engine, Struct = sw.load_engine(reference)
    opponent = load_opponent(engine, args.opponent, args.challenger)

    # Every child owns a fresh module graph and singleton.
    sys.path.insert(0, str(runtime))
    native = load_module("h3s420_native_main", runtime / "main.py")

    state, env = sw.initialize(engine, Struct, args.seed)
    initial_state, initial_env = copy.deepcopy((state, env))
    tape: list[list[dict]] = []
    statuses: Counter[str] = Counter()
    call_times: list[float] = []
    horizon_values: Counter[str] = Counter()
    h3_baselines: Counter[str] = Counter()
    h3_thresholds: Counter[str] = Counter()
    h3_observations = 0
    new_plan_suppressed = 0
    ah = hashlib.sha256()

    for step in range(env.configuration.episodeSteps):
        actions = []
        for player in (0, 1):
            state[player].observation.step = step
            obs = copy.deepcopy(state[player].observation)
            if player == args.seat:
                started = time.perf_counter()
                action = native.agent(obs, env.configuration)
                call_times.append(time.perf_counter() - started)
                instance = getattr(native, "_INSTANCE", None)
                diagnostics = getattr(instance, "diagnostics", {}) if instance is not None else {}
                statuses[str(diagnostics.get("status", "missing"))] += 1
                consumer = getattr(instance, "consumer", None)
                consumer_diag = getattr(consumer, "diagnostics", {}) if consumer is not None else {}
                if isinstance(consumer_diag, dict):
                    if "horizon" in consumer_diag:
                        horizon_values[str(consumer_diag.get("horizon"))] += 1
                    h3 = consumer_diag.get("h3s420")
                    if isinstance(h3, dict):
                        h3_observations += 1
                        h3_baselines[str(h3.get("baseline_horizon"))] += 1
                        h3_thresholds[str(h3.get("suppress_new_plans_after"))] += 1
                        new_plan_suppressed += int(bool(h3.get("new_plan_suppressed")))
            else:
                action = opponent(obs, env.configuration)
            if not isinstance(action, dict):
                raise AssertionError("native/opponent returned non-dict action")
            action = copy.deepcopy(action)
            actions.append(action)
            state[player].action = copy.deepcopy(action)
        own_action = actions[args.seat]
        ah.update(encoded(own_action) + b"\n")
        tape.append(actions)
        engine.interpreter(state, env)
        if all(s.status == "DONE" for s in state):
            break

    if len(tape) != 719 or not all(s.status == "DONE" for s in state):
        raise AssertionError(f"incomplete episode: steps={len(tape)} statuses={[s.status for s in state]}")

    native_state_sha = sw.digest(state)
    native_env_sha = sw.digest(env)
    native_tape_sha = sw.digest(tape)
    native_rewards = [s.reward for s in state]

    replay = sw.replay(engine, initial_state, initial_env, tape, 0)
    if not replay["terminal"]:
        raise AssertionError("captured native tape does not replay to terminal")
    for field, expected in (
        ("state_sha256", native_state_sha),
        ("env_sha256", native_env_sha),
        ("tape_sha256", native_tape_sha),
    ):
        if replay[field] != expected:
            raise AssertionError(f"observer replay mismatch: {field}")
    if replay["rewards"] != native_rewards:
        raise AssertionError("observer replay reward mismatch")

    own = native_rewards[args.seat]
    rival = native_rewards[1 - args.seat]
    fills = aggregate_sell_observer(replay, args.seat)
    final_money = replay["reports"][-1]["money"]
    runtime_ids = {name: identity(runtime / name) for name in (
        "main.py", "titan_runtime.py", "TITAN-CONFIG.json",
        "scheduler.py", "frozen_selected.py", "early_capital.py",
    )}
    for optional in ("projection_clone.py", "scoped_method_cache.py"):
        path = runtime / optional
        if path.exists():
            runtime_ids[optional] = identity(path)

    return {
        "schema": "titan.v4.h3s420-current-field-game/v1",
        "arm": args.arm,
        "seed": args.seed,
        "seat": args.seat,
        "opponent": args.opponent,
        "steps": len(tape),
        "terminal": True,
        "score": own,
        "rival": rival,
        "margin": own - rival,
        "final_money": {"own": final_money[args.seat], "rival": final_money[1 - args.seat]},
        "status_counts": dict(statuses),
        "fallback_callbacks": sum(v for k, v in statuses.items() if k != "completed"),
        "timing_seconds": {
            "max": max(call_times),
            "median": statistics.median(call_times),
            "total": sum(call_times),
        },
        "diagnostics": {
            "horizon_values": dict(horizon_values),
            "h3s420_observations": h3_observations,
            "baseline_horizon_values": dict(h3_baselines),
            "suppression_threshold_values": dict(h3_thresholds),
            "new_plan_suppressed_callbacks": new_plan_suppressed,
        },
        "sell_observer": fills,
        "action_sha256": ah.hexdigest(),
        "state_sha256": native_state_sha,
        "env_sha256": native_env_sha,
        "tape_sha256": native_tape_sha,
        "observer_replay_exact": True,
        "runtime_identities": runtime_ids,
    }


def parse_cases(value: str) -> list[tuple[str, int]]:
    out = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            opponent, seed_text = raw.rsplit(":", 1)
            seed = int(seed_text)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"bad case {raw!r}; expected opponent:seed") from error
        if opponent != "starter" and opponent not in CHALLENGER_NAMES:
            raise argparse.ArgumentTypeError(f"unknown opponent in case {raw!r}")
        out.append((opponent, seed))
    if not out:
        raise argparse.ArgumentTypeError("at least one opponent:seed case required")
    if len(set(out)) != len(out):
        raise argparse.ArgumentTypeError("duplicate opponent:seed cases")
    return out


def compare_pair(off: dict[str, Any], on: dict[str, Any]) -> dict[str, Any]:
    if (off["seed"], off["seat"], off["opponent"]) != (on["seed"], on["seat"], on["opponent"]):
        raise AssertionError("comparison pair mismatch")
    return {
        "seed": off["seed"],
        "seat": off["seat"],
        "opponent": off["opponent"],
        "delta_own": on["score"] - off["score"],
        "delta_rival": on["rival"] - off["rival"],
        "delta_margin": on["margin"] - off["margin"],
        "actions_changed": on["action_sha256"] != off["action_sha256"],
        "terminal_state_changed": on["state_sha256"] != off["state_sha256"],
        "sell_fill_units_delta": on["sell_observer"]["filled_units"] - off["sell_observer"]["filled_units"],
        "sell_cash_delta": on["sell_observer"]["sale_cash"] - off["sell_observer"]["sale_cash"],
        "off_fallback_callbacks": off["fallback_callbacks"],
        "on_fallback_callbacks": on["fallback_callbacks"],
        "on_h3s420_observations": on["diagnostics"]["h3s420_observations"],
        "on_new_plan_suppressed_callbacks": on["diagnostics"]["new_plan_suppressed_callbacks"],
    }


def run_panel(args: argparse.Namespace) -> dict[str, Any]:
    cases = parse_cases(args.cases)
    if any(name != "starter" for name, _ in cases):
        if args.challenger is None:
            raise ValueError("challenger source required by panel")
        if hashlib.sha256(args.challenger.read_bytes()).hexdigest() != CHALLENGER_SHA256:
            raise ValueError("challenger source identity mismatch")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    parts = Path(tempfile.mkdtemp(prefix="h3s420-field-parts-", dir=output.parent))
    games: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []

    for opponent, seed in cases:
        for seat in (0, 1):
            pair = []
            for arm, runtime in (("off", args.off_runtime), ("on", args.on_runtime)):
                part = parts / f"{opponent}-seed{seed}-seat{seat}-{arm}.json"
                cmd = [
                    sys.executable,
                    __file__,
                    "--one",
                    "--runtime", str(runtime),
                    "--arm", arm,
                    "--seed", str(seed),
                    "--seat", str(seat),
                    "--opponent", opponent,
                    "--output", str(part),
                ]
                if args.challenger is not None:
                    cmd += ["--challenger", str(args.challenger)]
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=args.child_timeout)
                if done.returncode:
                    raise RuntimeError(
                        f"child failed arm={arm} opponent={opponent} seed={seed} seat={seat}\n"
                        f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}"
                    )
                result = json.loads(part.read_text())
                games.append(result)
                pair.append(result)
                print(json.dumps({
                    "arm": arm,
                    "opponent": opponent,
                    "seed": seed,
                    "seat": seat,
                    "score": result["score"],
                    "rival": result["rival"],
                    "margin": result["margin"],
                    "fills": result["sell_observer"]["filled_units"],
                    "sale_cash": result["sell_observer"]["sale_cash"],
                    "fallback_callbacks": result["fallback_callbacks"],
                    "suppressed": result["diagnostics"]["new_plan_suppressed_callbacks"],
                }, sort_keys=True), flush=True)
            comparisons.append(compare_pair(pair[0], pair[1]))
            output.write_text(json.dumps({
                "status": "PARTIAL",
                "parts_directory": str(parts),
                "games": games,
                "comparisons": comparisons,
            }, indent=2) + "\n")

    report = {
        "schema": "titan.v4.h3s420-current-field/v1",
        "status": "COMPLETE",
        "python": sys.version,
        "cases": [{"opponent": name, "seed": seed} for name, seed in cases],
        "parts_directory": str(parts),
        "off_runtime": {
            "scheduler": identity(args.off_runtime / "scheduler.py"),
            "frozen_selected": identity(args.off_runtime / "frozen_selected.py"),
        },
        "on_runtime": {
            "scheduler": identity(args.on_runtime / "scheduler.py"),
            "frozen_selected": identity(args.on_runtime / "frozen_selected.py"),
        },
        "games": games,
        "comparisons": comparisons,
        "summary": {
            "pairs": len(comparisons),
            "positive_margin_pairs": sum(c["delta_margin"] > 0 for c in comparisons),
            "negative_margin_pairs": sum(c["delta_margin"] < 0 for c in comparisons),
            "zero_margin_pairs": sum(c["delta_margin"] == 0 for c in comparisons),
            "mean_margin_delta": sum(c["delta_margin"] for c in comparisons) / len(comparisons),
            "engaged_action_pairs": sum(c["actions_changed"] for c in comparisons),
            "pairs_with_sell_cash_delta": sum(c["sell_cash_delta"] != 0 for c in comparisons),
            "off_fallback_callbacks": sum(c["off_fallback_callbacks"] for c in comparisons),
            "on_fallback_callbacks": sum(c["on_fallback_callbacks"] for c in comparisons),
            "on_h3s420_observations": sum(c["on_h3s420_observations"] for c in comparisons),
            "on_new_plan_suppressed_callbacks": sum(c["on_new_plan_suppressed_callbacks"] for c in comparisons),
        },
        "release_authorized": False,
        "limits": [
            "Execution gate only; no production/default/archive/Kaggle activation.",
            "The reactive challenger is one synthetic soft family, not a leaderboard opponent.",
            "Promotion requires interpreting this receipt in the canonical V4 evidence/admission process.",
        ],
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--arm", choices=("off", "on"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--seat", type=int, choices=(0, 1))
    parser.add_argument("--opponent", choices=("starter",) + CHALLENGER_NAMES)
    parser.add_argument("--off-runtime", type=Path)
    parser.add_argument("--on-runtime", type=Path)
    parser.add_argument("--challenger", type=Path)
    parser.add_argument("--cases", default="starter:17,starter:9922999,orchard:17")
    parser.add_argument("--child-timeout", type=int, default=240)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.one:
        required = (args.runtime, args.arm, args.seed, args.seat, args.opponent)
        if any(value is None for value in required):
            parser.error("--one requires --runtime --arm --seed --seat --opponent")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(run_one(args), indent=2) + "\n")
        return 0

    if args.off_runtime is None or args.on_runtime is None:
        parser.error("panel mode requires --off-runtime and --on-runtime")
    report = run_panel(args)
    print(json.dumps({"status": report["status"], **report["summary"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
