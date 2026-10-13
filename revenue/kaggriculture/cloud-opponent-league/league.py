#!/usr/bin/env python3
"""T09 cloud league: freeze source, run fixed panels, retain paired loss traces.

Runtime is an explicit, already-prepared offline source pack. No downloads,
submissions, candidate search, credential access or provider calls occur here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
from collections import deque
from typing import Any

from variants import actor_class

HERE = Path(__file__).resolve().parent
PANELS = {"development": [9790001, 9790019], "evaluation": [9790101, 9790119]}
OPPONENTS = ["arlene", "apex", "arlene/sale_cadence", "apex/crop_demand",
             "arlene/labor_cadence"]
ARMS = ["control", "cap", "carrot"]
SCHEMA = "commons-opponent-league-v1"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="wb", delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(canonical(value)); f.flush(); os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)


def inside(root: Path, relative: str) -> Path:
    """Resolve manifest members, not arbitrary runtime commands."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"runtime member is not a file under the pack: {relative}")
    return path


def runtime_inventory(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def freeze(runtime: Path, destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError("freeze already exists; preserve it and use a new operation")
    if destination.resolve().is_relative_to(runtime.resolve()):
        raise ValueError("freeze must be outside the runtime")
    assets = json.loads((runtime / "assets.json").read_text())
    required = {"control", "cap", "carrot", "apex", "engine", "schema", "utils",
                "evaluator", "loader"}
    if set(assets.get("paths", {})) != required:
        raise ValueError(f"assets.paths must contain exactly {sorted(required)}")
    for path in assets["paths"].values():
        inside(runtime, path)
    # Disjoint seed lists are part of the source freeze, never selected by score.
    seeds = [s for panel in PANELS.values() for s in panel]
    if len(seeds) != len(set(seeds)):
        raise ValueError("development/evaluation seeds overlap")
    doc = {"schema": SCHEMA, "panels": PANELS, "opponents": OPPONENTS,
           "arms": ARMS, "seats": [0, 1], "assets": assets,
           "runtime_files": runtime_inventory(runtime),
           "runner_files": {p.name: sha(p) for p in
                            (HERE / "league.py", HERE / "variants.py")},
           "criteria": {"primary": "win/tie/loss and paired outcome flips",
                        "secondary": "own cash and own-minus-rival margin",
                        "selection": "no policy or opponent selection in this runner",
                        "loss_trace": "candidate loss OR own-cash/margin regression vs control"}}
    doc["freeze_sha256"] = hashlib.sha256(canonical(doc)).hexdigest()
    atomic_json(destination, doc)
    return doc


def verify(runtime: Path, frozen: dict) -> None:
    content = {k: v for k, v in frozen.items() if k != "freeze_sha256"}
    if hashlib.sha256(canonical(content)).hexdigest() != frozen["freeze_sha256"]:
        raise ValueError("freeze document digest mismatch")
    if frozen.get("schema") != SCHEMA:
        raise ValueError("unknown freeze schema")
    for name, digest in frozen["runner_files"].items():
        if sha(HERE / name) != digest:
            raise ValueError(f"runner changed since freeze: {name}")
    if runtime_inventory(runtime) != frozen["runtime_files"]:
        raise ValueError("runtime changed since freeze (including added/deleted files)")


def outcome(own: float, rival: float) -> str:
    return "win" if own > rival else "loss" if own < rival else "tie"


def stratify(rows: list[dict]) -> dict:
    """Match exact pairs; missing/duplicate arms are errors, never silent wins."""
    if not rows:
        raise ValueError("cannot rank an empty panel")
    for row in rows:
        if not row.get("valid"):
            raise ValueError("cannot rank invalid games")
        if row.get("outcome") not in ("win", "tie", "loss"):
            raise ValueError("invalid outcome")
        if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k])
                   for k in ("own_cash", "margin")):
            raise ValueError("nonfinite or missing economic metric")
    groups: dict[tuple, dict] = {}
    for r in rows:
        key = (r["seed"], r["seat"], r["opponent"])
        if r["arm"] in groups.setdefault(key, {}):
            raise ValueError(f"duplicate game: {key}/{r['arm']}")
        groups[key][r["arm"]] = r
    for key, arms in groups.items():
        if set(arms) != set(ARMS):
            raise ValueError(f"incomplete paired game: {key}")
    def summary(selected: list[dict]) -> dict:
        result = {}
        for arm in ARMS:
            rs = [r for r in selected if r["arm"] == arm]
            pairs = [(groups[(r["seed"], r["seat"], r["opponent"])]["control"], r)
                     for r in rs]
            cash = [r["own_cash"] - c["own_cash"] for c, r in pairs]
            margin = [r["margin"] - c["margin"] for c, r in pairs]
            flips = {}
            for c, r in pairs:
                k = c["outcome"] + "->" + r["outcome"]
                flips[k] = flips.get(k, 0) + 1
            result[arm] = {"games": len(rs),
                           "wtl": {o: sum(r["outcome"] == o for r in rs)
                                   for o in ("win", "tie", "loss")},
                           "paired_flips": flips,
                           "mean_own_cash": statistics.mean(r["own_cash"] for r in rs) if rs else None,
                           "mean_margin": statistics.mean(r["margin"] for r in rs) if rs else None,
                           "mean_paired_cash_delta": statistics.mean(cash) if cash else None,
                           "mean_paired_margin_delta": statistics.mean(margin) if margin else None,
                           "worst_paired_cash_delta": min(cash, default=None),
                           "worst_paired_margin_delta": min(margin, default=None)}
        return result
    overall = summary(rows)
    rank = sorted(ARMS, key=lambda a: (-(overall[a]["wtl"]["win"] +
                                       0.5 * overall[a]["wtl"]["tie"]),
                                     -(overall[a]["mean_margin"] or 0), a))
    return {"overall": overall, "ranking": rank,
            "by_seed": {str(s): summary([r for r in rows if r["seed"] == s])
                        for s in sorted({r["seed"] for r in rows})},
            "by_seat": {str(s): summary([r for r in rows if r["seat"] == s])
                        for s in sorted({r["seat"] for r in rows})},
            "by_opponent": {o: summary([r for r in rows if r["opponent"] == o])
                            for o in sorted({r["opponent"] for r in rows})}}


