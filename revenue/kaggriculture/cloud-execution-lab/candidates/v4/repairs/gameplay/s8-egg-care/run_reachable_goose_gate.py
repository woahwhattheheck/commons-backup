# SPDX-License-Identifier: Apache-2.0
"""Offline legal-reachability field fixture. NOT native or hosted promotion.

Use only a trusted source adapter: --candidate PATH --candidate-sha256 SHA.
The adapter must expose apply_egg_care(obs, action, config, enabled=True).
It is imported only after authentication; no missing file is downloaded.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Any

from reachable_goose_setup import (
    SITES, parent_action, identity_control, care_positive_control,
    collect_ablation_control,
)

SOURCE_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
EVALUATOR_SHA256 = "e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c"
LOADER_SHA256 = "cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def authenticate(root: Path) -> dict:
    """Authenticate the complete 109-member native input before any import."""
    source = root / "SOURCE.json"
    if digest(source) != SOURCE_SHA256:
        raise ValueError("Checked-release SOURCE.json identity mismatch")
    manifest = json.loads(source.read_text(encoding="utf-8"))["runtime"]
    if len(manifest) != 109:
        raise ValueError("Unexpected checked-release runtime inventory")
    for name, identity in manifest.items():
        path = root / name
        if not path.is_file() or path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise ValueError(f"Checked-release runtime member mismatch: {name}")
    ev = root / "checks/reference/evaluator/evaluate.py"
    loader = root / "checks/reference/evaluator/loader.py"
    if digest(ev) != EVALUATOR_SHA256 or digest(loader) != LOADER_SHA256:
        raise ValueError("Untrusted evaluator/loader")
    return {"source_sha256": SOURCE_SHA256, "runtime_members_authenticated": 109,
            "engine_ref": ENGINE_REF, "evaluator_sha256": EVALUATOR_SHA256,
            "loader_sha256": LOADER_SHA256}


def get_engine(root: Path):
    identity = authenticate(root)
    ev = import_path(root / "checks/reference/evaluator/evaluate.py", "reachable_goose_evaluator")
    engine, hashes = ev.get_engine(root / "checks/reference/engine",
                                   root / "checks/reference/evaluator/loader.py", prepare=False)
    identity["engine_sha256"] = hashes
    return ev, engine, identity


def adapter_from_source(path: Path, expected_sha256: str) -> Callable:
    """Load caller-selected trusted standalone S8 source; a hash isn't a sandbox."""
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("Candidate SHA256 must be 64 lowercase hexadecimal digits")
    if digest(path) != expected_sha256:
        raise ValueError("Candidate source identity mismatch")
    module = import_path(path.resolve(), "reachable_goose_candidate")
    apply = getattr(module, "apply_egg_care", None)
    if not callable(apply):
        raise ValueError("Candidate lacks apply_egg_care")
    return lambda obs, action, cfg: apply(obs, action, cfg, enabled=True)


def tile_count(farm: dict) -> int:
    return sum(isinstance(t, dict) and t.get("animal") == "GOOSE"
               for row in farm["tiles"] for t in row)


def opportunity(obs: dict, action: dict) -> tuple[bool, str]:
    """Mechanical S8 opportunity BEFORE any public price threshold, not profit."""
    day, hour = divmod(obs["step"], 24)
    if hour != 23 or day > 27 or action["farmer"] != ["COLLECT_FERTILIZER"]:
        return False, "wrong_action_or_clock"
    farm = obs["farms"][obs["player"]]
    x, y = farm["farmer"]
    tile = farm["tiles"][y][x]
    if not isinstance(tile, dict) or tile.get("animal") != "GOOSE":
        return False, "no_goose"
    if not tile["fed_today"] or tile["cared_today"] or not tile["fertilizer_available"] or tile.get("pending_care_bonus", 0):
        return False, "service_state"
    if day < tile["placed_day"] + 2:
        return False, "immature"
    if tile["yield_units"] + int(day >= tile["placed_day"] + 3) + 2 > 4:
        return False, "held_capacity"
    return True, "eligible_before_price"


def validate_action(action: Any) -> None:
    if not isinstance(action, dict) or set(action) != {"farmer", "hands", "market"}:
        raise ValueError("Fixture adapter returned an invalid action schema")
    if not isinstance(action["farmer"], list) or not action["farmer"] or action["hands"] != [] or not isinstance(action["market"], list):
        raise ValueError("Fixture adapter returned invalid actor rows")
    if any(not isinstance(row, list) or len(row) != 3 or type(row[2]) is not int or row[2] <= 0 for row in action["market"]):
        raise ValueError("Fixture adapter returned invalid market rows")
    encoded(action)


