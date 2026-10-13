#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run closure-bound paired games with action-to-state realization receipts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from panel_engine import play
from realized_execution import compare_game_pair, summarize_pairs
from source_contract import git_blob_sha1, sha256, verify_source_contract

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
EVALUATOR_PATH = LAB / "reference/evaluator/evaluate.py"
LOADER_PATH = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"
BASELINE_PATH = LAB / "main.py"
CANDIDATE_PATH = HERE / "candidate.py"
ARLENE_PATH = LAB / "reference/next-panel/vendor/arlene.py"
V1_PATH = LAB / "runtime/variants/v1/candidate.py"
OPERATION = "titan-v3-market-prefix-realized-execution-20260910-01"
DEFAULT_SEEDS = (2609099601, 2609099602, 2609099603, 2609099604)


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        temporary = stream.name
    os.replace(temporary, path)


def parse_seeds(text: str) -> tuple[int, ...]:
    values = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        value = int(raw)
        if isinstance(value, bool) or value < 0:
            raise ValueError("seeds must be nonnegative literal integers")
        values.append(value)
    if not values or len(values) != len(set(values)):
        raise ValueError("seed list must be nonempty and unique")
    return tuple(values)


def compare_grid(games, seeds, opponent_names):
    expected = {
        (variant, opponent, seed, seat)
        for variant in ("control", "candidate")
        for opponent in opponent_names
        for seed in seeds
        for seat in (0, 1)
    }
    indexed = {}
    invocation_ids = set()
    for game in games:
        seat = game.get("candidate_seat")
        if type(seat) is not int or seat not in (0, 1):
            raise ValueError("game contains non-literal seat")
        key = (game.get("variant"), game.get("opponent"), game.get("seed"), seat)
        if key in indexed:
            raise ValueError(f"duplicate game {key}")
        indexed[key] = game
        invocation = game.get("invocation_id")
        if not isinstance(invocation, str) or len(invocation) != 32 or invocation in invocation_ids:
            raise ValueError("missing or duplicate invocation ID")
        invocation_ids.add(invocation)
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        raise ValueError(f"grid mismatch; missing={missing}, extra={extra}")

    pairs = []
    for opponent in opponent_names:
        for seed in seeds:
            for seat in (0, 1):
                control = indexed[("control", opponent, seed, seat)]
                candidate = indexed[("candidate", opponent, seed, seat)]
                pairs.append(compare_game_pair(control, candidate))
    return summarize_pairs(pairs)


def markdown(report) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# TITAN V3 market-prefix realized-execution panel",
        "",
        f"- Operation: `{report['operation']}`",
        f"- Structural status: **{report['status']}**",
        f"- Economic verdict: **{summary.get('verdict')}**",
        f"- Exact head: `{report['runner_head']}`",
        f"- Completed games: {sum(g['status'] == 'complete' for g in report['games'])}/{len(report['games'])}",
        f"- Paired cells: {summary.get('paired_cells')}",
        f"- Syntactic activation cells/events: {summary.get('syntactic_activation_cells')}/{summary.get('syntactic_events')}",
        f"- Causal realized cells/events: {summary.get('realized_execution_cells')}/{summary.get('realized_events')}",
        f"- Inert/downstream events: {summary.get('inert_events')}/{summary.get('downstream_events')}",
        f"- Mean own delta: {summary.get('mean_own_delta')}",
        f"- Mean rival delta: {summary.get('mean_rival_delta')}",
        f"- Mean margin delta: {summary.get('mean_margin_delta')}",
        f"- Positive/zero/negative own cells: {summary.get('positive_zero_negative_own')}",
        "",
        "A structural crossing counts as realized only when equal pre-state and equal rival action are followed by a different post-interpreter world projection. Submitted actions are excluded from that projection.",
        "",
        "This is an exact offline development screen, not a Kaggle upload, leaderboard result, or promotion authorization.",
    ]
    reasons = summary.get("reasons") or []
    if reasons:
        lines.extend(["", "## Verdict reasons", *[f"- {reason}" for reason in reasons]])
    return "\n".join(lines) + "\n"


def candidate_tree_inventory() -> dict[str, dict[str, object]]:
    result = {}
    for path in sorted(HERE.iterdir()):
        if path.is_file() and not path.is_symlink():
            result[path.name] = {
                "sha256": sha256(path),
                "git_blob": git_blob_sha1(path),
                "bytes": path.stat().st_size,
            }
    return result


