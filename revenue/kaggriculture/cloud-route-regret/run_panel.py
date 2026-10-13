#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the exact-current paired route-checkpoint regret panel."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from panel_engine import play
from source_contract import checkpoints, git_blob_sha1, sha256, verify_source_contract
from thresholds import build_pairs, fit_report

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / "cloud-execution-lab"
EVALUATOR_PATH = LAB / "reference/evaluator/evaluate.py"
LOADER_PATH = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"
ARM_PATH = HERE / "route_arm.py"
ARLENE_PATH = LAB / "reference/next-panel/vendor/arlene.py"
V1_PATH = LAB / "runtime/variants/v1/candidate.py"
OPERATION = "titan-v3-route-checkpoint-regret-20260910-01"
DEFAULT_DEVELOPMENT = (2609104101, 2609104102)
DEFAULT_HOLDOUT = (2609104201, 2609104202)


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def atomic_json(path: Path, value: Any) -> None:
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


def tree_inventory() -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(HERE.iterdir()):
        if path.is_file() and not path.is_symlink():
            result[path.name] = {
                "sha256": sha256(path),
                "git_blob": git_blob_sha1(path),
                "bytes": path.stat().st_size,
            }
    return result


def _arm_specs() -> dict[str, str]:
    names = ["auto"]
    for checkpoint, *_ in checkpoints():
        names.extend((f"force_{checkpoint}", f"stay_{checkpoint}"))
    return {name: str(ARM_PATH.resolve()) + f"::{name}" for name in names}


def _expected_grid(seeds, opponents, arms):
    return {
        (arm, opponent, seed, seat)
        for arm in arms
        for opponent in opponents
        for seed in seeds
        for seat in (0, 1)
    }


def validate_grid(games, seeds, opponents, arms) -> None:
    expected = _expected_grid(seeds, opponents, arms)
    indexed = set()
    invocations = set()
    for game in games:
        key = (
            game.get("arm"),
            game.get("opponent"),
            game.get("seed"),
            game.get("tested_seat"),
        )
        if key in indexed:
            raise ValueError(f"duplicate game cell: {key}")
        indexed.add(key)
        invocation = game.get("invocation_id")
        if not isinstance(invocation, str) or len(invocation) != 32:
            raise ValueError("invalid invocation ID")
        if invocation in invocations:
            raise ValueError("duplicate invocation ID")
        invocations.add(invocation)
    if indexed != expected:
        raise ValueError(
            f"game grid mismatch: missing={sorted(expected-indexed)}, "
            f"extra={sorted(indexed-expected)}"
        )


def markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    fit = summary.get("threshold_fit") or {}
    lines = [
        "# TITAN V3 exact route-checkpoint regret panel",
        "",
        f"- Operation: `{report['operation']}`",
        f"- Structural status: **{report['status']}**",
        f"- Evidence verdict: **{summary.get('verdict')}**",
        f"- Exact runner head: `{report['runner_head']}`",
        f"- Named current base: `{report['source_receipt']['authored_base']}`",
        f"- Completed games: {sum(g['status'] == 'complete' for g in report['games'])}/{len(report['games'])}",
        f"- Eligible prefix-identical pairs: {summary.get('eligible_pairs')}",
        f"- Rejected/contaminated pairs: {summary.get('rejected_pairs')}",
        f"- Development seeds: `{','.join(map(str, report['development_seeds']))}`",
        f"- Holdout seeds: `{','.join(map(str, report['holdout_seeds']))}`",
        "",
        "Each FORCE/STAY pair begins from an identical hashed public world at the named checkpoint, uses the same rival checkpoint action, and changes only the prefix-compatible route choice. The untouched AUTO arm must reproduce the naturally selected side exactly before the pair is eligible.",
        "",
        "| checkpoint | feature | shipped | selected on dev | dev cells | holdout cells | holdout W/T/L delta | holdout own delta | holdout margin delta | screen |",
        "|---:|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in fit.get("checkpoints", []):
        delta = row["holdout_delta"]
        lines.append(
            "| {checkpoint} | `{feature}` | {shipped_threshold} | {selected_threshold} | "
            "{development_cells} | {holdout_cells} | {wins:+}/{ties:+}/{losses:+} | "
            "{own_total:+.0f} | {margin_total:+.0f} | {screen} |".format(
                **row,
                wins=delta["wins"],
                ties=delta["ties"],
                losses=delta["losses"],
                own_total=delta["own_total"],
                margin_total=delta["margin_total"],
                screen="PASS" if row["screen_passed"] else "NO CHANGE",
            )
        )
        if row["gate_reasons"]:
            lines.append(
                f"<!-- checkpoint {row['checkpoint']}: "
                + "; ".join(row["gate_reasons"])
                + " -->"
            )
    lines.extend(
        [
            "",
            "A threshold screen is evidence for a separate review, not a source patch or promotion authorization. This workflow does not modify the canonical runtime, build a replacement archive, call Kaggle, or mutate any provider.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(args) -> dict[str, Any]:
    if set(args.development_seeds) & set(args.holdout_seeds):
        raise ValueError("development and holdout seed sets overlap")
    source_receipt = verify_source_contract()
    evaluator = import_file(EVALUATOR_PATH, "sol_lever_route_regret_evaluator")
    if evaluator.ENGINE_REF != source_receipt["engine_ref"]:
        raise ValueError("evaluator engine ref drift")
    engine, engine_hashes = evaluator.get_engine(ENGINE_DIR, LOADER_PATH)
    arm_specs = _arm_specs()
    opponents = {
        "exact_public_arlene": str(ARLENE_PATH.resolve()) + "::agent",
        "frozen_v1": str(V1_PATH.resolve()) + "::agent",
    }
    all_seeds = tuple(args.development_seeds) + tuple(args.holdout_seeds)
    started = time.time()
    report = {
        "schema": "titan-route-regret-panel/v1",
        "operation": OPERATION,
        "status": "running",
        "runner_head": args.runner_head,
        "source_receipt": source_receipt,
        "experiment_tree": tree_inventory(),
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
        "arms": arm_specs,
        "opponents": {
            name: {
                "entrypoint": spec,
                "sha256": sha256(Path(spec.split("::", 1)[0])),
                "git_blob": git_blob_sha1(Path(spec.split("::", 1)[0])),
            }
            for name, spec in opponents.items()
        },
        "development_seeds": list(args.development_seeds),
        "holdout_seeds": list(args.holdout_seeds),
        "agent_rng_seed": args.rng_seed,
        "limits": {
            "action_timeout_seconds": args.action_timeout,
            "startup_timeout_seconds": args.startup_timeout,
            "game_timeout_seconds": args.game_timeout,
        },
        "method": (
            "Pinned official interpreter; fresh process and working directory per agent per game; "
            "both seats; two frozen opponent families; AUTO plus one FORCE/STAY pair per checkpoint; "
            "diagnostic removed before interpreter; threshold selected on development seeds only."
        ),
        "games": [],
        "pairs": [],
        "rejected_pairs": [],
        "summary": None,
        "wall_seconds": 0.0,
    }
    atomic_json(args.output, report)
    for opponent_name, rival in opponents.items():
        for seed in all_seeds:
            for seat in (0, 1):
                for arm, tested in arm_specs.items():
                    specs = [tested, rival] if seat == 0 else [rival, tested]
                    game = play(
                        evaluator,
                        engine,
                        specs,
                        seed,
                        seat,
                        arm=arm,
                        opponent=opponent_name,
                        rng_seed=args.rng_seed,
                        action_timeout=args.action_timeout,
                        startup_timeout=args.startup_timeout,
                        game_timeout=args.game_timeout,
                    )
                    report["games"].append(game)
                    report["wall_seconds"] = time.time() - started
                    atomic_json(args.output, report)
                    print(
                        json.dumps(
                            {
                                "arm": arm,
                                "opponent": opponent_name,
                                "seed": seed,
                                "seat": seat,
                                "status": game["status"],
                                "scores": game["scores"],
                                "checkpoint_receipts": len(
                                    game["checkpoint_receipts"]
                                ),
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    if game["status"] != "complete":
                        raise RuntimeError(
                            f"game failed: {arm}/{opponent_name}/{seed}/{seat}: "
                            f"{game['failure']}"
                        )
    validate_grid(report["games"], all_seeds, tuple(opponents), tuple(arm_specs))
    pairs, rejected = build_pairs(report["games"], checkpoints())
    fit = fit_report(
        pairs,
        checkpoints(),
        set(args.development_seeds),
        set(args.holdout_seeds),
        minimum_holdout_cells=args.minimum_holdout_cells,
    )
    verdict = "PAIR_CONTAMINATION" if rejected else fit["verdict"]
    report["pairs"] = pairs
    report["rejected_pairs"] = rejected
    report["summary"] = {
        "verdict": verdict,
        "games": len(report["games"]),
        "eligible_pairs": len(pairs),
        "rejected_pairs": len(rejected),
        "threshold_fit": fit,
    }
    report["status"] = "complete"
    report["wall_seconds"] = time.time() - started
    atomic_json(args.output, report)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--development-seeds", type=parse_seeds, default=DEFAULT_DEVELOPMENT
    )
    parser.add_argument("--holdout-seeds", type=parse_seeds, default=DEFAULT_HOLDOUT)
    parser.add_argument("--rng-seed", type=int, default=20260910)
    parser.add_argument("--action-timeout", type=float, default=1.25)
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    parser.add_argument("--game-timeout", type=float, default=240.0)
    parser.add_argument("--minimum-holdout-cells", type=int, default=4)
    parser.add_argument("--runner-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    if isinstance(args.rng_seed, bool):
        raise ValueError("rng seed must be integer")
    if args.minimum_holdout_cells < 1:
        raise ValueError("minimum holdout cells must be positive")
    report = run(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verdict": report["summary"]["verdict"],
                "games": report["summary"]["games"],
                "eligible_pairs": report["summary"]["eligible_pairs"],
                "rejected_pairs": report["summary"]["rejected_pairs"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
