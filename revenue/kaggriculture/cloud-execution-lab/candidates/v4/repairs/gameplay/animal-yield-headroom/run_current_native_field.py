#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current-native natural-engagement gate for TITAN V4 ANIMAL-HEADROOM.

Execution/measurement only. The current native runtime remains byte-identical.
The ON arm applies the already-merged default-OFF helper only to the returned
action card before the official interpreter executes it.
"""
from __future__ import annotations

import argparse
from collections import Counter
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

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[2]
SALE_DIR = V4 / "research" / "sale-window-engagement"
if str(SALE_DIR) not in sys.path:
    sys.path.insert(0, str(SALE_DIR))
import sale_window as sw  # noqa: E402

HELPER_GIT_BLOB = "b371532dd0af54cb36768b07a39d5401f15df6f0"
CHALLENGER_SHA256 = "9fa42931d195553aecf78da33a2170b5bdc17cc6df714e06bc79e86e566ef201"
PRODUCTS = ("EGG", "MILK", "WOOL")
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"git_blob": git_blob(data), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_helper():
    path = HERE / "animal_headroom_harvest.py"
    if identity(path)["git_blob"] != HELPER_GIT_BLOB:
        raise RuntimeError("animal-headroom helper identity drift")
    return load_module("animal_headroom_field_helper", path)


def load_opponent(engine, name: str, challenger_path: Path | None) -> Callable[[Any, Any], dict]:
    if name == "starter":
        def starter(observation: Any, _configuration: Any) -> dict:
            return engine.starter_agent(observation)
        return starter
    if name != "orchard":
        raise ValueError(f"unsupported opponent: {name}")
    if challenger_path is None:
        raise ValueError("orchard requires --challenger")
    if hashlib.sha256(challenger_path.read_bytes()).hexdigest() != CHALLENGER_SHA256:
        raise RuntimeError("reactive challenger identity drift")
    challenger = load_module("animal_headroom_orchard", challenger_path)
    return challenger.agent


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def farm_for(observation: Any, seat: int) -> Any:
    return _get(observation, "farms")[seat]


def private_for(state: list[Any], seat: int) -> Any:
    return state[seat].observation.private


def product_total(state: list[Any], seat: int, product: str) -> int:
    private = private_for(state, seat)
    shed = _get(private, "shed", {})
    total = int(_get(shed, product, 0) or 0)
    inventories = _get(private, "inventories", [])
    for inv in inventories:
        total += int(_get(inv, product, 0) or 0)
    farm = farm_for(state[seat].observation, seat)
    for row in _get(farm, "tiles", []):
        for tile in row:
            if isinstance(tile, dict) and ANIMAL_PRODUCT.get(tile.get("animal")) == product:
                total += int(tile.get("yield_units", 0) or 0)
    return total


def tile_at_state(state: list[Any], seat: int, position: list[int]) -> Any:
    x, y = position
    farm = farm_for(state[seat].observation, seat)
    return _get(farm, "tiles")[y][x]


def shed_units(state: list[Any], seat: int, product: str) -> int:
    return int(_get(_get(private_for(state, seat), "shed", {}), product, 0) or 0)


def sell_rows(report: dict[str, Any], seat: int) -> list[dict[str, Any]]:
    out = []
    for row in report.get("rows", []):
        parsed = row.get("parsed")
        if row.get("seat") != seat or not isinstance(parsed, dict) or parsed.get("type") != "SELL":
            continue
        item = str(parsed.get("item"))
        out.append({
            "step": report["step"],
            "item": item,
            "sold": int(row.get("sold", 0)),
            "cash": int(row.get("sale_cash", 0)),
        })
    return out


def run_one(args: argparse.Namespace) -> dict[str, Any]:
    runtime = args.runtime.resolve()
    helper = load_helper()
    engine, Struct = sw.load_engine(runtime / "checks" / "reference")
    if not helper.verify_engine_source(runtime / "checks" / "reference" / "engine" / "kaggriculture.py"):
        raise RuntimeError("helper rejected official runtime engine")
    opponent = load_opponent(engine, args.opponent, args.challenger)

    sys.path.insert(0, str(runtime))
    native = load_module("animal_headroom_native_main", runtime / "main.py")

    state, env = sw.initialize(engine, Struct, args.seed)
    reason_counts: Counter[str] = Counter()
    species_day: Counter[str] = Counter()
    events: list[dict[str, Any]] = []
    sales: list[dict[str, Any]] = []
    eod_totals: dict[str, dict[str, int]] = {}
    statuses: Counter[str] = Counter()
    action_hash = hashlib.sha256()
    call_times: list[float] = []
    eligible_callbacks = 0
    planned_rewrites = 0
    actual_rewrites = 0
    recoverable_units = 0
    capacity_refusals = 0

    for step in range(env.configuration.episodeSteps):
        actions: list[dict[str, Any]] = []
        own_plan: dict[str, Any] | None = None
        own_before: dict[str, Any] | None = None

        for player in (0, 1):
            state[player].observation.step = step
            obs = copy.deepcopy(state[player].observation)
            if player == args.seat:
                started = time.perf_counter()
                authored = native.agent(obs, env.configuration)
                call_times.append(time.perf_counter() - started)
                if not isinstance(authored, dict):
                    raise AssertionError("native agent returned non-dict")
                instance = getattr(native, "_INSTANCE", None)
                diagnostics = getattr(instance, "diagnostics", {}) if instance is not None else {}
                statuses[str(diagnostics.get("status", "missing"))] += 1

                off_identity = helper.apply_animal_headroom_harvest(
                    authored, obs, env.configuration, enabled=False
                )
                if off_identity is not authored:
                    raise AssertionError("default-OFF helper lost object identity")

                own_plan = helper.plan_animal_headroom_harvest(authored, obs, env.configuration)
                reason = str(own_plan.get("reason"))
                reason_counts[reason] += 1
                capacity_refusals += int(reason == "eod_shed_capacity_not_certified")
                if own_plan.get("eligible") is True:
                    eligible_callbacks += 1
                    planned_rewrites += len(own_plan.get("rewrites", []))
                    recoverable_units += int(own_plan.get("saved_clipped_units", 0))
                    for row in own_plan.get("rewrites", []):
                        species_day[f"{row['animal']}:day{own_plan['day']}"] += 1
                    own_before = {
                        product: {
                            "total": product_total(state, args.seat, product),
                            "shed": shed_units(state, args.seat, product),
                        }
                        for product in PRODUCTS
                    }

                if args.arm == "on":
                    action = helper.apply_animal_headroom_harvest(
                        authored, obs, env.configuration, enabled=True
                    )
                else:
                    action = authored
                action = copy.deepcopy(action)
                if args.arm == "on" and own_plan.get("eligible") is True:
                    changed = 0
                    before_rows = [authored["farmer"], *authored["hands"]]
                    after_rows = [action["farmer"], *action["hands"]]
                    for before, after in zip(before_rows, after_rows):
                        changed += int(before != after)
                    if changed != len(own_plan["rewrites"]):
                        raise AssertionError("helper rewrite cardinality mismatch")
                    actual_rewrites += changed
            else:
                action = opponent(obs, env.configuration)
                if not isinstance(action, dict):
                    raise AssertionError("opponent returned non-dict")
                action = copy.deepcopy(action)
            actions.append(action)

        action_hash.update(
            json.dumps(actions[args.seat], sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
        report = sw.observed_step(engine, state, env, actions, step)
        sales.extend(sell_rows(report, args.seat))

        if step % int(env.configuration.turnsPerDay) == int(env.configuration.turnsPerDay) - 1:
            eod_totals[str(step)] = {product: product_total(state, args.seat, product) for product in PRODUCTS}

        if own_plan is not None and own_plan.get("eligible") is True:
            event = {
                "step": step,
                "day": int(own_plan["day"]),
                "arm": args.arm,
                "planned_rewrites": copy.deepcopy(own_plan["rewrites"]),
                "recoverable_clipped_units": int(own_plan["saved_clipped_units"]),
                "pre": own_before,
                "post": {
                    product: {
                        "total": product_total(state, args.seat, product),
                        "shed": shed_units(state, args.seat, product),
                    }
                    for product in PRODUCTS
                },
                "target_tiles_after_eod": [],
            }
            for row in own_plan["rewrites"]:
                tile = tile_at_state(state, args.seat, row["position"])
                event["target_tiles_after_eod"].append({
                    "animal": row["animal"],
                    "product": row["product"],
                    "position": row["position"],
                    "yield_units": int(_get(tile, "yield_units", 0) or 0) if isinstance(tile, dict) else None,
                })
            events.append(event)

        if all(s.status == "DONE" for s in state):
            break

    steps = step + 1
    if steps != 719 or not all(s.status == "DONE" for s in state):
        raise AssertionError(f"incomplete episode: steps={steps} status={[s.status for s in state]}")

    farms = state[0].observation.farms
    terminal_money = [int(_get(farm, "money", 0)) for farm in farms]
    own_money = terminal_money[args.seat]
    rival_money = terminal_money[1 - args.seat]

    for event in events:
        for target in event["target_tiles_after_eod"]:
            product = target["product"]
            later = [row for row in sales if row["item"] == product and row["step"] > event["step"]]
            target["later_actual_sell_units"] = sum(row["sold"] for row in later)
            target["later_actual_sell_cash"] = sum(row["cash"] for row in later)

    runtime_files = (
        "main.py", "titan_runtime.py", "TITAN-CONFIG.json", "scheduler.py",
        "frozen_selected.py", "early_capital.py",
    )
    runtime_ids = {name: identity(runtime / name) for name in runtime_files if (runtime / name).exists()}
    return {
        "schema": "titan.v4.animal-headroom-current-native-game/v1",
        "arm": args.arm,
        "seed": args.seed,
        "seat": args.seat,
        "opponent": args.opponent,
        "steps": steps,
        "terminal": True,
        "terminal_money": {"own": own_money, "rival": rival_money, "margin": own_money - rival_money},
        "rewards": [state[0].reward, state[1].reward],
        "eligible_callbacks": eligible_callbacks,
        "planned_rewrites": planned_rewrites,
        "actual_rewrites": actual_rewrites,
        "recoverable_clipped_units": recoverable_units,
        "eod_capacity_refusals": capacity_refusals,
        "reason_counts": dict(reason_counts),
        "species_day": dict(species_day),
        "events": events,
        "actual_sell_rows": sales,
        "eod_product_totals": eod_totals,
        "status_counts": dict(statuses),
        "fallback_callbacks": sum(v for k, v in statuses.items() if k != "completed"),
        "timing_seconds": {
            "max": max(call_times),
            "median": statistics.median(call_times),
            "total": sum(call_times),
        },
        "action_sha256": action_hash.hexdigest(),
        "state_sha256": sw.digest(state),
        "env_sha256": sw.digest(env),
        "runtime_identities": runtime_ids,
        "helper_identity": identity(HERE / "animal_headroom_harvest.py"),
    }


def parse_cases(value: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            opponent, seed_text = raw.rsplit(":", 1)
            seed = int(seed_text)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"bad case {raw!r}; expected opponent:seed") from error
        if opponent not in ("starter", "orchard"):
            raise argparse.ArgumentTypeError(f"unsupported opponent {opponent!r}")
        out.append((opponent, seed))
    if not out or len(set(out)) != len(out):
        raise argparse.ArgumentTypeError("cases must be nonempty and unique")
    return out


def sell_after(game: dict[str, Any], step: int, product: str) -> tuple[int, int]:
    rows = [r for r in game["actual_sell_rows"] if r["item"] == product and r["step"] > step]
    return sum(r["sold"] for r in rows), sum(r["cash"] for r in rows)


def compare_pair(off: dict[str, Any], on: dict[str, Any]) -> dict[str, Any]:
    if (off["seed"], off["seat"], off["opponent"]) != (on["seed"], on["seat"], on["opponent"]):
        raise AssertionError("pair mismatch")
    event_followthrough = []
    for event in on["events"]:
        for rewrite in event["planned_rewrites"]:
            product = rewrite["product"]
            step = int(event["step"])
            off_total = int(off["eod_product_totals"][str(step)][product])
            on_total = int(on["eod_product_totals"][str(step)][product])
            off_sell_units, off_sell_cash = sell_after(off, step, product)
            on_sell_units, on_sell_cash = sell_after(on, step, product)
            event_followthrough.append({
                "step": step,
                "day": event["day"],
                "animal": rewrite["animal"],
                "product": product,
                "position": rewrite["position"],
                "recoverable_clipped_units": rewrite["recoverable_clipped_units"],
                "paired_post_eod_total_product_delta": on_total - off_total,
                "later_actual_sell_units_off": off_sell_units,
                "later_actual_sell_units_on": on_sell_units,
                "later_actual_sell_units_delta": on_sell_units - off_sell_units,
                "later_actual_sell_cash_delta": on_sell_cash - off_sell_cash,
            })
    return {
        "seed": off["seed"],
        "seat": off["seat"],
        "opponent": off["opponent"],
        "off_money": off["terminal_money"],
        "on_money": on["terminal_money"],
        "delta_own_cash": on["terminal_money"]["own"] - off["terminal_money"]["own"],
        "delta_rival_cash": on["terminal_money"]["rival"] - off["terminal_money"]["rival"],
        "delta_margin": on["terminal_money"]["margin"] - off["terminal_money"]["margin"],
        "off_eligible_callbacks": off["eligible_callbacks"],
        "on_eligible_callbacks": on["eligible_callbacks"],
        "on_actual_rewrites": on["actual_rewrites"],
        "on_recoverable_clipped_units": on["recoverable_clipped_units"],
        "on_eod_capacity_refusals": on["eod_capacity_refusals"],
        "off_fallback_callbacks": off["fallback_callbacks"],
        "on_fallback_callbacks": on["fallback_callbacks"],
        "actions_changed": off["action_sha256"] != on["action_sha256"],
        "terminal_state_changed": off["state_sha256"] != on["state_sha256"],
        "event_followthrough": event_followthrough,
    }


def run_panel(args: argparse.Namespace) -> dict[str, Any]:
    cases = parse_cases(args.cases)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    parts = Path(tempfile.mkdtemp(prefix="animal-headroom-parts-", dir=output.parent))
    games = []
    comparisons = []

    for opponent, seed in cases:
        for seat in (0, 1):
            pair = []
            for arm in ("off", "on"):
                part = parts / f"{opponent}-seed{seed}-seat{seat}-{arm}.json"
                cmd = [
                    sys.executable, __file__, "--one",
                    "--runtime", str(args.runtime),
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
                        f"child failed {opponent} seed={seed} seat={seat} arm={arm}\n"
                        f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}"
                    )
                result = json.loads(part.read_text())
                games.append(result)
                pair.append(result)
                print(json.dumps({
                    "opponent": opponent, "seed": seed, "seat": seat, "arm": arm,
                    "eligible": result["eligible_callbacks"],
                    "rewrites": result["actual_rewrites"],
                    "recoverable": result["recoverable_clipped_units"],
                    "capacity_refusals": result["eod_capacity_refusals"],
                    "money": result["terminal_money"],
                }, sort_keys=True), flush=True)
            comparisons.append(compare_pair(pair[0], pair[1]))
            output.write_text(json.dumps({
                "status": "PARTIAL", "games": games, "comparisons": comparisons
            }, indent=2) + "\n")

    total_rewrites = sum(c["on_actual_rewrites"] for c in comparisons)
    engaged = [c for c in comparisons if c["on_actual_rewrites"] > 0]
    report = {
        "schema": "titan.v4.animal-headroom-current-native-panel/v1",
        "status": "COMPLETE",
        "disposition": "COLD" if total_rewrites == 0 else "ENGAGED_EVIDENCE_ONLY",
        "python": sys.version,
        "cases": [{"opponent": name, "seed": seed} for name, seed in cases],
        "runtime_root": str(args.runtime.resolve()),
        "runtime_identity": {
            "main.py": identity(args.runtime / "main.py"),
            "scheduler.py": identity(args.runtime / "scheduler.py"),
            "frozen_selected.py": identity(args.runtime / "frozen_selected.py"),
        },
        "helper_identity": identity(HERE / "animal_headroom_harvest.py"),
        "games": games,
        "comparisons": comparisons,
        "summary": {
            "pairs": len(comparisons),
            "pairs_engaged": len(engaged),
            "on_actual_rewrites": total_rewrites,
            "on_recoverable_clipped_units": sum(c["on_recoverable_clipped_units"] for c in comparisons),
            "on_eod_capacity_refusals": sum(c["on_eod_capacity_refusals"] for c in comparisons),
            "mean_margin_delta_engaged": (
                sum(c["delta_margin"] for c in engaged) / len(engaged) if engaged else None
            ),
            "positive_margin_engaged": sum(c["delta_margin"] > 0 for c in engaged),
            "negative_margin_engaged": sum(c["delta_margin"] < 0 for c in engaged),
            "zero_margin_engaged": sum(c["delta_margin"] == 0 for c in engaged),
            "fallback_callbacks_off": sum(c["off_fallback_callbacks"] for c in comparisons),
            "fallback_callbacks_on": sum(c["on_fallback_callbacks"] for c in comparisons),
        },
        "release_authorized": False,
        "limits": [
            "Execution/evidence only; no runtime/default/config/archive/Kaggle activation.",
            "A zero-rewrite panel is COLD and does not justify broadening admission.",
            "Later SELL deltas are paired downstream outcomes, not unit-level provenance.",
        ],
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one", action="store_true")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--arm", choices=("off", "on"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--seat", type=int, choices=(0, 1))
    parser.add_argument("--opponent", choices=("starter", "orchard"))
    parser.add_argument("--challenger", type=Path)
    parser.add_argument("--cases", default="starter:17,starter:9922999,orchard:17")
    parser.add_argument("--child-timeout", type=int, default=240)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.one:
        if args.arm is None or args.seed is None or args.seat is None or args.opponent is None:
            parser.error("--one requires --arm --seed --seat --opponent")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(run_one(args), indent=2) + "\n")
        return 0

    report = run_panel(args)
    print(json.dumps({"disposition": report["disposition"], **report["summary"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