class TraceEngine:
    """Daily and final-eight-turn economy traces; observations are not changed."""
    def __init__(self, engine, seat):
        self.engine, self.seat = engine, seat
        self.specification = engine.specification
        self.daily = []
        self.tail = deque(maxlen=8)
        self.turn = 0

    def interpreter(self, state, env):
        observation = state[self.seat].observation
        if "farms" in observation:
            item = {"step": self.turn, "day": observation.get("day"),
                    "hour": observation.get("hour"),
                    "own_cash": observation["farms"][self.seat].get("money"),
                    "rival_cash": observation["farms"][1-self.seat].get("money"),
                    "shed": copy.deepcopy(observation.get("private", {}).get("shed", {})),
                    "inventories": copy.deepcopy(observation.get("private", {}).get("inventories", [])),
                    "market": copy.deepcopy(observation.get("market", {})),
                    "town": copy.deepcopy(observation.get("town", {})),
                    "candidate_action": copy.deepcopy(state[self.seat].action),
                    "rival_action_after_selection": copy.deepcopy(state[1-self.seat].action)}
            if self.turn % 24 == 0:
                self.daily.append(item)
            self.tail.append(item)
            self.turn += 1
        return self.engine.interpreter(state, env)

    @property
    def trace(self):
        seen = {r["step"] for r in self.daily}
        return sorted(self.daily + [r for r in self.tail if r["step"] not in seen],
                      key=lambda row: row["step"])


