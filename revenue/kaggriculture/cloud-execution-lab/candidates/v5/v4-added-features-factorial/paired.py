#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Factorial self-ablation of four selected production features in submitted V4.

Every experimental arm is derived from the exact submitted V4 archive and may change
only TITAN-CONFIG.json. Runtime, policy, engine, opponent, and evaluator bytes are
otherwise shared and authenticated. This experiment does not reconstruct V3.1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
import time
import types

BASELINE_SHA256 = "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b"
V4_CONFIG_SHA256 = "ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af"
V4_SOURCE = "4af1113154e78c662780e6658cd920daac7902e3"
HELPER_GIT_BLOB = "719e3514d72bc7ea4c3e505836d16fcddae11019"
HELPER = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
FEATURES = ("idle_fertilizer", "crop_release", "early_capital", "town_procurement")
SCHEMA = "astra.v5.v4-added-features-factorial.v3"

SCREEN_ARMS = (
    "v4",
    "all_four_off",
    "off_idle_fertilizer",
    "off_crop_release",
    "off_early_capital",
    "off_town_procurement",
)


def load_captured(raw: bytes, origin: Path, name: str):
    """Execute exactly the bytes already authenticated by the caller.

    This deliberately never reopens ``origin``. A moving checkout therefore cannot
    pass a source hash check and then substitute different executable bytes.
    """
    if type(raw) is not bytes:
        raise TypeError("captured module source must be bytes")
    module = types.ModuleType(name)
    module.__file__ = str(origin)
    module.__package__ = ""
    sys.modules[name] = module
    code = compile(raw, str(origin), "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def capture_authenticated(path: Path, expected_git_blob: str) -> bytes:
    """Single-read Git-blob authentication for executable helper source."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Authenticated helper must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = git_blob_bytes(raw)
    if actual != expected_git_blob:
        raise ValueError(
            f"Authenticated helper moved; expected Git blob {expected_git_blob}, got {actual}"
        )
    return raw


def capture_sha256(path: Path, expected_sha256: str, label: str = "Snapshot member") -> bytes:
    """Capture one ordinary file once and authenticate exactly those bytes."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = sha256_bytes(raw)
    if actual != expected_sha256:
        raise ValueError(f"{label} SHA256 mismatch; expected {expected_sha256}, got {actual}")
    return raw


def write_private_runtime_bytes(raw: bytes, path: Path, expected_sha256: str) -> Path:
    """Publish already-authenticated bytes only into a private runtime location."""
    if type(raw) is not bytes or sha256_bytes(raw) != expected_sha256:
        raise ValueError("Private runtime bytes do not match authenticated SHA256")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    path.write_bytes(raw)
    if sha256_bytes(path.read_bytes()) != expected_sha256:
        raise ValueError("Private runtime publication changed authenticated bytes")
    return path


def archive_members_captured(helper, raw: bytes) -> dict[str, bytes]:
    """Parse only the exact baseline bytes authenticated by the caller."""
    if type(raw) is not bytes:
        raise TypeError("captured archive must be bytes")
    with tempfile.TemporaryDirectory(prefix="v4-factorial-baseline-") as temp:
        snapshot = Path(temp) / "submitted-v4.tar.gz"
        with snapshot.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if snapshot.is_symlink() or not snapshot.is_file():
            raise ValueError("Private baseline snapshot is not an ordinary file")
        return helper.archive_members(snapshot)


def exact_v4_config(raw: bytes) -> dict:
    if sha256_bytes(raw) != V4_CONFIG_SHA256:
        raise ValueError("TITAN-CONFIG.json is not the exact submitted V4 config")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("V4 config must be a JSON object")
    for feature in FEATURES:
        if type(value.get(feature)) is not bool or value[feature] is not True:
            raise ValueError(f"Submitted V4 must enable {feature}=true")
    return value


def canonical_arm(name: str) -> str:
    """Map deprecated input spellings to the canonical experiment identity."""
    return "all_four_off" if name == "v31_flags" else name


def feature_vector(name: str) -> dict[str, bool]:
    name = canonical_arm(name)
    if name == "v4":
        return {feature: True for feature in FEATURES}
    if name == "all_four_off":
        return {feature: False for feature in FEATURES}
    if name.startswith("off_"):
        target = name[4:]
        if target not in FEATURES:
            raise ValueError(f"Unknown feature-off arm: {name}")
        return {feature: feature != target for feature in FEATURES}
    if name.startswith("mask_") and len(name) == len("mask_") + len(FEATURES):
        bits = name[len("mask_"):]
        if any(bit not in "01" for bit in bits):
            raise ValueError(f"Invalid mask arm: {name}")
        return {feature: bit == "1" for feature, bit in zip(FEATURES, bits)}
    raise ValueError(f"Unknown arm: {name}")


def design_arms(design: str) -> list[str]:
    if design == "screen":
        return list(SCREEN_ARMS)
    if design == "full":
        return [f"mask_{value:04b}" for value in range(16)]
    raise ValueError(f"Unknown design: {design}")


def arm_members(baseline: dict[str, bytes], name: str) -> dict[str, bytes]:
    if "TITAN-CONFIG.json" not in baseline:
        raise ValueError("V4 archive is missing TITAN-CONFIG.json")
    original = baseline["TITAN-CONFIG.json"]
    config = exact_v4_config(original)
    vector = feature_vector(name)
    if all(vector[feature] is True for feature in FEATURES):
        return dict(baseline)
    for feature in FEATURES:
        config[feature] = vector[feature]
    changed = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    candidate = dict(baseline)
    candidate["TITAN-CONFIG.json"] = changed
    if set(candidate) != set(baseline):
        raise AssertionError("arm changed archive membership")
    diffs = [path for path in baseline if baseline[path] != candidate[path]]
    if diffs != ["TITAN-CONFIG.json"]:
        raise AssertionError(f"arm changed unexpected members: {diffs}")
    reparsed = json.loads(changed)
    for key, value in json.loads(original).items():
        if key not in FEATURES and reparsed.get(key) != value:
            raise AssertionError(f"arm changed non-factor key: {key}")
    return candidate


def arm_identity(members: dict[str, bytes]) -> dict:
    raw = members["TITAN-CONFIG.json"]
    config = json.loads(raw)
    return {
        "config_sha256": sha256_bytes(raw),
        "feature_vector": {feature: bool(config[feature]) for feature in FEATURES},
    }


def margin(game: dict, seat: int):
    if game.get("status") != "complete" or game.get("steps") != 719:
        return None
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        return None
    return scores[seat] - scores[1 - seat]


def summarize(cells: list[dict], arms: list[str]) -> dict:
    result = {}
    for arm in arms:
        per_opponent = {}
        for opponent in sorted({cell["opponent"] for cell in cells}):
            rows = [cell for cell in cells if cell["opponent"] == opponent]
            values = [
                cell["margin_delta"].get(arm)
                for cell in rows
                if cell["margin_delta"].get(arm) is not None
            ]
            per_opponent[opponent] = {
                "pairs": len(rows),
                "complete_pairs": len(values),
                "improved": sum(value > 0 for value in values),
                "unchanged": sum(value == 0 for value in values),
                "regressed": sum(value < 0 for value in values),
                "mean_margin_delta": statistics.mean(values) if values else None,
                "min_margin_delta": min(values) if values else None,
                "max_margin_delta": max(values) if values else None,
            }
        result[arm] = {
            "baseline_equivalent": arm in {"v4", "mask_1111"},
            "features": feature_vector(arm),
            "opponents": per_opponent,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Exact submitted V4 archive")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=("screen", "full"), default="screen")
    parser.add_argument("--arms", help="Comma-separated explicit arm names; overrides --design")
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
    seeds = [int(value) for value in args.seeds.split(",") if value]
    seats = [int(value) for value in args.seats.split(",") if value]
    opponents = [value for value in args.opponents.split(",") if value]
    raw_arms = ([value for value in args.arms.split(",") if value]
                if args.arms else design_arms(args.design))
    arms = [canonical_arm(value) for value in raw_arms]
    if (not seeds or len(seeds) != len(set(seeds))
            or not seats or len(seats) != len(set(seats)) or not set(seats) <= {0, 1}
            or not opponents or len(opponents) != len(set(opponents))
            or not set(opponents) <= {"apex_v7", "arlene_v14"}
            or not arms or len(arms) != len(set(arms))):
        parser.error("Use distinct seeds/arms, seats 0/1, opponents apex_v7/arlene_v14")
    for arm in arms:
        feature_vector(arm)
    if not any(all(feature_vector(arm)[f] for f in FEATURES) for arm in arms):
        parser.error("Arm set must include a V4-equivalent all-true baseline")
    if any(not math.isfinite(value) or value <= 0
           for value in (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("Timeouts must be finite and positive")

    root = args.kg_root.resolve(strict=True)
    engine_dir = args.engine_dir.resolve(strict=True)
    baseline_path = Path(args.baseline)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    baseline_raw = capture_sha256(
        baseline_path, BASELINE_SHA256, "Baseline archive"
    )

    helper_path = root / HELPER
    helper_raw = capture_authenticated(helper_path, HELPER_GIT_BLOB)
    helper = load_captured(helper_raw, helper_path, "v4_factorial_authenticated_helper")
    if helper.BASELINE_SHA256 != BASELINE_SHA256:
        raise ValueError("Helper baseline authority disagrees with this harness")

    baseline = archive_members_captured(helper, baseline_raw)
    exact_v4_config(baseline["TITAN-CONFIG.json"])
    arm_payloads = {arm: arm_members(baseline, arm) for arm in arms}
    arm_ids = {arm: arm_identity(payload) for arm, payload in arm_payloads.items()}
    baseline_arm = next(
        arm for arm in arms if all(arm_ids[arm]["feature_vector"][f] for f in FEATURES)
    )

    output_parent = output.parent.resolve(strict=True)

    # Keep authenticated execution authorities private for the entire panel.
    # The caller-visible snapshot is a copy for evidence only and is never imported.
    with tempfile.TemporaryDirectory(
        prefix="v4-factorial-private-runtime-", dir=output_parent
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
            "Evaluator",
        )
        pack_raw = capture_sha256(
            runtime_snapshot / pack_rel,
            harness["repository_files"][pack_rel]["sha256"],
            "Packer",
        )
        bridge_raw = capture_sha256(
            runtime_snapshot / bridge_rel,
            harness["repository_files"][bridge_rel]["sha256"],
            "Reference-policy bridge",
        )
        loader_expected = harness["repository_files"][loader_rel]["sha256"]
        loader_raw = capture_sha256(
            runtime_snapshot / loader_rel, loader_expected, "Candidate loader"
        )
        loader = write_private_runtime_bytes(
            loader_raw, private_root / "candidate-loader" / "evaluate.py", loader_expected
        )

        evaluator = load_captured(
            evaluator_raw, runtime_snapshot / evaluator_rel, "v4_factorial_evaluator"
        )
        pack = load_captured(
            pack_raw, runtime_snapshot / pack_rel, "v4_factorial_pack"
        )
        bridge = load_captured(
            bridge_raw, runtime_snapshot / bridge_rel, "v4_factorial_reference_bank"
        )
        engine_hashes = evaluator.verify_sources(engine_dir)

        output.mkdir(parents=False, exist_ok=False)
        snapshot_root = output / ".harness-snapshot"
        shutil.copytree(runtime_snapshot, snapshot_root)

        runtime = {}
        opponent_receipts = {}
        expected_bridge = harness["repository_files"][
            helper.BANK + "/reference_policies.py"]["sha256"]
        expected_registry = harness["repository_files"][
            helper.BANK + "/REFERENCE-POLICIES.json"]["sha256"]
        for opponent in opponents:
            runtime[opponent] = output / "opponents" / opponent
            receipt = bridge.prepare(opponent, runtime_snapshot, runtime[opponent])
            if (receipt.get("bridge_sha256") != expected_bridge
                    or receipt.get("source_registry_sha256") != expected_registry
                    or receipt.get("support_files") != harness["opponent_support_sha256"]):
                raise ValueError(f"Opponent escaped authenticated harness: {opponent}")
            if Path(receipt.get("support_root", "")).resolve(strict=True) != runtime_snapshot:
                raise ValueError(
                    f"Opponent did not bind private runtime snapshot: {opponent}"
                )
            opponent_receipts[opponent] = receipt

        run = {
            "schema": SCHEMA,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "v4_source": V4_SOURCE,
            "baseline_archive_sha256": BASELINE_SHA256,
            "baseline_config_sha256": V4_CONFIG_SHA256,
            "baseline_execution": (
                "single-read SHA256-authenticated captured bytes via private snapshot"
            ),
            "changed_member_contract": ["TITAN-CONFIG.json"],
            "factor_features": list(FEATURES),
            "design": args.design,
            "arms": arm_ids,
            "baseline_arm": baseline_arm,
            "seeds": seeds,
            "seats": seats,
            "opponents": opponents,
            "engine": engine_hashes,
            "helper_git_blob": HELPER_GIT_BLOB,
            "helper_sha256": sha256_bytes(helper_raw),
            "helper_execution": "single-read authenticated captured bytes",
            "harness_execution": {
                "mode": "captured core modules + private authenticated runtime snapshot",
                "evaluator_sha256": sha256_bytes(evaluator_raw),
                "pack_sha256": sha256_bytes(pack_raw),
                "bridge_sha256": sha256_bytes(bridge_raw),
                "loader_sha256": sha256_bytes(loader_raw),
                "public_snapshot": ".harness-snapshot (evidence only; never executed)",
            },
            "harness": harness,
            "opponent_receipts": opponent_receipts,
            "python": sys.version,
            "platform": platform.platform(),
            "method": (
                "Every arm is extracted from one single-read SHA256-authenticated capture of "
                "the exact submitted V4 archive, parsed through a private snapshot. Only "
                "TITAN-CONFIG.json may differ, and only four selected submitted-V4 boolean "
                "mechanisms may change. all_four_off is a V4 self-ablation and is NOT a "
                "behavioral reconstruction or approximation of submitted V3.1; exact V3.1 "
                "comparison belongs to archive-version-bridge/gauntlet and R04 recovery evidence. "
                "The shared helper executes from its single authenticated captured byte snapshot. "
                "Evaluator, packer and reference bank execute from captured authenticated bytes; "
                "the candidate loader executes from a separate private runtime-only copy of its "
                "captured authenticated bytes; opponent support binds the private authenticated "
                "snapshot. The public .harness-snapshot is evidence only and never execution "
                "authority. Each arm gets a fresh persistent agent process and private payload; "
                "arm order rotates by cell."
            ),
        }
        helper.write_json(output / "run.json", run)

        cells = []
        for opponent in opponents:
            for seed in seeds:
                for seat in seats:
                    rotate = len(cells) % len(arms)
                    order = arms[rotate:] + arms[:rotate]
                    cell_id = f"{opponent}-s{seed}-p{seat}"
                    cell = {
                        "schema": SCHEMA,
                        "cell_id": cell_id,
                        "opponent": opponent,
                        "seed": seed,
                        "seat": seat,
                        "execution_order": order,
                        "games": {},
                        "margins": {},
                        "margin_delta": {},
                    }
                    for arm in order:
                        with tempfile.TemporaryDirectory(
                            prefix=f"{cell_id}-{arm}-", dir=output
                        ) as arm_temp:
                            directory = Path(arm_temp)
                            payload = directory / "payload"
                            helper.extract_members(arm_payloads[arm], payload)
                            adapter = directory / "adapter.py"
                            pack.write_adapter(adapter, payload / "main.py")
                            rival = str(runtime[opponent] / "adapter.py")
                            specs = (
                                [str(adapter), rival] if seat == 0
                                else [rival, str(adapter)]
                            )
                            engine, _ = evaluator.get_engine(engine_dir, loader)
                            game = evaluator.play(
                                engine, specs, engine_dir, loader, seed, seat,
                                args.rng_seed, args.action_timeout,
                                args.startup_timeout, args.game_timeout,
                            )
                        game["arm"] = arm
                        game["arm_config_sha256"] = arm_ids[arm]["config_sha256"]
                        game["opponent"] = opponent
                        cell["games"][arm] = game
                        cell["margins"][arm] = margin(game, seat)
                        helper.write_json(output / f"{cell_id}-{arm}.json", game)
                        print(json.dumps({
                            "cell_id": cell_id,
                            "arm": arm,
                            "status": game.get("status"),
                            "steps": game.get("steps"),
                            "scores": game.get("scores"),
                            "failure": game.get("failure"),
                        }), flush=True)

                    baseline_margin = cell["margins"][baseline_arm]
                    for arm in arms:
                        value = cell["margins"][arm]
                        cell["margin_delta"][arm] = (
                            value - baseline_margin
                            if value is not None and baseline_margin is not None else None
                        )
                    complete = all(cell["margins"][arm] is not None for arm in arms)
                    cell["status"] = (
                        "complete_cell" if complete else "incomplete_cell"
                    )
                    helper.write_json(output / f"{cell_id}.json", cell)
                    cells.append(cell)
                    helper.write_json(output / "report.json", {
                        "run": run,
                        "summary": summarize(cells, arms),
                        "cells": cells,
                    })
                    print("CELL " + json.dumps({
                        key: value for key, value in cell.items() if key != "games"
                    }), flush=True)

        summary = summarize(cells, arms)
        print("SUMMARY " + json.dumps(summary), flush=True)
        return int(any(cell["status"] != "complete_cell" for cell in cells))


if __name__ == "__main__":
    raise SystemExit(main())
