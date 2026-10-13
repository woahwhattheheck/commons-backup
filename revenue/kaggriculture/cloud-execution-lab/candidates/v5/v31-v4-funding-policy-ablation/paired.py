#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Matched V3.1/V4 funding-policy 2x2 official-engine evidence runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
import time
import types

import ablation

HELPER = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
HELPER_GIT_BLOB = "719e3514d72bc7ea4c3e505836d16fcddae11019"
V31_ARCHIVE_SHA256 = "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361"
SCHEMA = "astra.v5.v31-v4-funding-policy-paired.v1"
RUN_ARMS = ("v31_reference",) + ablation.ARMS
TREATMENTS = ablation.ARMS[1:]


def git_blob_bytes(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def capture_git_blob(path: Path, expected: str) -> bytes:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Authenticated helper must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = git_blob_bytes(raw)
    if actual != expected:
        raise ValueError(f"Helper Git blob mismatch; expected {expected}, got {actual}")
    return raw


def capture_archive(path: Path, expected: str, label: str) -> bytes:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} SHA256 mismatch; expected {expected}, got {actual}")
    return raw


def load_captured(raw: bytes, origin: Path, name: str):
    """Compile and execute exactly one already-authenticated source buffer."""
    if type(raw) is not bytes:
        raise TypeError("captured source must be bytes")
    module = types.ModuleType(name)
    module.__file__ = str(origin)
    module.__package__ = ""
    sys.modules[name] = module
    exec(compile(raw, str(origin), "exec", dont_inherit=True), module.__dict__)
    return module