def run_game(ev, engine, seed: int, seat: int, adapter: Callable = identity_control,
             *, label: str = "baseline", audit: bool = False, disposal: bool = False) -> dict:
    if type(seed) is not int or type(seat) is not int or seat not in (0, 1):
        raise ValueError("Invalid game coordinates")
    cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                     for k, v in engine.specification["configuration"].items()})
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    # resolve_episode_seed removes the private seed from the agent config.
    if cfg.seed is not None:
        raise ValueError("Environment leaked its private seed into candidate configuration")
    trace, action_trace = hashlib.sha256(), hashlib.sha256()
    counts = Counter()
    changed_rows, opportunity_rows, event_rows, audit_rows = [], [], [], []
    placements = []
    for step in range(719):
        for s in state:
            s.observation.step = step
            s.observation.remainingOverageTime = 0
        obs = json.loads(encoded(state[seat].observation))
        public_cfg = json.loads(encoded(cfg))
        parent = parent_action(obs, public_cfg, disposal=disposal)
        before_args = encoded([obs, parent, public_cfg])
        action = adapter(obs, parent, public_cfg)
        if encoded([obs, parent, public_cfg]) != before_args:
            raise ValueError("Candidate mutated observation, parent action, or configuration")
        validate_action(action)
        if action["hands"] != parent["hands"] or action["market"] != parent["market"]:
            raise ValueError("S8 fixture adapter changed hands or market rows")
        if action != parent:
            allowed = {(("COLLECT_FERTILIZER",), ("CARE",)),
                       (("PASS",), ("CARE",)), (("COLLECT_FERTILIZER",), ("PASS",))}
            if (tuple(parent["farmer"]), tuple(action["farmer"])) not in allowed:
                raise ValueError("S8 fixture adapter changed an unrelated unit action")
            changed_rows.append({"step": step, "parent": parent, "returned": copy.deepcopy(action),
                                 "shed_units": sum(obs["private"]["shed"].values()),
                                 "egg_price": obs["market"]["prices"]["EGG"],
                                 "fertilizer_price": obs["market"]["prices"]["FERTILIZER"]})
        eligible, reason = opportunity(obs, parent)
        if step % 24 == 23:
            counts["opportunity_" + reason] += 1
        if eligible:
            opportunity_rows.append({"step": step, "day": step // 24,
                                     "prices": copy.deepcopy(obs["market"]["prices"]),
                                     "shed_fertilizer": obs["private"]["shed"].get("FERTILIZER", 0),
                                     "shed_units": sum(obs["private"]["shed"].values())})
        farm_before = obs["farms"][seat]
        x, y = farm_before["farmer"]
        tile_before = farm_before["tiles"][y][x]
        inventory_before = obs["private"]["inventories"][0]
        total_before = {p: obs["private"]["shed"].get(p, 0) + sum(i.get(p, 0) for i in obs["private"]["inventories"])
                        for p in ("EGG", "FERTILIZER", "WHEAT", "GOOSE")}
        op = action["farmer"][0]
        state[seat].action = copy.deepcopy(action)
        state[1 - seat].action = engine.starter_agent(copy.deepcopy(state[1 - seat].observation))
        engine.interpreter(state, env)
        after = state[seat].observation
        farm_after = after.farms[seat]
        tile_after = farm_after["tiles"][y][x]
        total_after = {p: after.private["shed"].get(p, 0) + sum(i.get(p, 0) for i in after.private["inventories"])
                       for p in total_before}
        new_geese = tile_count(farm_after) - tile_count(farm_before)
        if new_geese:
            placements.append({"step": step, "delta": new_geese, "action": action["farmer"],
                               "carried_geese_before": inventory_before.get("GOOSE", 0),
                               "money": farm_after["money"]})
            counts["geese_placed"] += max(0, new_geese)
            counts["geese_lost"] += max(0, -new_geese)
        actual_egg_harvest = max(0, total_after["EGG"] - total_before["EGG"]) if op == "HARVEST" else 0
        counts["egg_harvested"] += actual_egg_harvest
        if op == "FEED":
            counts["wheat_consumed_by_feed"] += max(0, total_before["WHEAT"] - total_after["WHEAT"])
        if op == "COLLECT_FERTILIZER":
            counts["fertilizer_collected_and_retained"] += max(0, total_after["FERTILIZER"] - total_before["FERTILIZER"])
        if op == "CARE" and isinstance(tile_before, dict) and not tile_before.get("cared_today", True):
            if step % 24 != 23:
                counts["care_succeeded"] += int(isinstance(tile_after, dict) and tile_after.get("cared_today", False))
            else:
                counts["care_succeeded"] += int(isinstance(tile_after, dict) and tile_after.get("pending_care_bonus", 0) > tile_before.get("pending_care_bonus", 0))
        if step % 24 == 23:
            for sx, sy in SITES:
                old, new = farm_before["tiles"][sy][sx], farm_after["tiles"][sy][sx]
                if isinstance(old, dict) and isinstance(new, dict) and old.get("animal") == new.get("animal") == "GOOSE":
                    produced = max(0, new["yield_units"] - old["yield_units"])
                    counts["eggs_produced_to_tile"] += produced
                    # Only counts observed stock increments, never an unfilled request.
                    if produced or new.get("pending_care_bonus", 0):
                        event_rows.append({"step": step, "site": [sx, sy], "produced": produced,
                                           "yield_after": new["yield_units"],
                                           "pending_before": old.get("pending_care_bonus", 0),
                                           "pending_after": new.get("pending_care_bonus", 0),
                                           "fed_before": old["fed_today"], "cared_before": old["cared_today"]})
        if any(row[0] == "SELL" for row in action["market"]):
            for p in ("EGG", "FERTILIZER"):
                counts[p.lower() + "_sold_units"] += max(0, total_before[p] - total_after[p])
        counts["callbacks"] += 1
        counts["interpreter_transitions"] += 1
        action_trace.update(encoded([step, [s.action for s in state]]))
        trace.update(encoded([step, [s.action for s in state], [s.observation for s in state],
                              [s.status for s in state], [s.reward for s in state], dict(env)]))
        if audit:
            audit_rows.append({"step": step, "own_observation": obs, "action": action,
                               "after_own_observation": copy.deepcopy(dict(after))})
        if all(s.status == "DONE" for s in state):
            break
    if step != 718 or not all(s.status == "DONE" for s in state):
        raise ValueError("Incomplete official episode")
    scores = [int(s.reward) for s in state]
    result = {"seed": seed, "seat": seat, "label": label, "status": "complete",
              "fixture": "standard_cash_fullshed" if disposal else "ordinary",
              "scores": scores, "own": scores[seat], "rival": scores[1-seat],
              "margin": scores[seat] - scores[1-seat], "counts": dict(counts),
              "placements": placements, "changes": changed_rows,
              "opportunities_before_price": opportunity_rows, "production_events": event_rows,
              "action_trace_sha256": action_trace.hexdigest(), "world_trace_sha256": trace.hexdigest(),
              "final_own_shed": copy.deepcopy(state[seat].observation.private["shed"]),
              "final_goose_count": tile_count(state[seat].observation.farms[seat])}
    if audit:
        result["audit_rows"] = audit_rows
    return result


