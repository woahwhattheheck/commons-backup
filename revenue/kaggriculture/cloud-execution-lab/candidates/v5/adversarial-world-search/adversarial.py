#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TITAN V5 F50: search deterministic worlds for candidate regressions.

This tool reuses the authenticated Commons evaluator/reference-policy harness. It
never changes candidate bytes, CURRENT/default/release pointers, or Kaggle state.
It searches exact seed/seat cells, fails closed on custody/runtime anomalies, and
emits one minimal first-divergence witness per distinct regression signature.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

EXPECTED_CANDIDATE_SHA256 = "8b4b074012fe3bd731c218a4956f85ce8dadd74d5afe81a3e04c2795a2a533ee"
EXPECTED_CONTROL_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
EXPECTED_ENGINE_BUNDLE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
SCHEMA = "titan.v5.f50.adversarial-world-search.v1"
EVALUATOR = "cloud-execution-lab/reference/evaluator/evaluate.py"
PACK = "cloud-pack/pack.py"
LOADER = "20260907-offline-agent/evaluate.py"
SHARED = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
BANK = "cloud-execution-lab/candidates/v4/research/reference-policy-bank"
SUPPORTED_OPPONENTS = ("apex_v7", "arlene_v14")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def clone_json(value):
    return json.loads(canonical(value))


def parse_csv_ints(value: str, *, allowed=None) -> list[int]:
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values or len(values) != len(set(values)):
        raise ValueError("Expected distinct comma-separated integers")
    if allowed is not None and not set(values) <= set(allowed):
        raise ValueError(f"Values must be in {sorted(allowed)}")
    return values


def seed_plan(explicit: str | None, start: int | None, count: int | None, stride: int) -> list[int]:
    if explicit:
        if start is not None or count is not None:
            raise ValueError("Use either --seeds or --seed-start/--seed-count")
        return parse_csv_ints(explicit)
    if start is None or count is None:
        raise ValueError("Provide --seeds or both --seed-start and --seed-count")
    if count < 1 or stride < 1:
        raise ValueError("seed count and stride must be positive")
    return [start + i * stride for i in range(count)]


def safe_margin(game: dict, seat: int) -> float | None:
    if game.get("status") != "complete" or game.get("steps") != 719:
        return None
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        return None
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in scores):
        return None
    return float(scores[seat] - scores[1 - seat])


def outcome(margin: float) -> str:
    return "win" if margin > 0 else "loss" if margin < 0 else "tie"


def classify_pair(control: dict, candidate: dict, seat: int) -> dict:
    control_margin = safe_margin(control, seat)
    candidate_margin = safe_margin(candidate, seat)
    if control_margin is None or candidate_margin is None:
        return {
            "status": "invalid_pair",
            "control_margin": control_margin,
            "candidate_margin": candidate_margin,
            "margin_delta": None,
            "regression": False,
            "conversion": None,
        }
    delta = candidate_margin - control_margin
    before, after = outcome(control_margin), outcome(candidate_margin)
    return {
        "status": "complete_pair",
        "control_margin": control_margin,
        "candidate_margin": candidate_margin,
        "margin_delta": delta,
        "regression": delta < 0,
        "conversion": f"{before}_to_{after}" if before != after else "none",
    }