def capture_sha256(path: Path, expected: str) -> bytes:
    """Single-read one ordinary harness member and authenticate captured bytes."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Authenticated snapshot member must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"Snapshot member SHA256 mismatch; expected {expected}, got {actual}")
    return raw


def write_private_runtime_bytes(raw: bytes, path: Path, expected: str) -> Path:
    """Publish captured bytes once into a private execution-only location."""
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Private runtime bytes do not match authenticated SHA256")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    path.write_bytes(raw)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Private runtime publication changed authenticated bytes")
    return path


def assert_private_execution_path(path: Path, private_root: Path, public_output: Path) -> Path:
    """Fail closed unless an executable leaf lives under private runtime custody."""
    resolved = Path(path).resolve(strict=True)
    private = Path(private_root).resolve(strict=True)
    public = Path(public_output).resolve(strict=True)
    if resolved == public or public in resolved.parents:
        raise ValueError(f"Execution path points into caller-visible output: {resolved}")
    if resolved != private and private not in resolved.parents:
        raise ValueError(f"Execution path escaped private runtime: {resolved}")
    return resolved


def copy_evidence_tree(source: Path, destination: Path) -> Path:
    """Copy private bytes to a caller-visible evidence tree that is never executed."""
    source = Path(source).resolve(strict=True)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


def score_triplet(game: dict, seat: int):
    if game.get("status") != "complete" or game.get("steps") != 719:
        return None
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        return None
    own, rival = scores[seat], scores[1 - seat]
    if (isinstance(own, bool) or isinstance(rival, bool)
            or not isinstance(own, (int, float)) or not isinstance(rival, (int, float))
            or not math.isfinite(float(own)) or not math.isfinite(float(rival))):
        return None
    return {"own": float(own), "rival": float(rival), "margin": float(own - rival)}


def _delta(a, b):
    if a is None or b is None:
        return None
    return {key: float(a[key] - b[key]) for key in ("own", "rival", "margin")}


def _summarize_vectors(vectors: list[dict]) -> dict:
    out = {"pairs": len(vectors)}
    for key in ("own", "rival", "margin"):
        values = [float(vector[key]) for vector in vectors]
        out[f"mean_{key}_delta"] = statistics.mean(values) if values else None
        out[f"median_{key}_delta"] = statistics.median(values) if values else None
        out[f"min_{key}_delta"] = min(values) if values else None
        out[f"max_{key}_delta"] = max(values) if values else None
    return out


def _summarize_delta_rows(rows: list[dict], arm: str) -> dict:
    vectors = [cell["deltas_vs_control"][arm] for cell in rows]
    summary = _summarize_vectors(vectors)
    margins = [vector["margin"] for vector in vectors]
    summary.update({
        "margin_improved": sum(value > 0 for value in margins),
        "margin_unchanged": sum(value == 0 for value in margins),
        "margin_regressed": sum(value < 0 for value in margins),
    })
    return summary


def summarize(cells: list[dict]) -> dict:
    result = {"arms_vs_v4_control": {}, "v31_vs_v4_control": {}, "interaction": {}}
    comparisons = list(TREATMENTS) + ["v31_reference"]
    for arm in comparisons:
        rows = [cell for cell in cells if cell["deltas_vs_control"].get(arm) is not None]
        per_opponent = {}
        for opponent in sorted({cell["opponent"] for cell in cells}):
            opp_rows = [cell for cell in rows if cell["opponent"] == opponent]
            per_opponent[opponent] = _summarize_delta_rows(opp_rows, arm)
        summary = _summarize_delta_rows(rows, arm)
        summary["opponents"] = per_opponent
        if arm == "v31_reference":
            result["v31_vs_v4_control"] = summary
        else:
            result["arms_vs_v4_control"][arm] = summary

    interactions = []
    for cell in cells:
        metrics = cell.get("metrics", {})
        if all(metrics.get(arm) is not None for arm in ablation.ARMS):
            c = metrics["control"]
            a = metrics["min_v31"]
            b = metrics["no_reorder"]
            ab = metrics["funding_pair_v31"]
            interactions.append({
                key: ab[key] - a[key] - b[key] + c[key]
                for key in ("own", "rival", "margin")
            })
    result["interaction"] = _summarize_vectors(interactions)
    result["complete_cells"] = sum(
        all(cell.get("metrics", {}).get(arm) is not None for arm in RUN_ARMS)
        for cell in cells
    )
    result["total_cells"] = len(cells)
    return result


def parse_csv_ints(value: str) -> list[int]:
    values = [int(item) for item in value.split(",") if item]
    if not values or len(values) != len(set(values)):
        raise ValueError("Expected a non-empty distinct integer list")
    return values


def _archive_members_from_captured(helper, raw: bytes, output_parent: Path, prefix: str):
    with tempfile.TemporaryDirectory(prefix=prefix, dir=output_parent) as td:
        sealed = Path(td) / "archive.tar.gz"
        sealed.write_bytes(raw)
        return helper.archive_members(sealed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--v31-baseline", type=Path, required=True)
    parser.add_argument("--v4-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="2051966578,1378040481")
    parser.add_argument("--seats", default="0,1")
    parser.add_argument("--opponents", default="apex_v7,arlene_v14")
    parser.add_argument("--rng-seed", type=int, default=20260912)
    parser.add_argument("--action-timeout", type=float, default=1.25)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--game-timeout", type=float, default=900.0)
    args = parser.parse_args()

    if sys.platform != "linux":
        parser.error("Run games on a Linux fleet VM")
    try:
        seeds = parse_csv_ints(args.seeds)
        seats = parse_csv_ints(args.seats)
    except ValueError as exc:
        parser.error(str(exc))
    opponents = [item for item in args.opponents.split(",") if item]
    if (not set(seats) <= {0, 1} or not opponents or len(opponents) != len(set(opponents))
            or not set(opponents) <= {"apex_v7", "arlene_v14"}):
        parser.error("Use distinct seats 0/1 and opponents apex_v7,arlene_v14")
    if any(not math.isfinite(value) or value <= 0
           for value in (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("Timeouts must be finite and positive")

    root = args.kg_root.resolve(strict=True)
    engine_dir = args.engine_dir.resolve(strict=True)
    v31_path = args.v31_baseline.resolve(strict=True)
    v4_path = args.v4_baseline.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output_parent = output.parent.resolve(strict=True)

    v31_raw = capture_archive(v31_path, V31_ARCHIVE_SHA256, "Submitted-V3.1 baseline")
    v4_raw = ablation.capture_exact_archive(v4_path)
    helper_path = root / HELPER
    helper_raw = capture_git_blob(helper_path, HELPER_GIT_BLOB)
    helper = load_captured(
        helper_raw, helper_path, "funding_policy_authenticated_joint_liquidity_helper"
    )
    if helper.BASELINE_SHA256 != ablation.BASELINE_SHA256:
        raise ValueError("Shared helper baseline authority disagrees with funding-policy runner")

    v31_members = _archive_members_from_captured(
        helper, v31_raw, output_parent, "funding-v31-baseline-"
    )
    v4_members = _archive_members_from_captured(
        helper, v4_raw, output_parent, "funding-v4-baseline-"
    )
    v4_arms, source_receipts = ablation.build_arms(v4_members)
    arm_payloads = {"v31_reference": v31_members, **v4_arms}

    # Core modules, prepared opponents, and per-game candidate payloads all stay
    # under one private runtime. Caller-visible trees are evidence-only copies.
    with tempfile.TemporaryDirectory(
        prefix="funding-private-runtime-", dir=output_parent
    ) as temp:
        private_root = Path(temp)
        runtime_snapshot = private_root / "kg"
        harness = helper.snapshot_harness(root, runtime_snapshot, opponents)

        evaluator_rel = helper.EVALUATOR
        pack_rel = "cloud-pack/pack.py"
        bridge_rel = helper.BANK + "/reference_policies.py"
        loader_rel = "20260907-offline-agent/evaluate.py"
        evaluator_raw = capture_sha256(
            runtime_snapshot / evaluator_rel,
            harness["repository_files"][evaluator_rel]["sha256"],
        )
        pack_raw = capture_sha256(
            runtime_snapshot / pack_rel,
            harness["repository_files"][pack_rel]["sha256"],
        )
        bridge_raw = capture_sha256(
            runtime_snapshot / bridge_rel,
            harness["repository_files"][bridge_rel]["sha256"],
        )
        loader_expected = harness["repository_files"][loader_rel]["sha256"]
        loader_raw = capture_sha256(runtime_snapshot / loader_rel, loader_expected)
        loader = write_private_runtime_bytes(
            loader_raw,
            private_root / "candidate-loader" / "evaluate.py",
            loader_expected,
        )

        evaluator = load_captured(
            evaluator_raw, runtime_snapshot / evaluator_rel, "funding_policy_evaluator"
        )
        pack = load_captured(
            pack_raw, runtime_snapshot / pack_rel, "funding_policy_pack"
        )
        bridge = load_captured(
            bridge_raw, runtime_snapshot / bridge_rel, "funding_policy_reference_bank"
        )
        engine_hashes = evaluator.verify_sources(engine_dir)

        output.mkdir(parents=False, exist_ok=False)
        snapshot_root = output / ".harness-snapshot"
        shutil.copytree(runtime_snapshot, snapshot_root)

        private_opponents = private_root / "opponents"
        private_opponents.mkdir()
        private_games = private_root / "games"
        private_games.mkdir()
        runtime = {}
        opponent_receipts = {}
        expected_bridge = harness["repository_files"][bridge_rel]["sha256"]
        expected_registry = harness["repository_files"][
            helper.BANK + "/REFERENCE-POLICIES.json"
        ]["sha256"]
        for opponent in opponents:
            runtime[opponent] = private_opponents / opponent
            receipt = bridge.prepare(opponent, runtime_snapshot, runtime[opponent])
            if (receipt.get("bridge_sha256") != expected_bridge
                    or receipt.get("source_registry_sha256") != expected_registry
                    or receipt.get("support_files") != harness["opponent_support_sha256"]):
                raise ValueError(f"Opponent escaped authenticated harness: {opponent}")
            if Path(receipt.get("support_root", "")).resolve(strict=True) != runtime_snapshot:
                raise ValueError(f"Opponent did not bind private runtime snapshot: {opponent}")
            assert_private_execution_path(
                runtime[opponent] / "adapter.py", private_root, output
            )
            copy_evidence_tree(runtime[opponent], output / "opponents" / opponent)
            opponent_receipts[opponent] = receipt

        run = {
            "schema": SCHEMA,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "v31_archive_sha256": V31_ARCHIVE_SHA256,
            "v4_archive_sha256": ablation.BASELINE_SHA256,
            "v31_source": ablation.V31_SOURCE,
            "v4_source": ablation.V4_SOURCE,
            "arms": list(RUN_ARMS),
            "v4_arm_source_receipts": source_receipts,
            "seeds": seeds,
            "seats": seats,
            "opponents": opponents,
            "engine": engine_hashes,
            "helper_git_blob": HELPER_GIT_BLOB,
            "helper_sha256": hashlib.sha256(helper_raw).hexdigest(),
            "helper_execution": "single-read Git-blob-authenticated captured bytes",
            "archive_execution": "single-read SHA256-authenticated private snapshots",
            "harness_execution": {
                "mode": "captured core modules + fully private executable leaf artifacts",
                "evaluator_sha256": hashlib.sha256(evaluator_raw).hexdigest(),
                "pack_sha256": hashlib.sha256(pack_raw).hexdigest(),
                "bridge_sha256": hashlib.sha256(bridge_raw).hexdigest(),
                "loader_sha256": hashlib.sha256(loader_raw).hexdigest(),
                "public_snapshot": ".harness-snapshot (evidence only; never executed)",
                "opponents": "private adapters executed; output/opponents are evidence copies",
                "candidates": "private per-game payload/adapter only; no public execution origin",
            },
            "harness": harness,
            "opponent_receipts": opponent_receipts,
            "python": sys.version,
            "platform": platform.platform(),
            "authorizing": False,
            "method": (
                "Each matched cell executes exact submitted V3.1, exact submitted V4, "
                "and a 2x2 over only V4 funded-minimum semantics and same-turn SELL queue "
                "reordering. All V4 treatment archives preserve every member except "
                "frozen_selected.py; no arm is a V3.1 reconstruction. Evaluator, loader, "
                "prepared opponent adapter and candidate payload/adapter execution origins "
                "remain private for the entire panel; caller-visible copies are evidence only."
            ),
        }
        helper.write_json(output / "run.json", run)

        cells = []
        for opponent in opponents:
            for seed in seeds:
                for seat in seats:
                    offset = len(cells) % len(RUN_ARMS)
                    order = list(RUN_ARMS[offset:] + RUN_ARMS[:offset])
                    cell_id = f"{opponent}-seed{seed}-seat{seat}"
                    cell = {
                        "opponent": opponent,
                        "seed": seed,
                        "seat": seat,
                        "execution_order": order,
                        "games": {},
                        "metrics": {},
                        "deltas_vs_control": {},
                    }
                    for arm in order:
                        with tempfile.TemporaryDirectory(
                            prefix=f"{cell_id}-{arm}-", dir=private_games
                        ) as game_temp:
                            directory = Path(game_temp)
                            payload = directory / "payload"
                            helper.extract_members(arm_payloads[arm], payload)
                            adapter = directory / "adapter.py"
                            pack.write_adapter(adapter, payload / "main.py")
                            candidate = assert_private_execution_path(
                                adapter, private_root, output
                            )
                            rival = assert_private_execution_path(
                                runtime[opponent] / "adapter.py", private_root, output
                            )
                            specs = ([str(candidate), str(rival)] if seat == 0
                                     else [str(rival), str(candidate)])
                            engine, _ = evaluator.get_engine(engine_dir, loader)
                            game = evaluator.play(
                                engine, specs, engine_dir, loader, seed, seat,
                                args.rng_seed, args.action_timeout,
                                args.startup_timeout, args.game_timeout,
                            )
                        cell["games"][arm] = game
                        cell["metrics"][arm] = score_triplet(game, seat)
                        print(json.dumps({
                            "cell": cell_id,
                            "arm": arm,
                            "status": game.get("status"),
                            "scores": game.get("scores"),
                        }), flush=True)

                    control = cell["metrics"]["control"]
                    for arm in RUN_ARMS:
                        if arm == "control":
                            continue
                        cell["deltas_vs_control"][arm] = _delta(cell["metrics"][arm], control)
                    control_trace = cell["games"]["control"].get("trace_sha256")
                    cell["whole_game_trace_diff_vs_control"] = {
                        arm: (
                            None if not control_trace or not cell["games"][arm].get("trace_sha256")
                            else cell["games"][arm].get("trace_sha256") != control_trace
                        )
                        for arm in RUN_ARMS if arm != "control"
                    }
                    cell["status"] = (
                        "complete_cell"
                        if all(cell["metrics"][arm] is not None for arm in RUN_ARMS)
                        else "incomplete_cell"
                    )
                    helper.write_json(output / f"cell-{len(cells):03d}.json", cell)
                    cells.append(cell)

        summary = summarize(cells)
        final = {
            "schema": SCHEMA,
            "run": run,
            "cells": cells,
            "summary": summary,
            "authorizing": False,
            "verdict": (
                "CAUSAL_SCREEN_COMPLETE"
                if summary["complete_cells"] == summary["total_cells"]
                else "INCOMPLETE_NONAUTHORIZING"
            ),
        }
        helper.write_json(output / "RESULTS.json", final)
        print(json.dumps({"summary": summary, "verdict": final["verdict"]}, sort_keys=True))
        return 0 if final["verdict"] == "CAUSAL_SCREEN_COMPLETE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