def run(args) -> dict:
    source_receipt = verify_source_contract()
    evaluator = import_file(EVALUATOR_PATH, "sol_realizer_evaluator")
    if evaluator.ENGINE_REF != source_receipt["engine_ref"]:
        raise ValueError("evaluator engine ref drift")
    engine, engine_hashes = evaluator.get_engine(ENGINE_DIR, LOADER_PATH)
    baseline_spec = str(BASELINE_PATH.resolve()) + "::agent"
    candidate_spec = str(CANDIDATE_PATH.resolve()) + "::instrumented_agent"
    opponents = {
        "exact_public_arlene": str(ARLENE_PATH.resolve()) + "::agent",
        "frozen_v1": str(V1_PATH.resolve()) + "::agent",
    }
    started = time.time()
    report = {
        "schema": "titan-market-prefix-realized-panel/v1",
        "operation": OPERATION,
        "status": "running",
        "runner_head": args.runner_head,
        "source_receipt": source_receipt,
        "candidate_tree": candidate_tree_inventory(),
        "engine": {"ref": evaluator.ENGINE_REF, "sha256": engine_hashes},
        "evaluator": {
            "path": str(EVALUATOR_PATH),
            "sha256": sha256(EVALUATOR_PATH),
            "git_blob": git_blob_sha1(EVALUATOR_PATH),
        },
        "loader": {
            "path": str(LOADER_PATH),
            "sha256": sha256(LOADER_PATH),
            "git_blob": git_blob_sha1(LOADER_PATH),
        },
        "control": {"entrypoint": baseline_spec, "sha256": sha256(BASELINE_PATH)},
        "candidate": {
            "entrypoint": candidate_spec,
            "sha256": sha256(CANDIDATE_PATH),
            "transform_sha256": sha256(HERE / "market_prefix_rescue.py"),
            "realization_sha256": sha256(HERE / "realized_execution.py"),
        },
        "opponents": {
            name: {"entrypoint": spec, "sha256": sha256(Path(spec.split("::", 1)[0]))}
            for name, spec in opponents.items()
        },
        "seeds": list(args.seeds),
        "agent_rng_seed": args.rng_seed,
        "limits": {
            "action_timeout_seconds": args.action_timeout,
            "startup_timeout_seconds": args.startup_timeout,
            "game_timeout_seconds": args.game_timeout,
        },
        "method": (
            "Pinned official interpreter; fresh process per agent per game; exact control/candidate cells in both seats; "
            "candidate diagnostic stripped before interpreter; pre/post world projection excludes submitted action bytes."
        ),
        "games": [],
        "summary": None,
        "wall_seconds": 0.0,
    }
    atomic_json(args.output, report)
    for variant, tested in (("control", baseline_spec), ("candidate", candidate_spec)):
        for opponent_name, rival in opponents.items():
            for seed in args.seeds:
                for seat in (0, 1):
                    specs = [tested, rival] if seat == 0 else [rival, tested]
                    game = play(
                        evaluator,
                        engine,
                        specs,
                        seed,
                        seat,
                        rng_seed=args.rng_seed,
                        action_timeout=args.action_timeout,
                        startup_timeout=args.startup_timeout,
                        game_timeout=args.game_timeout,
                    )
                    game.update(variant=variant, opponent=opponent_name)
                    report["games"].append(game)
                    report["wall_seconds"] = time.time() - started
                    atomic_json(args.output, report)
                    print(
                        json.dumps(
                            {
                                "variant": variant,
                                "opponent": opponent_name,
                                "seed": seed,
                                "seat": seat,
                                "status": game["status"],
                                "events": game["syntactic_event_count"],
                                "scores": game["scores"],
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    if game["status"] != "complete":
                        raise RuntimeError(f"game failed: {variant}/{opponent_name}/{seed}/{seat}: {game['failure']}")
    report["summary"] = compare_grid(report["games"], args.seeds, tuple(opponents))
    report["status"] = "complete"
    report["wall_seconds"] = time.time() - started
    atomic_json(args.output, report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=parse_seeds, default=DEFAULT_SEEDS)
    parser.add_argument("--rng-seed", type=int, default=20260910)
    parser.add_argument("--action-timeout", type=float, default=1.0)
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--game-timeout", type=float, default=180.0)
    parser.add_argument("--runner-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    if isinstance(args.rng_seed, bool):
        raise ValueError("rng seed must be integer")
    report = run(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verdict": report["summary"]["verdict"],
                "paired_cells": report["summary"]["paired_cells"],
                "realized_events": report["summary"]["realized_events"],
                "mean_own_delta": report["summary"]["mean_own_delta"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
