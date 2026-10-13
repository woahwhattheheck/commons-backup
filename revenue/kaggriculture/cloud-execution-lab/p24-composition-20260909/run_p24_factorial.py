#!/usr/bin/env python3
"""Run a fail-closed 2^4 configuration factorial from one immutable TITAN archive."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import traceback

import p24_factorial as p24

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
OPERATION = "op:titan-v25-orders-20260909-P24"

DEVELOPMENT_SEEDS = {2609099501}
HELD_SEEDS = set(range(2609099509, 2609099517))


def import_file(path: Path):
    spec = importlib.util.spec_from_file_location("titan_p24_evaluator", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def opponent_specs(items, runtime: Path):
    """Resolve opponent specs and bind each entry file by SHA-256.

    Runtime-prefixed opponents are transitively archive-bound.
    External opponents bind the entry file; multi-module external/held
    runs should supply a hermetic bundle digest via future extension.
    """
    output = {}
    for item in items:
        label, separator, value = item.partition("=")
        if not separator or not label or label in output:
            raise ValueError("Each opponent must be a unique LABEL=SPEC")
        entry_path = None
        is_runtime = value.startswith("runtime:")
        if is_runtime:
            relative = value.removeprefix("runtime:")
            path, call_separator, callable_name = relative.partition("::")
            entry_path = (runtime / path).resolve(strict=True)
            value = str(entry_path) + ("::" + callable_name if call_separator else "")
        elif value != "official_starter":
            path, call_separator, callable_name = value.partition("::")
            entry_path = Path(path).resolve(strict=True)
            value = str(entry_path) + ("::" + callable_name if call_separator else "")
        sha = p24.sha256_file(entry_path) if entry_path is not None else None
        output[label] = {
            "spec": value,
            "path": str(entry_path) if entry_path else None,
            "sha256": sha,
            "binding": "archive-transitive" if is_runtime else ("entry-file" if entry_path else "official"),
        }
    if not output:
        raise ValueError("At least one --opponent is required")
    return output


def _write_failed_receipt(output: Path, receipt: dict | None, stage: str, exc: BaseException, started: float):
    """Fail-closed reporter: ensure a receipt exists for any interruption."""
    base = receipt if isinstance(receipt, dict) else {
        "schema_version": 1,
        "operation": OPERATION,
        "status": "failed",
    }
    base = dict(base)
    base["status"] = "failed"
    base["failure_stage"] = stage
    base["failure"] = {
        "type": type(exc).__name__,
        "message": str(exc)[:2000],
        "traceback": traceback.format_exc()[-4000:],
    }
    base["wall_seconds"] = time.time() - started
    try:
        p24.write_json(output, base)
    except Exception:
        # Last-resort: write minimal JSON so artifact is never empty {}
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "schema_version": 1,
                "operation": OPERATION,
                "status": "failed",
                "failure_stage": stage,
                "failure": {"type": type(exc).__name__, "message": str(exc)[:500]},
            }, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


def run(args):
    started = time.time()
    receipt = None
    output = args.output
    try:
        archive = args.archive.resolve(strict=True)
        archive_sha, archive_bytes = p24.sha256_file(archive), archive.stat().st_size
        if args.expected_archive_sha256 and archive_sha != args.expected_archive_sha256:
            raise AssertionError(f"Archive SHA mismatch: {archive_sha}")
        if args.expected_archive_bytes is not None and archive_bytes != args.expected_archive_bytes:
            raise AssertionError(f"Archive size mismatch: {archive_bytes}")
        seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
        if not seeds or len(seeds) != len(set(seeds)):
            raise ValueError("--seeds requires distinct integers")
        phase = getattr(args, "phase", "development") or "development"
        frozen = getattr(args, "frozen_selection_hash", None)
        if phase == "development":
            disallowed = [s for s in seeds if s in HELD_SEEDS or s not in DEVELOPMENT_SEEDS]
            if disallowed:
                raise ValueError(f"Development phase rejects non-allowlisted or held seeds: {disallowed}")
        elif phase == "held":
            if not frozen:
                raise ValueError("Held phase requires --frozen-selection-hash")
            if not p24.valid_hash(frozen):
                raise ValueError("--frozen-selection-hash must be a 64-hex digest")
            # Binding to a real frozen-selection document is required for holdout authority;
            # the public smoke remains development-only.
            disallowed = [s for s in seeds if s not in HELD_SEEDS]
            if disallowed:
                raise ValueError(f"Held phase accepts only reserved held seeds: {disallowed}")
        else:
            raise ValueError(f"Unknown phase: {phase}")
        with tempfile.TemporaryDirectory(prefix="titan-p24-") as directory:
            work = Path(directory); runtime = work / "runtime"
            members = p24.safe_extract(archive, runtime)
            # Exactly one root SOURCE.json; compare only the other regular members to expected runtime_files.
            source_name = "SOURCE.json"
            if members.count(source_name) != 1:
                raise AssertionError(f"Expected exactly one root SOURCE.json; found {members.count(source_name)}")
            runtime_members = [m for m in members if m != source_name]
            if args.expected_member_count is not None and len(runtime_members) != args.expected_member_count:
                raise AssertionError(
                    f"Runtime member count mismatch: {len(runtime_members)} (total regular={len(members)})")
            source = runtime / source_name
            if not source.is_file():
                raise FileNotFoundError("SOURCE.json missing after extract")
            source_sha = p24.sha256_file(source)
            if args.expected_source_sha256 and source_sha != args.expected_source_sha256:
                raise AssertionError(f"SOURCE.json SHA mismatch: {source_sha}")
            matrix, config = p24.prepare_variants(runtime, work / "variants")
            opponents = opponent_specs(args.opponent, runtime)
            evaluator_path = runtime / "checks/reference/evaluator/evaluate.py"
            loader = runtime / "checks/reference/evaluator/loader.py"
            engine_dir = runtime / "checks/reference/engine"
            required = [evaluator_path, loader, *(engine_dir / name for name in ("kaggriculture.py", "kaggriculture.json", "utils.py"))]
            for path in required:
                if not path.exists():
                    raise FileNotFoundError(f"Missing evaluator input: {path.relative_to(runtime)}")
            evaluator = import_file(evaluator_path)
            if evaluator.ENGINE_REF != ENGINE_REF:
                raise AssertionError(f"Engine ref drift: {evaluator.ENGINE_REF}")
            engine, engine_hashes = evaluator.get_engine(engine_dir, loader)
            expected_keys = {(row["name"], opp, seed, seat)
                             for row in matrix for opp in opponents for seed in seeds for seat in (0, 1)}
            # Initialize exact-identity receipt before gameplay (checkpoint for interruption modes).
            receipt = {
                "schema_version": 1, "operation": OPERATION, "dispatch_commit": args.dispatch_commit,
                "status": "running", "phase": phase,
                "frozen_selection_hash": frozen,
                "archive": {"path": str(archive), "sha256": archive_sha, "bytes": archive_bytes,
                            "runtime_member_count": len(runtime_members), "total_regular_members": len(members),
                            "source_manifest_sha256": source_sha},
                "engine": {"ref": ENGINE_REF, "sha256": engine_hashes,
                           "evaluator_sha256": p24.sha256_file(evaluator_path),
                           "loader_sha256": p24.sha256_file(loader)},
                "runner_head": getattr(args, "runner_head", None),
                "factors": list(p24.FACTORS), "base_config": config,
                "variants": [{key: value for key, value in row.items() if key != "candidate"} for row in matrix],
                "opponents": list(opponents), "opponent_evidence": opponents, "seeds": seeds,
                "agent_rng_seed": args.agent_rng_seed,
                "limits": {"action_timeout_seconds": args.action_timeout, "startup_timeout_seconds": args.startup_timeout,
                           "game_timeout_seconds": args.game_timeout},
                "expected_cells": len(expected_keys),
                "attempted_keys": [],
                "completed_keys": [],
                "games": [],
                "wall_seconds": 0.0, "python": sys.version, "platform": sys.platform,
            }
            p24.write_json(output, receipt)
            games = []
            completed_keys = []
            attempted_keys = []
            for variant in matrix:
                for opponent, meta in opponents.items():
                    rival = meta["spec"]
                    for seed in seeds:
                        for seat in (0, 1):
                            key = (variant["name"], opponent, seed, seat)
                            attempted_keys.append(list(key))
                            receipt["attempted_keys"] = attempted_keys
                            receipt["running_key"] = list(key)
                            p24.write_json(output, receipt)
                            pair = [variant["candidate"], rival] if seat == 0 else [rival, variant["candidate"]]
                            game = evaluator.play(engine, pair, engine_dir, loader, seed, seat, args.agent_rng_seed,
                                                  args.action_timeout, args.startup_timeout, args.game_timeout, None)
                            row = {"variant": variant["name"], "opponent": opponent, **game}
                            games.append(row)
                            print(json.dumps({k: row.get(k) for k in
                                             ("variant", "opponent", "seed", "candidate_seat", "status", "scores", "failure")},
                                             sort_keys=True), flush=True)
                            # Checkpoint after every cell; completed_keys only on valid complete.
                            receipt["games"] = games
                            receipt["wall_seconds"] = time.time() - started
                            if game.get("status") != "complete" or game.get("failure") is not None:
                                receipt["status"] = "failed"
                                receipt["failed_cell"] = row
                                receipt["completed_keys"] = completed_keys  # do not include failed
                                p24.write_json(output, receipt)
                                raise RuntimeError(f"Fail-closed game failure: {variant['name']}/{opponent}/{seed}/seat{seat}")
                            completed_keys.append(list(key))
                            receipt["completed_keys"] = completed_keys
                            receipt.pop("running_key", None)
                            p24.write_json(output, receipt)
            p24.validate_games(games, matrix, list(opponents), seeds)
            summary = p24.summarize(games, matrix)
            receipt.update({
                "status": "complete", "all_complete": True, "summary": summary,
                "scheduled_games": len(games), "wall_seconds": time.time() - started,
                "method": "Pinned official interpreter; process-isolated agents; one archive; configuration-only 2^4 matched cells; offline; not hosted scoring.",
            })
            p24.write_json(output, receipt)
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(p24.markdown(receipt), encoding="utf-8")
            print("P24_SUMMARY " + json.dumps(summary["joint_vs_baseline"], sort_keys=True), flush=True)
            return receipt
    except BaseException as exc:
        _write_failed_receipt(output, receipt, stage="run", exc=exc, started=started)
        raise


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--archive", type=Path, required=True)
    value.add_argument("--expected-archive-sha256")
    value.add_argument("--expected-archive-bytes", type=int)
    value.add_argument("--expected-member-count", type=int,
                       help="Expected count of regular runtime files excluding the single root SOURCE.json")
    value.add_argument("--expected-source-sha256")
    value.add_argument("--dispatch-commit", required=True)
    value.add_argument("--seeds", required=True)
    value.add_argument("--phase", choices=["development", "held"], default="development")
    value.add_argument("--frozen-selection-hash", default=None)
    value.add_argument("--runner-head", default=None, help="Workflow/runner commit SHA for evidence binding")
    value.add_argument("--opponent", action="append", default=[])
    value.add_argument("--agent-rng-seed", type=int, default=20260909)
    value.add_argument("--action-timeout", type=float, default=1.0)
    value.add_argument("--startup-timeout", type=float, default=10.0)
    value.add_argument("--game-timeout", type=float, default=120.0)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--markdown", type=Path, required=True)
    return value


def main():
    args = parser().parse_args()
    if any(not math.isfinite(value) or value <= 0 for value in
           (args.action_timeout, args.startup_timeout, args.game_timeout)):
        raise SystemExit("Timeouts must be finite and positive")
    run(args)


if __name__ == "__main__":
    main()
