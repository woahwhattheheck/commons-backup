#!/usr/bin/env python3
"""Run one both-seat current-TITAN versus Apex shard with full action retention.

This composes the repository's existing process-isolated cloud evaluator and
pinned official interpreter.  It does not alter either agent.  Every ordered
joint action and before/after bank value is retained in gzip JSONL sidecars.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evaluator", type=Path, required=True)
    p.add_argument("--loader", type=Path, required=True)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--apex", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--action-timeout", type=float, default=1.0)
    p.add_argument("--startup-timeout", type=float, default=10.0)
    p.add_argument("--game-timeout", type=float, default=120.0)
    args = p.parse_args()

    for path in (args.evaluator, args.loader, args.candidate, args.apex, args.archive):
        path.resolve(strict=True)
    args.engine_dir.resolve(strict=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    archive_hash = sha256(args.archive)
    expected_archive = "87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7"
    if archive_hash != expected_archive:
        raise SystemExit(f"archive mismatch: {archive_hash}")

    ev = load_module(args.evaluator.resolve(), "astra_current_apex_eval")
    engine, engine_hashes = ev.get_engine(args.engine_dir.resolve(), args.loader.resolve())
    candidate = ev.resolve_spec(str(args.candidate.resolve()))
    apex = ev.resolve_spec(str(args.apex.resolve()))

    report: dict[str, Any] = {
        "schema_version": 1,
        "method": (
            "Repository cloud-eval Actor/play with the pinned official interpreter; "
            "fresh isolated actor processes; full ordered joint actions captured by a "
            "read-only interpreter wrapper. Local cloud development evidence, not hosted rating."
        ),
        "seed": args.seed,
        "archive": {
            "path": args.archive.name,
            "bytes": args.archive.stat().st_size,
            "sha256": archive_hash,
        },
        "candidate": ev.fingerprint(candidate),
        "apex": {
            **ev.fingerprint(apex),
            "agent_so_sha256": sha256(args.apex.with_name("agent.so")),
            "policy_cpp_sha256": sha256(args.apex.parent / "source" / "policy.cpp"),
            "tape_inc_sha256": sha256(args.apex.parent / "source" / "tape.inc"),
            "bridge_sha256": sha256(args.apex.parent / "submission_bridge.cpp"),
        },
        "engine_ref": ev.ENGINE_REF,
        "engine_sha256": engine_hashes,
        "evaluator_sha256": sha256(args.evaluator),
        "loader_sha256": sha256(args.loader),
        "runner_sha256": sha256(Path(__file__)),
        "python": sys.version,
        "platform": platform.platform(),
        "limits": {
            "action_rpc_seconds": args.action_timeout,
            "startup_seconds": args.startup_timeout,
            "game_seconds_between_steps": args.game_timeout,
            "remaining_overage_time": 0,
        },
        "games": [],
    }

    for candidate_seat in (0, 1):
        events: list[dict[str, Any]] = []
        original_interpreter = engine.interpreter

        def capture_interpreter(state, env):
            has_actions = any(bool(getattr(s, "action", None)) for s in state)
            if has_actions:
                step = int(state[0].observation.get("step", len(events)))
                before = [float(state[0].observation.farms[i]["money"]) for i in range(2)]
                actions = [plain(copy.deepcopy(s.action)) for s in state]
            result = original_interpreter(state, env)
            if has_actions:
                after = [float(state[0].observation.farms[i]["money"]) for i in range(2)]
                events.append({
                    "step": step,
                    "actions": actions,
                    "bank_before": before,
                    "bank_after": after,
                    "status_after": [str(s.status) for s in state],
                    "reward_after": [plain(s.reward) for s in state],
                })
            return result

        engine.interpreter = capture_interpreter
        specs = [candidate, apex] if candidate_seat == 0 else [apex, candidate]
        started = time.perf_counter()
        try:
            game = ev.play(
                engine,
                specs,
                args.engine_dir.resolve(),
                args.loader.resolve(),
                args.seed,
                candidate_seat,
                rng_seed=20260907,
                action_timeout=args.action_timeout,
                startup_timeout=args.startup_timeout,
                game_timeout=args.game_timeout,
            )
        finally:
            engine.interpreter = original_interpreter
        game["opponent"] = "apex"
        game["capture_wall_seconds"] = time.perf_counter() - started
        trace_path = args.output_dir / f"actions-seed{args.seed}-seat{candidate_seat}.jsonl.gz"
        with gzip.open(trace_path, "wt", encoding="utf-8", newline="\n", compresslevel=9) as f:
            for event in events:
                f.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False))
                f.write("\n")
        game["action_trace"] = {
            "path": trace_path.name,
            "events": len(events),
            "bytes": trace_path.stat().st_size,
            "sha256": sha256(trace_path),
        }
        if game.get("status") == "complete":
            own = float(game["scores"][candidate_seat])
            rival = float(game["scores"][1 - candidate_seat])
            game["candidate_cash"] = own
            game["rival_cash"] = rival
            game["margin"] = own - rival
            game["verdict"] = "W" if own > rival else "L" if own < rival else "T"
        report["games"].append(game)
        print(json.dumps({
            "seed": args.seed,
            "candidate_seat": candidate_seat,
            "status": game.get("status"),
            "scores": game.get("scores"),
            "verdict": game.get("verdict"),
            "margin": game.get("margin"),
            "events": len(events),
            "failure": game.get("failure"),
        }, sort_keys=True), flush=True)

    complete = [g for g in report["games"] if g.get("status") == "complete"]
    report["summary"] = {
        "scheduled": 2,
        "completed": len(complete),
        "failed": 2 - len(complete),
        "wins": sum(g.get("verdict") == "W" for g in complete),
        "ties": sum(g.get("verdict") == "T" for g in complete),
        "losses": sum(g.get("verdict") == "L" for g in complete),
        "mean_candidate_cash": (sum(g["candidate_cash"] for g in complete) / len(complete)) if complete else None,
        "mean_rival_cash": (sum(g["rival_cash"] for g in complete) / len(complete)) if complete else None,
        "mean_margin": (sum(g["margin"] for g in complete) / len(complete)) if complete else None,
        "max_candidate_call_seconds": max(
            (g["actors"][g["candidate_seat"]]["max_call_seconds"] for g in complete),
            default=None,
        ),
        "max_candidate_rpc_seconds": max(
            (g["actors"][g["candidate_seat"]]["max_rpc_seconds"] for g in complete),
            default=None,
        ),
    }
    report_path = args.output_dir / "RESULTS.json"
    temporary = report_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, report_path)
    print("SUMMARY " + json.dumps(report["summary"], sort_keys=True), flush=True)
    return 0 if len(complete) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
