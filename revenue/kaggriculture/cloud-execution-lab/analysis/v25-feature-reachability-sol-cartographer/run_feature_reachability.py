#!/usr/bin/env python3
"""Run an exact-archive TITAN enabled-feature reachability / leave-one-out panel."""
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

import feature_reachability as fr

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
OPERATION = "op:titan-v3-v25-feature-reachability-bisect-20260910-01"
DEVELOPMENT_SEEDS = {2609099501}


def import_file(path: Path):
    spec = importlib.util.spec_from_file_location("titan_feature_reachability_evaluator", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def opponent_specs(items: list[str], runtime: Path) -> dict[str, dict[str, str | None]]:
    output: dict[str, dict[str, str | None]] = {}
    for item in items:
        label, separator, value = item.partition("=")
        if not separator or not label or label in output:
            raise ValueError("Each --opponent must be a unique LABEL=SPEC")
        entry_path: Path | None = None
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
        output[label] = {
            "spec": value,
            "path": str(entry_path) if entry_path else None,
            "sha256": fr.sha256_file(entry_path) if entry_path else None,
            "binding": "archive-transitive" if is_runtime else ("entry-file" if entry_path else "official-engine"),
        }
    if not output:
        raise ValueError("At least one --opponent is required")
    return output


def episode_steps(engine) -> int:
    value = engine.specification["configuration"]["episodeSteps"]
    value = value.get("default") if isinstance(value, dict) else value
    if not isinstance(value, int) or value < 2:
        raise ValueError(f"Invalid official episodeSteps: {value!r}")
    return value


def write_failed(output: Path, receipt: dict | None, stage: str, exc: BaseException, started: float) -> None:
    base = dict(receipt) if isinstance(receipt, dict) else {
        "schema_version": 1,
        "operation": OPERATION,
    }
    base.update({
        "status": "failed",
        "failure_stage": stage,
        "failure": {
            "type": type(exc).__name__,
            "message": str(exc)[:2000],
            "traceback": traceback.format_exc()[-5000:],
        },
        "wall_seconds": time.time() - started,
    })
    try:
        fr.write_json(output, base)
    except Exception:
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
    try:
        archive = args.archive.resolve(strict=True)
        external_receipt_path = args.archive_receipt.resolve(strict=True)
        external_receipt = json.loads(external_receipt_path.read_text(encoding="utf-8"))
        archive_sha = fr.sha256_file(archive)
        archive_bytes = archive.stat().st_size
        expected = {
            "sha256": args.expected_archive_sha256,
            "bytes": args.expected_archive_bytes,
            "runtime_files": args.expected_runtime_files,
            "source_manifest_sha256": args.expected_source_sha256,
        }
        for key, value in expected.items():
            if value is not None and external_receipt.get(key) != value:
                raise AssertionError(f"External archive receipt {key} mismatch: {external_receipt.get(key)!r}")
        if archive_sha != external_receipt.get("sha256"):
            raise AssertionError(f"Archive SHA mismatch: actual={archive_sha}, receipt={external_receipt.get('sha256')}")
        if archive_bytes != external_receipt.get("bytes"):
            raise AssertionError(f"Archive byte-size mismatch: actual={archive_bytes}, receipt={external_receipt.get('bytes')}")

        seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
        if not seeds or len(seeds) != len(set(seeds)):
            raise ValueError("--seeds requires distinct integers")
        disallowed = [seed for seed in seeds if seed not in DEVELOPMENT_SEEDS]
        if disallowed:
            raise ValueError(f"Development panel rejects non-allowlisted seeds: {disallowed}")

        with tempfile.TemporaryDirectory(prefix="titan-feature-reachability-") as directory:
            work = Path(directory)
            runtime = work / "runtime"
            members = fr.safe_extract(archive, runtime)
            if members.count("SOURCE.json") != 1:
                raise AssertionError(f"Expected exactly one root SOURCE.json; found {members.count('SOURCE.json')}")
            runtime_members = [name for name in members if name != "SOURCE.json"]
            if len(runtime_members) != external_receipt.get("runtime_files"):
                raise AssertionError(
                    f"Runtime member count mismatch: {len(runtime_members)} != {external_receipt.get('runtime_files')}")
            source_path = runtime / "SOURCE.json"
            source_sha = fr.sha256_file(source_path)
            if source_sha != external_receipt.get("source_manifest_sha256"):
                raise AssertionError(
                    f"Internal SOURCE.json mismatch: {source_sha} != {external_receipt.get('source_manifest_sha256')}")

            config = fr.validate_config(json.loads((runtime / "TITAN-CONFIG.json").read_text(encoding="utf-8")))
            source_references = fr.find_config_references(runtime)
            tested_factors = fr.runtime_access_factors(source_references)
            static_unreferenced = [factor for factor in fr.FACTORS if factor not in tested_factors]
            if not tested_factors:
                raise AssertionError("No enabled feature flag had an active-source runtime access")
            if static_unreferenced:
                raise AssertionError(
                    "Whole-stack contract requires a runtime access beyond the Features declaration "
                    f"for every enabled flag: {static_unreferenced}")
            variants, base_config = fr.materialize_variants(runtime, work / "variants", tested_factors)

            evaluator_path = runtime / "checks/reference/evaluator/evaluate.py"
            loader = runtime / "checks/reference/evaluator/loader.py"
            engine_dir = runtime / "checks/reference/engine"
            required = [
                evaluator_path,
                loader,
                *(engine_dir / name for name in ("kaggriculture.py", "kaggriculture.json", "utils.py")),
            ]
            for path in required:
                if not path.is_file():
                    raise FileNotFoundError(f"Missing evaluator input: {path.relative_to(runtime)}")
            evaluator = import_file(evaluator_path)
            if evaluator.ENGINE_REF != ENGINE_REF:
                raise AssertionError(f"Engine ref drift: {evaluator.ENGINE_REF}")
            engine, engine_hashes = evaluator.get_engine(engine_dir, loader)
            steps = episode_steps(engine)
            opponents = opponent_specs(args.opponent, runtime)

            expected_games = len(variants) * len(opponents) * len(seeds) * 2
            replay_games = 1 if args.recheck_control else 0
            hard_call_bound = fr.max_scheduled_agent_calls(expected_games + replay_games, steps)
            if hard_call_bound > args.max_agent_calls:
                raise ValueError(
                    f"Scheduled hard call bound {hard_call_bound} exceeds --max-agent-calls {args.max_agent_calls}")

            receipt = {
                "schema_version": 1,
                "operation": OPERATION,
                "status": "running",
                "phase": "development",
                "runner_head": args.runner_head,
                "archive": {
                    "path": str(archive),
                    "sha256": archive_sha,
                    "bytes": archive_bytes,
                    "runtime_member_count": len(runtime_members),
                    "source_manifest_sha256": source_sha,
                    "external_receipt_path": str(external_receipt_path),
                    "external_receipt_sha256": fr.sha256_file(external_receipt_path),
                },
                "engine": {
                    "ref": ENGINE_REF,
                    "sha256": engine_hashes,
                    "evaluator_sha256": fr.sha256_file(evaluator_path),
                    "loader_sha256": fr.sha256_file(loader),
                    "episode_steps": steps,
                },
                "all_enabled_config": base_config,
                "all_enabled_config_sha256": fr.sha256_file(runtime / "TITAN-CONFIG.json"),
                "requested_factors": list(fr.FACTORS),
                "tested_factors": tested_factors,
                "static_unreferenced_factors": static_unreferenced,
                "source_references": source_references,
                "variants": [{key: value for key, value in row.items() if key != "candidate"} for row in variants],
                "opponents": list(opponents),
                "opponent_evidence": opponents,
                "seeds": seeds,
                "agent_rng_seed": args.agent_rng_seed,
                "limits": {
                    "action_timeout_seconds": args.action_timeout,
                    "startup_timeout_seconds": args.startup_timeout,
                    "game_timeout_seconds": args.game_timeout,
                    "max_agent_calls": args.max_agent_calls,
                    "scheduled_hard_agent_call_bound": hard_call_bound,
                },
                "expected_complete_games": expected_games,
                "attempted_keys": [],
                "completed_keys": [],
                "games": [],
                "wall_seconds": 0.0,
                "python": sys.version,
                "platform": sys.platform,
            }
            fr.write_json(args.output, receipt)

            games = []
            observed_calls = 0
            for variant in variants:
                for opponent, opponent_meta in opponents.items():
                    for seed in seeds:
                        for seat in (0, 1):
                            key = [variant["name"], opponent, seed, seat]
                            receipt["attempted_keys"].append(key)
                            receipt["running_key"] = key
                            fr.write_json(args.output, receipt)
                            pair = [variant["candidate"], opponent_meta["spec"]]
                            if seat == 1:
                                pair.reverse()
                            game = evaluator.play(
                                engine,
                                pair,
                                engine_dir,
                                loader,
                                seed,
                                seat,
                                args.agent_rng_seed,
                                args.action_timeout,
                                args.startup_timeout,
                                args.game_timeout,
                                None,
                            )
                            row = {"variant": variant["name"], "opponent": opponent, **game}
                            games.append(row)
                            calls = fr.actor_calls(row)
                            observed_calls += calls
                            receipt["games"] = games
                            receipt["observed_agent_calls"] = observed_calls
                            receipt["wall_seconds"] = time.time() - started
                            print(json.dumps({
                                "variant": variant["name"],
                                "opponent": opponent,
                                "seed": seed,
                                "candidate_seat": seat,
                                "status": row.get("status"),
                                "scores": row.get("scores"),
                                "agent_calls": calls,
                                "failure": row.get("failure"),
                            }, sort_keys=True), flush=True)
                            if observed_calls > args.max_agent_calls:
                                raise RuntimeError(f"Observed agent calls {observed_calls} exceeded cap {args.max_agent_calls}")
                            if row.get("status") != "complete" or row.get("failure") is not None:
                                receipt["failed_cell"] = row
                                fr.write_json(args.output, receipt)
                                raise RuntimeError(f"Fail-closed game failure: {key}")
                            receipt["completed_keys"].append(key)
                            receipt.pop("running_key", None)
                            fr.write_json(args.output, receipt)

            fr.validate_games(games, variants, list(opponents), seeds)

            reproducibility = {"checked": False}
            if args.recheck_control:
                first_opponent, first_meta = next(iter(opponents.items()))
                first = next(
                    game for game in games
                    if game["variant"] == "all_enabled"
                    and game["opponent"] == first_opponent
                    and game["seed"] == seeds[0]
                    and game["candidate_seat"] == 0
                )
                replay = evaluator.play(
                    engine,
                    [variants[0]["candidate"], first_meta["spec"]],
                    engine_dir,
                    loader,
                    seeds[0],
                    0,
                    args.agent_rng_seed,
                    args.action_timeout,
                    args.startup_timeout,
                    args.game_timeout,
                    None,
                )
                replay_calls = fr.actor_calls(replay)
                observed_calls += replay_calls
                same = (
                    replay.get("status") == "complete"
                    and replay.get("failure") is None
                    and replay.get("trace_sha256") == first.get("trace_sha256")
                    and replay.get("scores") == first.get("scores")
                )
                reproducibility = {
                    "checked": True,
                    "same_trace_and_scores": same,
                    "original_trace_sha256": first.get("trace_sha256"),
                    "replay_trace_sha256": replay.get("trace_sha256"),
                    "original_scores": first.get("scores"),
                    "replay_scores": replay.get("scores"),
                    "agent_calls": replay_calls,
                }
                if observed_calls > args.max_agent_calls:
                    raise RuntimeError(f"Observed agent calls {observed_calls} exceeded cap {args.max_agent_calls}")
                if not same:
                    raise AssertionError("All-enabled control replay was not deterministic")

            summary = fr.summarize(games, tested_factors, source_references)
            summary["observed_agent_calls"] = observed_calls
            receipt.update({
                "status": "complete",
                "all_complete": True,
                "scheduled_games": len(games),
                "observed_agent_calls": observed_calls,
                "reproducibility": reproducibility,
                "summary": summary,
                "wall_seconds": time.time() - started,
                "method": (
                    "Pinned official interpreter; exact committed archive and internal SOURCE.json; fresh process-isolated "
                    "agents; all-enabled control plus one exact config-bit disable per source-referenced enabled feature; "
                    "matched opponent/seed/both-seat cells; offline development evidence; not hosted scoring or promotion authority."
                ),
            })
            fr.write_json(args.output, receipt)
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(fr.markdown(receipt), encoding="utf-8")
            print("FEATURE_REACHABILITY_SUMMARY " + json.dumps({
                "candidate_disable": summary["candidate_disable"],
                "candidate_keep": summary["candidate_keep"],
                "panel_inert": summary["panel_inert"],
                "needs_more_evidence": summary["needs_more_evidence"],
                "agent_calls": observed_calls,
            }, sort_keys=True), flush=True)
            return receipt
    except BaseException as exc:
        write_failed(args.output, receipt, "run", exc, started)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--archive", type=Path, required=True)
    value.add_argument("--archive-receipt", type=Path, required=True)
    value.add_argument("--expected-archive-sha256", required=True)
    value.add_argument("--expected-archive-bytes", type=int, required=True)
    value.add_argument("--expected-runtime-files", type=int, required=True)
    value.add_argument("--expected-source-sha256", required=True)
    value.add_argument("--runner-head", required=True)
    value.add_argument("--seeds", default="2609099501")
    value.add_argument("--opponent", action="append", default=[])
    value.add_argument("--agent-rng-seed", type=int, default=20260910)
    value.add_argument("--action-timeout", type=float, default=1.0)
    value.add_argument("--startup-timeout", type=float, default=15.0)
    value.add_argument("--game-timeout", type=float, default=180.0)
    value.add_argument("--max-agent-calls", type=int, default=45000)
    value.add_argument("--recheck-control", action="store_true")
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--markdown", type=Path, required=True)
    return value


def main() -> None:
    args = parser().parse_args()
    if any(not math.isfinite(value) or value <= 0 for value in (
        args.action_timeout,
        args.startup_timeout,
        args.game_timeout,
    )):
        raise SystemExit("Timeouts must be finite and positive")
    if args.max_agent_calls <= 0:
        raise SystemExit("--max-agent-calls must be positive")
    for value in (args.expected_archive_sha256, args.expected_source_sha256):
        if not fr.valid_hash(value):
            raise SystemExit("Expected hashes must be lowercase 64-hex digests")
    run(args)


if __name__ == "__main__":
    main()