def first_divergence(control_steps: list[dict], candidate_steps: list[dict]) -> dict:
    """Return the earliest causal divergence; fail closed on impossible prehistory drift."""
    if len(control_steps) != len(candidate_steps):
        return {"kind": "trace_length_mismatch", "control_steps": len(control_steps),
                "candidate_steps": len(candidate_steps), "valid": False}
    for index, (left, right) in enumerate(zip(control_steps, candidate_steps)):
        if left["step"] != right["step"] or left["step"] != index:
            return {"kind": "step_index_mismatch", "step": index, "valid": False}
        if left["candidate_observation_sha256"] != right["candidate_observation_sha256"]:
            # If no prior candidate action differed, identical deterministic worlds should
            # not expose different public state. Treat this as custody/nondeterminism, not
            # a candidate regression witness.
            return {
                "kind": "pre_action_state_divergence",
                "step": index,
                "control_observation_sha256": left["candidate_observation_sha256"],
                "candidate_observation_sha256": right["candidate_observation_sha256"],
                "valid": False,
            }
        if left["opponent_action_sha256"] != right["opponent_action_sha256"]:
            return {
                "kind": "pre_candidate_opponent_divergence",
                "step": index,
                "control_opponent_action_sha256": left["opponent_action_sha256"],
                "candidate_opponent_action_sha256": right["opponent_action_sha256"],
                "valid": False,
            }
        if left["candidate_action_sha256"] != right["candidate_action_sha256"]:
            return {
                "kind": "candidate_action",
                "step": index,
                "observation_sha256": left["candidate_observation_sha256"],
                "control_action_sha256": left["candidate_action_sha256"],
                "candidate_action_sha256": right["candidate_action_sha256"],
                "control_action": left["candidate_action"],
                "candidate_action": right["candidate_action"],
                "public_observation": left["candidate_observation"],
                "bank_before": left["bank_before"],
                "valid": True,
            }
    return {"kind": "identity", "step": None, "valid": True}


def signature(witness: dict) -> str:
    if not witness.get("valid") or witness.get("kind") != "candidate_action":
        raise ValueError("Only valid candidate-action witnesses have regression signatures")
    payload = {
        "step": witness["step"],
        "observation_sha256": witness["observation_sha256"],
        "control_action_sha256": witness["control_action_sha256"],
        "candidate_action_sha256": witness["candidate_action_sha256"],
    }
    return sha256_bytes(canonical(payload))


