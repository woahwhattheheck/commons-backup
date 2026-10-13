#!/usr/bin/env python3
"""Run the exact-current TITAN final-pressure three-arm development panel."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import traceback
from typing import Any, Mapping

import evidence
import game_runner
import panel_analysis
import variants as arm_defs

OPERATION = "op:titan-v3-final-pressure-three-arm-20260909-solstice"
ALLOWED_DEVELOPMENT_SEEDS = frozenset(
    (2609099821, 2609099822, 2609099823, 2609099824)
)


def _write_failed_receipt(
    output: Path,
    receipt: Mapping[str, Any] | None,
    stage: str,
    exc: BaseException,
    started: float,
) -> None:
    base = (
        dict(receipt)
        if isinstance(receipt, Mapping)
        else {"schema_version": 1, "operation": OPERATION}
    )
    base.update(
        status="failed",
        failure_stage=stage,
        failure={
            "type": type(exc).__name__,
            "message": str(exc)[:2000],
            "traceback": traceback.format_exc()[-6000:],
        },
        wall_seconds=time.time() - started,
    )
    try:
        evidence.write_json(output, base)
    except Exception:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operation": OPERATION,
                    "status": "failed",
                    "failure_stage": stage,
                    "failure": {
                        "type": type(exc).__name__,
                        "message": str(exc)[:500],
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def parse_seeds(value: str) -> list[int]:
    try:
        seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise evidence.EvidenceError(
            "--seeds requires comma-separated integers"
        ) from exc
    if not seeds or len(seeds) != len(set(seeds)):
        raise evidence.EvidenceError("--seeds requires distinct integers")
    disallowed = sorted(set(seeds) - ALLOWED_DEVELOPMENT_SEEDS)
    if disallowed:
        raise evidence.EvidenceError(
            f"Unreserved development seeds: {disallowed}"
        )
    return seeds


def _validate_archive(args, work: Path) -> tuple[Path, dict[str, Any]]:
    archive_path = args.archive.resolve(strict=True)
    archive_snapshot = evidence.snapshot(archive_path, max_bytes=64 << 20)
    if archive_snapshot.sha256 != args.expected_archive_sha256:
        raise evidence.EvidenceError(
            f"Archive SHA mismatch: {archive_snapshot.sha256}"
        )
    if len(archive_snapshot.data) != args.expected_archive_bytes:
        raise evidence.EvidenceError(
            f"Archive size mismatch: {len(archive_snapshot.data)}"
        )
    private_archive = work / "archive.snapshot.tar.gz"
    private_archive.write_bytes(archive_snapshot.data)
    runtime = work / "runtime"
    members = evidence.safe_extract(private_archive, runtime)
    if members.count("SOURCE.json") != 1:
        raise evidence.EvidenceError(
            "Archive must contain exactly one root SOURCE.json"
        )
    runtime_members = [name for name in members if name != "SOURCE.json"]
    if len(runtime_members) != args.expected_member_count:
        raise evidence.EvidenceError(
            f"Runtime member count mismatch: {len(runtime_members)}"
        )
    source_snapshot = evidence.snapshot(
        runtime / "SOURCE.json", max_bytes=4 << 20
    )
    if source_snapshot.sha256 != args.expected_source_sha256:
        raise evidence.EvidenceError(
            f"SOURCE.json SHA mismatch: {source_snapshot.sha256}"
        )
    return runtime, {
        "path": str(archive_path),
        "sha256": archive_snapshot.sha256,
        "bytes": len(archive_snapshot.data),
        "runtime_member_count": len(runtime_members),
        "total_regular_members": len(members),
        "source_manifest_sha256": source_snapshot.sha256,
    }


def _load_evaluator(runtime: Path):
    evaluator_path = runtime / "checks/reference/evaluator/evaluate.py"
    loader = runtime / "checks/reference/evaluator/loader.py"
    engine_dir = runtime / "checks/reference/engine"
    required = [
        evaluator_path,
        loader,
        *(
            engine_dir / name
            for name in ("kaggriculture.py", "kaggriculture.json", "utils.py")
        ),
    ]
    for path in required:
        if not path.is_file():
            raise evidence.EvidenceError(
                f"Missing evaluator input: {path.relative_to(runtime)}"
            )
    evaluator = game_runner.import_file(
        evaluator_path, "titan_final_pressure_evaluator"
    )
    if evaluator.ENGINE_REF != game_runner.ENGINE_REF:
        raise evidence.EvidenceError(
            f"Engine ref drift: {evaluator.ENGINE_REF}"
        )
    engine, engine_hashes = evaluator.get_engine(engine_dir, loader)
    return evaluator, engine, engine_dir, loader, {
        "ref": game_runner.ENGINE_REF,
        "sha256": engine_hashes,
        "evaluator_sha256": evidence.snapshot(evaluator_path).sha256,
        "loader_sha256": evidence.snapshot(loader).sha256,
    }


def _initial_receipt(
    args,
    archive: Mapping[str, Any],
    canonical: Mapping[str, Any],
    variants: list[dict[str, Any]],
    opponents: Mapping[str, Any],
    seeds: list[int],
    engine_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    expected_cells = (
        len(variants) * len(opponents) * len(seeds) * 2
    )
    return {
        "schema_version": 1,
        "operation": OPERATION,
        "status": "running",
        "dispatch_commit": args.dispatch_commit,
        "runner_head": args.runner_head,
        "archive": dict(archive),
        "canonical": dict(canonical),
        "engine": dict(engine_receipt),
        "variants": [
            {
                key: value
                for key, value in row.items()
                if key not in ("candidate", "root")
            }
            for row in variants
        ],
        "opponents": list(opponents),
        "opponent_evidence": dict(opponents),
        "seeds": seeds,
        "seed_allowlist": sorted(ALLOWED_DEVELOPMENT_SEEDS),
        "agent_rng_seed": args.agent_rng_seed,
        "limits": {
            "action_timeout_seconds": args.action_timeout,
            "startup_timeout_seconds": args.startup_timeout,
            "game_timeout_seconds": args.game_timeout,
        },
        "expected_cells": expected_cells,
        "attempted_keys": [],
        "completed_keys": [],
        "games": [],
        "wall_seconds": 0.0,
        "python": sys.version,
        "platform": sys.platform,
    }


def _execute_cells(
    args,
    receipt: dict[str, Any],
    variants: list[dict[str, Any]],
    opponents: Mapping[str, Mapping[str, Any]],
    seeds: list[int],
    evaluator,
    engine,
    engine_dir: Path,
    loader: Path,
    started: float,
) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    attempted: list[list[Any]] = []
    completed: list[list[Any]] = []
    for variant in variants:
        for opponent, opponent_meta in opponents.items():
            for seed in seeds:
                for seat in (0, 1):
                    key = [variant["name"], opponent, seed, seat]
                    attempted.append(key)
                    receipt["attempted_keys"] = attempted
                    receipt["running_key"] = key
                    evidence.write_json(args.output, receipt)
                    pair = (
                        [variant["candidate"], opponent_meta["spec"]]
                        if seat == 0
                        else [opponent_meta["spec"], variant["candidate"]]
                    )
                    game = game_runner.play_attributed(
                        evaluator,
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
                    )
                    row = {
                        "variant": variant["name"],
                        "opponent": opponent,
                        **game,
                    }
                    games.append(row)
                    print(
                        json.dumps(
                            {
                                name: row.get(name)
                                for name in (
                                    "variant",
                                    "opponent",
                                    "seed",
                                    "candidate_seat",
                                    "status",
                                    "scores",
                                    "failure",
                                )
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    receipt["games"] = games
                    receipt["wall_seconds"] = time.time() - started
                    if (
                        row.get("status") != "complete"
                        or row.get("failure") is not None
                    ):
                        receipt["status"] = "failed"
                        receipt["failed_cell"] = row
                        receipt["completed_keys"] = completed
                        evidence.write_json(args.output, receipt)
                        raise RuntimeError(
                            "Fail-closed game failure: "
                            + "/".join(map(str, key))
                        )
                    completed.append(key)
                    receipt["completed_keys"] = completed
                    receipt.pop("running_key", None)
                    evidence.write_json(args.output, receipt)
    return games


def run(args) -> dict[str, Any]:
    started = time.time()
    receipt: dict[str, Any] | None = None
    try:
        seeds = parse_seeds(args.seeds)
        with tempfile.TemporaryDirectory(
            prefix="titan-final-pressure-"
        ) as directory:
            work = Path(directory)
            runtime, archive_receipt = _validate_archive(args, work)
            variants, canonical = arm_defs.prepare_variants(
                runtime, work / "variants"
            )
            if (
                args.expected_main_sha256
                and canonical["main_sha256"] != args.expected_main_sha256
            ):
                raise evidence.EvidenceError(
                    f"Canonical main.py SHA mismatch: {canonical['main_sha256']}"
                )
            if (
                args.expected_config_sha256
                and canonical["config_sha256"]
                != args.expected_config_sha256
            ):
                raise evidence.EvidenceError(
                    "Canonical config SHA mismatch: "
                    + canonical["config_sha256"]
                )
            opponents = game_runner.opponent_specs(args.opponent, runtime)
            evaluator, engine, engine_dir, loader, engine_receipt = (
                _load_evaluator(runtime)
            )
            receipt = _initial_receipt(
                args,
                archive_receipt,
                canonical,
                variants,
                opponents,
                seeds,
                engine_receipt,
            )
            evidence.write_json(args.output, receipt)
            games = _execute_cells(
                args,
                receipt,
                variants,
                opponents,
                seeds,
                evaluator,
                engine,
                engine_dir,
                loader,
                started,
            )
            panel_analysis.validate_games(
                games, variants, list(opponents), seeds
            )
            summary = panel_analysis.summarize(
                games, variants, list(opponents), seeds
            )
            receipt.update(
                status="complete",
                all_complete=True,
                summary=summary,
                scheduled_games=len(games),
                wall_seconds=time.time() - started,
                method=(
                    "Pinned official interpreter; process-isolated agents; "
                    "exact immutable canonical archive; three source/config "
                    "arms; candidate-action and post-state digests separated; "
                    "offline development attribution only."
                ),
            )
            evidence.write_json(args.output, receipt)
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(
                panel_analysis.markdown(receipt), encoding="utf-8"
            )
            print(
                "FINAL_PRESSURE_SUMMARY "
                + json.dumps(
                    {
                        "development_signal": summary["development_signal"],
                        "leaders": summary["leaders_by_mean_margin"],
                        "comparisons": {
                            key: {
                                "mean_margin_delta": value[
                                    "mean_margin_delta"
                                ],
                                "new_losses": value["new_losses"],
                                "post_state_changed_cells": value[
                                    "post_state_changed_cells"
                                ],
                            }
                            for key, value in summary["comparisons"].items()
                        },
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            return receipt
    except BaseException as exc:
        _write_failed_receipt(args.output, receipt, "run", exc, started)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--archive", type=Path, required=True)
    value.add_argument("--expected-archive-sha256", required=True)
    value.add_argument("--expected-archive-bytes", type=int, required=True)
    value.add_argument("--expected-member-count", type=int, required=True)
    value.add_argument("--expected-source-sha256", required=True)
    value.add_argument("--expected-main-sha256")
    value.add_argument("--expected-config-sha256")
    value.add_argument("--dispatch-commit", required=True)
    value.add_argument("--runner-head", required=True)
    value.add_argument("--seeds", required=True)
    value.add_argument("--opponent", action="append", default=[])
    value.add_argument("--agent-rng-seed", type=int, default=20260909)
    value.add_argument("--action-timeout", type=float, default=1.0)
    value.add_argument("--startup-timeout", type=float, default=10.0)
    value.add_argument("--game-timeout", type=float, default=120.0)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--markdown", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    hashes = (
        args.expected_archive_sha256,
        args.expected_source_sha256,
        args.expected_main_sha256,
        args.expected_config_sha256,
    )
    if any(
        value is not None and not evidence.valid_sha256(value)
        for value in hashes
    ):
        raise SystemExit(
            "Expected hashes must be lowercase 64-hex SHA-256 values"
        )
    if args.expected_archive_bytes <= 0 or args.expected_member_count <= 0:
        raise SystemExit(
            "Expected archive bytes/member count must be positive"
        )
    if any(
        not math.isfinite(value) or value <= 0
        for value in (
            args.action_timeout,
            args.startup_timeout,
            args.game_timeout,
        )
    ):
        raise SystemExit("Timeouts must be finite and positive")
    try:
        run(args)
    except Exception as exc:
        print(
            f"FINAL_PRESSURE_FAILED {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