def pair_result(base: dict, candidate: dict) -> dict:
    if (base["seed"], base["seat"], base["fixture"]) != (candidate["seed"], candidate["seat"], candidate["fixture"]):
        raise ValueError("Mismatched paired coordinates")
    return {"seed": base["seed"], "seat": base["seat"], "arm": candidate["label"],
            "delta_own": candidate["own"] - base["own"],
            "delta_rival": candidate["rival"] - base["rival"],
            "delta_margin": candidate["margin"] - base["margin"],
            "changed_actions": len(candidate["changes"]),
            "delta_eggs_harvested": candidate["counts"].get("egg_harvested", 0) - base["counts"].get("egg_harvested", 0),
            "delta_fertilizer_retained": candidate["counts"].get("fertilizer_collected_and_retained", 0) - base["counts"].get("fertilizer_collected_and_retained", 0),
            "same_action_trace": candidate["action_trace_sha256"] == base["action_trace_sha256"],
            "same_world_trace": candidate["world_trace_sha256"] == base["world_trace_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[17, 101, 6607, 9922999])
    parser.add_argument("--fixture", choices=["ordinary", "standard_cash_fullshed"], default="ordinary")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.candidate) != bool(args.candidate_sha256):
        parser.error("--candidate and --candidate-sha256 must be supplied together")
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Duplicate seeds would duplicate cells")
    ev, engine, identity = get_engine(args.native_root.resolve())
    arms = [("identity_control", identity_control),
            ("care_positive_control_NOT_S8", care_positive_control),
            ("collect_ablation_control_NOT_S8", collect_ablation_control)]
    if args.candidate:
        arms.append(("candidate", adapter_from_source(args.candidate, args.candidate_sha256)))
    games, pairs = [], []
    for seed in args.seeds:
        for seat in (0, 1):
            base = run_game(ev, engine, seed, seat, disposal=args.fixture == "standard_cash_fullshed")
            games.append(base)
            for label, adapter in arms:
                if label == "candidate":
                    # A fresh module per episode prevents telemetry or future
                    # stateful adapters from carrying state between cells.
                    adapter = adapter_from_source(args.candidate, args.candidate_sha256)
                result = run_game(ev, engine, seed, seat, adapter, label=label, disposal=args.fixture == "standard_cash_fullshed")
                games.append(result)
                pairs.append(pair_result(base, result))
    payload = {"schema": "titan-v4-reachable-goose-gate/v1", "disposition": "FIXTURE_ONLY_NOT_PROMOTION",
               "input_identity": identity, "candidate_sha256": args.candidate_sha256,
               "fixture_source_sha256": digest(Path(__file__).with_name("reachable_goose_setup.py")),
               "runner_source_sha256": digest(Path(__file__)),
               "python_version": sys.version, "optimized": bool(sys.flags.optimize),
               "fixture": args.fixture,
               "configuration": "official defaults; engine seed hidden from agents",
               "opponent": "pinned_official_starter", "games": games, "pairs": pairs,
               "limits": ["Test grower, NOT native TITAN control or current composed V4.",
                          "Positive and ablation controls are NOT the S8 source candidate.",
                          "Direct interpreter, NOT hosted runtime/deadline proof.",
                          "Fixed setup and seeds, NOT held-out field EV or strength.",
                          "No production/default/archive/Kaggle change."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"games": len(games), "pairs": pairs, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"REACHABLE-GOOSE ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