def run_game(runtime: Path, frozen: dict, evaluator, engine, seed: int,
             seat: int, opponent: str, arm: str) -> tuple[dict, list]:
    paths = frozen["assets"]["paths"]
    def spec(name: str) -> str:
        return str(inside(runtime, paths[name]))
    parent, _, variant = opponent.partition("/")
    rival = spec("control" if parent == "arlene" else "apex")
    if variant:
        rival += "|league=" + variant
    traced = TraceEngine(engine, seat)
    agents = [None, None]
    agents[seat] = spec(arm)
    agents[1-seat] = rival
    result = evaluator.play(traced, agents, inside(runtime, paths["engine"]).parent,
                            inside(runtime, paths["loader"]), seed, seat)
    valid = result["status"] == "complete"
    # The official engine zeroes both reward scores on a tie. Use its saved
    # bank snapshot for economic metrics, while outcomes use terminal rewards.
    banks = result.get("bank_snapshot", {}).get("bank", [])
    own, rival_cash = (map(float, (banks[seat], banks[1-seat]))
                       if valid else (None, None))
    if valid and not all(math.isfinite(x) for x in (own, rival_cash)):
        raise ValueError("non-finite final cash")
    actors = result.get("actors", [])
    row = {"seed": seed, "seat": seat, "opponent": opponent, "arm": arm,
           "own_cash": own, "rival_cash": rival_cash,
           "margin": own-rival_cash if valid else None,
           "outcome": outcome(result["scores"][seat], result["scores"][1-seat]) if valid else None,
           "rounds": result["steps"], "status": result["status"],
           "failure": result["failure"], "elapsed_seconds": result["wall_seconds"],
           "opponent_changed_turns": actors[1-seat].get("league_changed_turns", 0)
                                     if len(actors) == 2 else None,
           "bank_snapshot": result["bank_snapshot"], "actor_resources": actors,
           "engine_trace_sha256": result["trace_sha256"], "valid": valid}
    return row, traced.trace


def run(runtime: Path, frozen: dict, panel: str, output: Path) -> dict:
    verify(runtime, frozen)
    if output.exists():
        raise FileExistsError("output exists; do not overwrite or silently rerun a held panel")
    if output.resolve().is_relative_to(runtime.resolve()):
        raise ValueError("output must be outside the frozen runtime")
    output.mkdir(parents=True)
    assets = frozen["assets"]["paths"]
    evaluator = load_module(inside(runtime, assets["evaluator"]), "league_evaluator")
    engine, _ = evaluator.get_engine(inside(runtime, assets["engine"]).parent,
                                     loader=inside(runtime, assets["loader"]))
    evaluator.Actor = actor_class(evaluator.Actor, engine.SHOPS)
    rows: list[dict] = []
    doc = {"schema": SCHEMA, "freeze_sha256": frozen["freeze_sha256"],
           "panel": panel, "complete": False, "rows": rows,
           "trace_visibility": "candidate-observation-only; post-action replay", "invalid_games": []}
    atomic_json(output / "results.json", doc)
    for seed in frozen["panels"][panel]:
        for seat in frozen["seats"]:
            for opponent in frozen["opponents"]:
                control = None
                for arm in frozen["arms"]:
                    row, trace = run_game(runtime, frozen, evaluator, engine,
                                          seed, seat, opponent, arm)
                    rows.append(row)
                    if arm == "control":
                        control = row
                    row["paired_cash_delta"] = row["own_cash"]-control["own_cash"] if row["valid"] and control["valid"] else None
                    row["paired_margin_delta"] = row["margin"]-control["margin"] if row["valid"] and control["valid"] else None
                    if (row["outcome"] == "loss" or (row["paired_cash_delta"] is not None and row["paired_cash_delta"] < 0) or
                            (row["paired_margin_delta"] is not None and row["paired_margin_delta"] < 0) or not row["valid"]):
                        name = f"{seed}-{seat}-{opponent.replace('/', '_')}-{arm}.json"
                        atomic_json(output / "loss-traces" / name,
                                    {"freeze_sha256": frozen["freeze_sha256"],
                                     "game": row, "trace": trace})
                        row["loss_trace"] = "loss-traces/"+name
                    if not row["valid"]:
                        doc["invalid_games"].append({k: row[k] for k in
                                                     ("seed", "seat", "opponent", "arm", "failure", "status")})
                    atomic_json(output / "results.json", doc)
                    print(json.dumps({k: row[k] for k in ("seed", "seat", "opponent", "arm", "outcome", "margin", "valid")}), flush=True)
    verify(runtime, frozen)
    doc["complete"] = True
    # An invalid policy run is not ranked as an economic loss or improvement.
    doc["summary"] = stratify(rows) if not doc["invalid_games"] else None
    atomic_json(output / "results.json", doc)
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--runtime", type=Path, required=True)
    f.add_argument("--output", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--freeze", type=Path, required=True)
    r.add_argument("--panel", choices=PANELS, required=True)
    r.add_argument("--runtime", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps(freeze(args.runtime.resolve(), args.output), indent=2))
    else:
        result = run(args.runtime.resolve(), json.loads(args.freeze.read_text()),
                     args.panel, args.output)
        return 0 if not result["invalid_games"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