def reduce_witnesses(rows: list[dict]) -> list[dict]:
    """One deterministic exact reproducer per first-divergence signature."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if not row.get("regression"):
            continue
        witness = row.get("first_divergence", {})
        if not witness.get("valid") or witness.get("kind") != "candidate_action":
            continue
        groups.setdefault(signature(witness), []).append(row)
    reduced = []
    for sig, members in sorted(groups.items()):
        # Most negative margin is the strongest reproducer; deterministic tiebreaks
        # choose the earliest divergence, then numerically smallest seed/seat.
        chosen = min(members, key=lambda row: (
            row["margin_delta"], row["first_divergence"]["step"], row["seed"], row["seat"]
        ))
        reduced.append({
            "signature": sig,
            "members": len(members),
            "seed": chosen["seed"],
            "seat": chosen["seat"],
            "opponent": chosen["opponent"],
            "control_margin": chosen["control_margin"],
            "candidate_margin": chosen["candidate_margin"],
            "margin_delta": chosen["margin_delta"],
            "conversion": chosen["conversion"],
            "first_divergence": chosen["first_divergence"],
        })
    return reduced


def _bank_from_state(state) -> list[float]:
    try:
        farms = state[0].observation.farms
        return [float(farms[i]["money"]) for i in range(2)]
    except Exception:
        return [0.0, 0.0]


def play_trace(ev, engine, specs, cache, loader, seed: int, candidate_seat: int,
               rng_seed: int, action_timeout: float, startup_timeout: float,
               game_timeout: float) -> tuple[dict, list[dict]]:
    """Evaluator-compatible game with candidate-side public/action trace capture."""
    cfg = ev.Struct({key: value.get("default") if isinstance(value, dict) else value
                     for key, value in engine.specification["configuration"].items()})
    if not isinstance(cfg.episodeSteps, int) or cfg.episodeSteps != 720:
        raise ValueError(f"F50 requires canonical 720-step configuration, got {cfg.episodeSteps!r}")
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    started, initial_cpu = time.perf_counter(), time.process_time()
    actors = []
    trace_rows: list[dict] = []
    trace_digest = hashlib.sha256()
    result = {"seed": seed, "candidate_seat": candidate_seat, "status": "failed",
              "scores": None, "failure": None, "steps": 0, "episode_steps": cfg.episodeSteps,
              "daily_bank": []}
    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise ValueError("Environment seed must not be exposed to agents")
        for seat, spec in enumerate(specs):
            actor = ev.Actor(spec, cache, loader, rng_seed + (seat != candidate_seat), startup_timeout)
            actors.append(actor)
            if actor.ready.get("kind") != "ready":
                result["failure"] = {"seat": seat, "step": 0, "phase": "startup", **actor.ready}
                return result, trace_rows
        for step in range(cfg.episodeSteps):
            actions = []
            candidate_observation = None
            candidate_observation_sha = None
            bank_before = _bank_from_state(state)
            for seat, actor in enumerate(actors):
                remaining = game_timeout - (time.perf_counter() - started)
                if remaining <= 0:
                    result["failure"] = {"kind": "game_timeout", "seat": None, "step": step}
                    return result, trace_rows
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                if seat == candidate_seat:
                    candidate_observation = clone_json(state[seat].observation)
                    candidate_observation_sha = sha256_bytes(canonical(candidate_observation))
                response = actor.act(state[seat].observation, cfg, min(action_timeout, remaining))
                if response.get("kind") != "action":
                    result["failure"] = {"seat": seat, "step": step, "phase": "action", **response}
                    return result, trace_rows
                actions.append(clone_json(response["action"]))
            if candidate_observation is None or candidate_observation_sha is None:
                raise AssertionError("candidate observation capture missing")
            opponent_seat = 1 - candidate_seat
            row = {
                "step": step,
                "candidate_observation_sha256": candidate_observation_sha,
                "candidate_observation": candidate_observation,
                "candidate_action_sha256": sha256_bytes(canonical(actions[candidate_seat])),
                "candidate_action": actions[candidate_seat],
                "opponent_action_sha256": sha256_bytes(canonical(actions[opponent_seat])),
                "bank_before": bank_before,
            }
            trace_rows.append(row)
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            result["steps"] += 1
            bank = _bank_from_state(state)
            trace_digest.update(canonical({"step": step, "actions": actions, "bank": bank}))
            done = all(s.status == "DONE" for s in state)
            if (step + 1) % cfg.turnsPerDay == 0 or done:
                result["daily_bank"].append({"step": step, "bank": bank})
            if done:
                scores = [s.reward for s in state]
                if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in scores):
                    raise ValueError("Nonfinite or missing terminal score")
                result.update(status="complete", scores=scores)
                env.done = True
                return result, trace_rows
        result["failure"] = {"kind": "incomplete", "seat": None, "step": result["steps"]}
    except Exception as exc:
        result["failure"] = {"kind": "engine_error", "seat": None, "step": result["steps"],
                             "error": f"{type(exc).__name__}: {exc}"[:1000]}
    finally:
        for actor in actors:
            actor.close()
        result["actors"] = [actor.report() for actor in actors]
        result["wall_seconds"] = time.perf_counter() - started
        result["driver_cpu_seconds"] = time.process_time() - initial_cpu
        result["bank_snapshot"] = _bank_from_state(state)
        trace_digest.update(canonical([clone_json(s.observation) for s in state]))
        result["trace_sha256"] = trace_digest.hexdigest()
    return result, trace_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-root", type=Path, required=True,
                        help="Existing revenue/kaggriculture directory")
    parser.add_argument("--engine-dir", type=Path, required=True,
                        help="Pinned official engine cache")
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--opponents", default="apex_v7,arlene_v14")
    parser.add_argument("--seeds")
    parser.add_argument("--seed-start", type=int)
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--seed-stride", type=int, default=1)
    parser.add_argument("--seats", default="0,1")
    parser.add_argument("--rng-seed", type=int, default=20260913)
    parser.add_argument("--max-regressions", type=int, default=16)
    parser.add_argument("--action-timeout", type=float, default=1.25)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--game-timeout", type=float, default=900.0)
    args = parser.parse_args()

    if sys.platform != "linux":
        parser.error("F50 uses the existing Linux process evaluator")
    try:
        seeds = seed_plan(args.seeds, args.seed_start, args.seed_count, args.seed_stride)
        seats = parse_csv_ints(args.seats, allowed={0, 1})
    except ValueError as exc:
        parser.error(str(exc))
    opponents = [item.strip() for item in args.opponents.split(",") if item.strip()]
    if not opponents or len(opponents) != len(set(opponents)) or not set(opponents) <= set(SUPPORTED_OPPONENTS):
        parser.error("opponents must be distinct apex_v7 and/or arlene_v14")
    if args.max_regressions < 1:
        parser.error("--max-regressions must be positive")
    if any(not math.isfinite(value) or value <= 0 for value in
           (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("timeouts must be finite and positive")

    kg_root = args.kg_root.resolve(strict=True)
    engine_dir = args.engine_dir.resolve(strict=True)
    control = args.control.resolve(strict=True)
    candidate = args.candidate.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.resolve(strict=True)

    shared = load(kg_root / SHARED, "f50_shared")
    if shared.digest(control) != EXPECTED_CONTROL_SHA256:
        raise ValueError("Control archive differs from exact production20f")
    if shared.digest(candidate) != EXPECTED_CANDIDATE_SHA256:
        raise ValueError("Candidate archive differs from held WF1+C02 leader")
    control_members = shared.archive_members(control)
    candidate_members = shared.archive_members(candidate)

    # Build one immutable execution closure before importing any executable harness bytes.
    with tempfile.TemporaryDirectory(prefix="f50-snapshot-", dir=output.parent) as temp:
        staged = Path(temp) / "kg"
        harness = shared.snapshot_harness(kg_root, staged, opponents)
        output.mkdir()
        snapshot_root = output / ".harness-snapshot"
        os.replace(staged, snapshot_root)

    ev = load(snapshot_root / EVALUATOR, "f50_evaluator")
    pack = load(snapshot_root / PACK, "f50_pack")
    bridge = load(snapshot_root / BANK / "reference_policies.py", "f50_reference_policies")
    engine, engine_hashes = ev.get_engine(engine_dir, snapshot_root / LOADER)

    runtime_root = output / "opponents"
    runtimes = {}
    opponent_receipts = {}
    expected_bridge = harness["repository_files"][BANK + "/reference_policies.py"]["sha256"]
    expected_registry = harness["repository_files"][BANK + "/REFERENCE-POLICIES.json"]["sha256"]
    for name in opponents:
        runtime = runtime_root / name
        receipt = bridge.prepare(name, snapshot_root, runtime)
        if (receipt.get("bridge_sha256") != expected_bridge
                or receipt.get("source_registry_sha256") != expected_registry
                or receipt.get("support_files") != harness["opponent_support_sha256"]):
            raise ValueError(f"Opponent preparation escaped authenticated snapshot: {name}")
        if Path(receipt.get("support_root", "")).resolve(strict=True) != snapshot_root.resolve(strict=True):
            raise ValueError(f"Opponent support root mismatch: {name}")
        runtimes[name] = runtime
        opponent_receipts[name] = receipt

    metadata = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "control_sha256": EXPECTED_CONTROL_SHA256,
        "engine_bundle_authority_sha256": EXPECTED_ENGINE_BUNDLE_SHA256,
        "engine_ref": ev.ENGINE_REF,
        "engine_files_sha256": engine_hashes,
        "harness": harness,
        "evaluator_sha256": shared.digest(snapshot_root / EVALUATOR),
        "loader_sha256": shared.digest(snapshot_root / LOADER),
        "launcher_sha256": shared.digest(__file__),
        "opponent_receipts": opponent_receipts,
        "seeds": seeds,
        "seats": seats,
        "opponents": opponents,
        "rng_seed": args.rng_seed,
        "limits": {"action_rpc_seconds": args.action_timeout,
                   "startup_seconds": args.startup_timeout,
                   "game_seconds": args.game_timeout,
                   "max_regressions": args.max_regressions},
        "submission_hold": True,
        "method": (
            "Exact production20f and held WF1+C02 archives; copied and authenticated Commons "
            "evaluator/loader/packer/reference-policy closure; pinned official interpreter; "
            "fresh process-isolated matched games; deterministic seed/seat order. A regression "
            "is candidate margin < control margin. A causal witness is accepted only when the "
            "first differing candidate action is reached from byte-equivalent canonical public "
            "observations with identical opponent action at that step. Any earlier observation, "
            "opponent-action, timeout, DQ, fallback, incomplete game, or identity mismatch fails "
            "closed and is not reported as a candidate regression witness."
        ),
    }
    shared.write_json(output / "run.json", metadata)

    rows = []
    regressions = 0
    invalid = 0
    for opponent in opponents:
        for seed in seeds:
            for seat in seats:
                # pair_cell needs the immutable engine cache/loader paths; call the lower layer
                # here so there are no hidden globals or host-side mutable references.
                games, traces = {}, {}
                for label, members in (("control", control_members), ("candidate", candidate_members)):
                    with tempfile.TemporaryDirectory(prefix=f"f50-{opponent}-{seed}-p{seat}-{label}-", dir=output) as temp:
                        directory = Path(temp)
                        payload = directory / "payload"
                        shared.extract_members(members, payload)
                        adapter = directory / "adapter.py"
                        pack.write_adapter(adapter, payload / "main.py")
                        rival = str(runtimes[opponent] / "adapter.py")
                        specs = [str(adapter), rival] if seat == 0 else [rival, str(adapter)]
                        game, trace_rows = play_trace(
                            ev, engine, specs, engine_dir, snapshot_root / LOADER,
                            seed, seat, args.rng_seed, args.action_timeout,
                            args.startup_timeout, args.game_timeout,
                        )
                    games[label], traces[label] = game, trace_rows
                pair = classify_pair(games["control"], games["candidate"], seat)
                divergence = first_divergence(traces["control"], traces["candidate"])
                row = {
                    "seed": seed, "seat": seat, "opponent": opponent, **pair,
                    "control_trace_sha256": games["control"].get("trace_sha256"),
                    "candidate_trace_sha256": games["candidate"].get("trace_sha256"),
                    "first_divergence": divergence,
                    "control_failure": games["control"].get("failure"),
                    "candidate_failure": games["candidate"].get("failure"),
                }
                row_invalid = pair["status"] != "complete_pair" or not divergence.get("valid")
                if pair["regression"] and divergence.get("kind") != "candidate_action":
                    row_invalid = True
                    row["regression"] = False
                    row["status"] = "invalid_regression_witness"
                if row_invalid:
                    invalid += 1
                elif pair["regression"]:
                    regressions += 1
                rows.append(row)
                shared.write_json(output / "rows.json", rows)
                print(json.dumps({k: row.get(k) for k in
                                  ("opponent", "seed", "seat", "status", "margin_delta", "regression", "conversion")}),
                      flush=True)
                if regressions >= args.max_regressions:
                    break
            if regressions >= args.max_regressions:
                break
        if regressions >= args.max_regressions:
            break

    valid_pairs = [row for row in rows if row["status"] == "complete_pair"]
    deltas = [row["margin_delta"] for row in valid_pairs]
    reduced = reduce_witnesses(rows)
    summary = {
        "scheduled_cells": len(rows),
        "complete_pairs": len(valid_pairs),
        "invalid_cells": invalid,
        "regressions": sum(bool(row.get("regression")) for row in rows),
        "distinct_regression_signatures": len(reduced),
        "positive": sum(row["margin_delta"] > 0 for row in valid_pairs),
        "zero": sum(row["margin_delta"] == 0 for row in valid_pairs),
        "negative": sum(row["margin_delta"] < 0 for row in valid_pairs),
        "mean_margin_delta": statistics.mean(deltas) if deltas else None,
        "median_margin_delta": statistics.median(deltas) if deltas else None,
        "min_margin_delta": min(deltas) if deltas else None,
        "max_margin_delta": max(deltas) if deltas else None,
        "win_to_loss": sum(row.get("conversion") == "win_to_loss" for row in rows),
        "loss_to_win": sum(row.get("conversion") == "loss_to_win" for row in rows),
        "fail_closed": invalid > 0,
    }
    report = {"run": metadata, "summary": summary, "minimal_reproducers": reduced, "rows": rows}
    shared.write_json(output / "report.json", report)
    print("SUMMARY " + json.dumps(summary), flush=True)
    return int(invalid > 0)


if __name__ == "__main__":
    raise SystemExit(main())
