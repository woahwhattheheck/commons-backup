#!/usr/bin/env python3
"""Evidence-only exact V3.1 vs V4 archive bridge for TITAN V5.

This launcher does not port legacy policy code into the current runtime. It runs
the exact submitted archives from fresh temporary payloads, using the already
authenticated V5 harness snapshot and reference-opponent bank from #13388.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import statistics
import sys
import tarfile
import tempfile
import time

SCHEMA = "titan.v5.v31-v4-archive-bridge/v1"
EXPECTED_CALLBACKS = 719
VERSIONS = {
    "v31": {
        "source_commit": "a90d888f03987ef0b35cfd20ec3519c6144db08a",
        "submission": 56172377,
        "archive_sha256": "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361",
    },
    "v4": {
        "source_commit": "4af1113154e78c662780e6658cd920daac7902e3",
        "submission": 56182437,
        "archive_sha256": "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b",
    },
}
HELPER = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
HELPER_GIT_BLOB = "fbc5e320b8a2ee63af11dc9856c956a679823409"
BANK = "cloud-execution-lab/candidates/v4/research/reference-policy-bank"
EVALUATOR = "cloud-execution-lab/reference/evaluator/evaluate.py"
LOADER = "20260907-offline-agent/evaluate.py"
PACKER = "cloud-pack/pack.py"


def encoded(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_blob_id(path: Path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data
    ).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value) -> None:
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def archive_members(path: Path) -> dict[str, bytes]:
    """Read an ordinary-file-only submission archive without extracting it."""
    data: dict[str, bytes] = {}
    total = 0
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            rel = PurePosixPath(member.name)
            if (
                not member.name
                or "\\" in member.name
                or rel.is_absolute()
                or ".." in rel.parts
                or str(rel) != member.name.rstrip("/")
            ):
                raise ValueError(f"Invalid archive path: {member.name!r}")
            if member.isdir():
                continue
            if not member.isfile() or member.name in data:
                raise ValueError(
                    f"Non-file, linked, special, or duplicate member: {member.name}"
                )
            if member.size > 100 * 1024**2:
                raise ValueError(f"Oversized archive member: {member.name}")
            total += member.size
            if total > 250 * 1024**2:
                raise ValueError("Submission archive exceeds 250 MiB expanded")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            data[member.name] = stream.read()
    if "main.py" not in data:
        raise ValueError("Submission archive must expose root main.py")
    return data


def require_archive_identity(label: str, path: Path) -> str:
    if label not in VERSIONS:
        raise ValueError(f"Unknown exact version: {label}")
    actual = digest(path)
    expected = VERSIONS[label]["archive_sha256"]
    if actual != expected:
        raise ValueError(
            f"{label} archive identity mismatch; expected {expected}, got {actual}"
        )
    return actual


def extract_members(members: dict[str, bytes], directory: Path) -> None:
    directory.mkdir()
    for name, payload in members.items():
        path = directory.joinpath(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def actions_sha256(actions: list[dict]) -> str:
    return hashlib.sha256(encoded(actions)).hexdigest()


def action_sha256(action: dict) -> str:
    return hashlib.sha256(encoded(action)).hexdigest()


def first_divergence(left: list[dict], right: list[dict]):
    shared = min(len(left), len(right))
    for step in range(shared):
        if encoded(left[step]) != encoded(right[step]):
            return {
                "step": step,
                "kind": "action",
                "v31_action_sha256": action_sha256(left[step]),
                "v4_action_sha256": action_sha256(right[step]),
                "v31_action": left[step],
                "v4_action": right[step],
            }
    if len(left) != len(right):
        return {
            "step": shared,
            "kind": "length",
            "v31_action_count": len(left),
            "v4_action_count": len(right),
        }
    return None


def margin(game: dict, seat: int):
    if game.get("status") != "complete" or game.get("steps") != EXPECTED_CALLBACKS:
        return None
    return game["scores"][seat] - game["scores"][1 - seat]


def summarize(cells: list[dict]) -> dict:
    output = {}
    for opponent in sorted({cell["opponent"] for cell in cells}):
        rows = [cell for cell in cells if cell["opponent"] == opponent]
        values = [
            cell["margin_delta_v31_minus_v4"]
            for cell in rows
            if cell["margin_delta_v31_minus_v4"] is not None
        ]
        output[opponent] = {
            "pairs": len(rows),
            "complete_pairs": len(values),
            "v31_better": sum(value > 0 for value in values),
            "tied": sum(value == 0 for value in values),
            "v4_better": sum(value < 0 for value in values),
            "mean_margin_delta_v31_minus_v4": (
                statistics.mean(values) if values else None
            ),
            "min_margin_delta_v31_minus_v4": min(values) if values else None,
            "max_margin_delta_v31_minus_v4": max(values) if values else None,
        }
    return output


def play_traced(
    evaluator,
    engine,
    specs,
    cache: Path,
    loader: Path,
    seed: int,
    candidate_seat: int,
    *,
    rng_seed: int,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
):
    """Evaluator.play parity plus exact returned actions for the tested seat."""
    cfg = evaluator.Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    if not isinstance(cfg.episodeSteps, int) or cfg.episodeSteps < 2:
        raise ValueError("episodeSteps must be at least 2")
    cfg.seed = seed
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [
        evaluator.Struct(
            observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0
        )
        for _ in range(2)
    ]
    started, initial_cpu = time.perf_counter(), time.process_time()
    actors = []
    trace = hashlib.sha256()
    tested_actions: list[dict] = []
    result = {
        "seed": seed,
        "candidate_seat": candidate_seat,
        "status": "failed",
        "scores": None,
        "failure": None,
        "steps": 0,
        "episode_steps": cfg.episodeSteps,
        "daily_bank": [],
    }
    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise ValueError("Environment seed must not be exposed to agents")
        for seat, spec in enumerate(specs):
            actor = evaluator.Actor(
                spec,
                cache,
                loader,
                rng_seed + (seat != candidate_seat),
                startup_timeout,
            )
            actors.append(actor)
            if actor.ready.get("kind") != "ready":
                result["failure"] = {
                    "seat": seat,
                    "step": 0,
                    "phase": "startup",
                    **actor.ready,
                }
                return result

        for step in range(cfg.episodeSteps):
            actions = []
            for seat, actor in enumerate(actors):
                remaining = game_timeout - (time.perf_counter() - started)
                if remaining <= 0:
                    result["failure"] = {
                        "kind": "game_timeout",
                        "seat": None,
                        "step": step,
                    }
                    return result
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                response = actor.act(
                    state[seat].observation, cfg, min(action_timeout, remaining)
                )
                if response.get("kind") != "action":
                    result["failure"] = {
                        "seat": seat,
                        "step": step,
                        "phase": "action",
                        **response,
                    }
                    return result
                actions.append(response["action"])

            tested_actions.append(copy.deepcopy(actions[candidate_seat]))
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            result["steps"] += 1
            bank = [
                float(state[0].observation.farms[index]["money"])
                for index in range(2)
            ]
            trace.update(
                evaluator.encoded(
                    {"step": step, "actions": actions, "bank": bank}
                )
            )
            done = all(row.status == "DONE" for row in state)
            if (step + 1) % cfg.turnsPerDay == 0 or done:
                result["daily_bank"].append({"step": step, "bank": bank})
            if done:
                scores = [row.reward for row in state]
                if not all(
                    isinstance(score, (int, float)) and math.isfinite(score)
                    for score in scores
                ):
                    raise ValueError("Nonfinite or missing terminal score")
                result.update(status="complete", scores=scores)
                env.done = True
                return result

        result["failure"] = {
            "kind": "incomplete",
            "seat": None,
            "step": result["steps"],
        }
    except Exception as exc:
        result["failure"] = {
            "kind": "engine_error",
            "seat": None,
            "step": result["steps"],
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }
    finally:
        for actor in actors:
            actor.close()
        result["actors"] = [actor.report() for actor in actors]
        result["wall_seconds"] = time.perf_counter() - started
        result["driver_cpu_seconds"] = time.process_time() - initial_cpu
        result["bank_snapshot"] = [
            float(
                state[0]
                .observation.get("farms", [{"money": 0}] * 2)[index]["money"]
            )
            for index in range(2)
        ]
        trace.update(evaluator.encoded([row.observation for row in state]))
        result["trace_sha256"] = trace.hexdigest()
        result["tested_seat_actions"] = tested_actions
        result["tested_action_count"] = len(tested_actions)
        result["tested_action_sha256"] = actions_sha256(tested_actions)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kg-root", type=Path, required=True,
        help="Existing revenue/kaggriculture directory"
    )
    parser.add_argument(
        "--engine-dir", type=Path, required=True,
        help="Existing exact official-engine cache"
    )
    parser.add_argument("--v31", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="2051966578")
    parser.add_argument("--opponents", default="arlene_v14")
    parser.add_argument("--seats", default="0,1")
    parser.add_argument("--rng-seed", type=int, default=20260912)
    parser.add_argument("--action-timeout", type=float, default=1.25)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--game-timeout", type=float, default=900.0)
    args = parser.parse_args()

    if sys.platform != "linux":
        parser.error("Run bridge games on Linux; no Windows deadline shim is used")
    seeds = [int(value) for value in args.seeds.split(",")]
    seats = [int(value) for value in args.seats.split(",")]
    opponents = args.opponents.split(",")
    if (
        not seeds
        or len(seeds) != len(set(seeds))
        or not seats
        or len(seats) != len(set(seats))
        or not set(seats) <= {0, 1}
        or not opponents
        or len(opponents) != len(set(opponents))
        or not set(opponents) <= {"apex_v7", "arlene_v14"}
    ):
        parser.error(
            "Use distinct seeds, seats 0/1, and authenticated apex_v7/arlene_v14"
        )
    if any(
        not math.isfinite(value) or value <= 0
        for value in (
            args.action_timeout,
            args.startup_timeout,
            args.game_timeout,
        )
    ):
        parser.error("Timeouts must be finite and positive")

    args.kg_root = args.kg_root.resolve(strict=True)
    args.engine_dir = args.engine_dir.resolve(strict=True)
    archives = {
        "v31": args.v31.resolve(strict=True),
        "v4": args.v4.resolve(strict=True),
    }
    archive_bytes = {}
    for label, path in archives.items():
        require_archive_identity(label, path)
        archive_bytes[label] = archive_members(path)

    helper_path = (args.kg_root / HELPER).resolve(strict=True)
    if git_blob_id(helper_path) != HELPER_GIT_BLOB:
        raise ValueError(
            "Authenticated V5 snapshot helper drifted; rebind deliberately"
        )
    helper = load(helper_path, "titan_v5_archive_bridge_snapshot_helper")

    args.output = args.output.resolve()
    if args.output.exists():
        raise FileExistsError(args.output)
    output_parent = args.output.parent.resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="v31-v4-harness-snapshot-", dir=output_parent
    ) as temp:
        staged_snapshot = Path(temp) / "kg"
        harness = helper.snapshot_harness(
            args.kg_root, staged_snapshot, opponents
        )
        args.output.mkdir(parents=False, exist_ok=False)
        snapshot_root = args.output / ".harness-snapshot"
        os.replace(staged_snapshot, snapshot_root)

    evaluator_path = snapshot_root / EVALUATOR
    loader_path = snapshot_root / LOADER
    evaluator = load(evaluator_path, "titan_v31_v4_existing_evaluator")
    pack = load(snapshot_root / PACKER, "titan_v31_v4_existing_pack")
    bridge = load(
        snapshot_root / BANK / "reference_policies.py",
        "titan_v31_v4_existing_reference_bank",
    )
    engine_hashes = evaluator.verify_sources(args.engine_dir)

    runtime = {}
    opponent_receipts = {}
    expected_bridge = harness["repository_files"][
        BANK + "/reference_policies.py"
    ]["sha256"]
    expected_registry = harness["repository_files"][
        BANK + "/REFERENCE-POLICIES.json"
    ]["sha256"]
    for opponent in opponents:
        runtime[opponent] = args.output / "opponents" / opponent
        receipt = bridge.prepare(opponent, snapshot_root, runtime[opponent])
        if (
            receipt.get("bridge_sha256") != expected_bridge
            or receipt.get("source_registry_sha256") != expected_registry
            or receipt.get("support_files")
            != harness["opponent_support_sha256"]
        ):
            raise ValueError(
                f"Opponent preparation escaped authenticated snapshot: {opponent}"
            )
        support_root = Path(receipt.get("support_root", "")).resolve(strict=True)
        if support_root != snapshot_root.resolve(strict=True):
            raise ValueError(
                f"Opponent preparation did not bind snapshot root: {opponent}"
            )
        opponent_receipts[opponent] = receipt

    metadata = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "versions": {
            label: {
                **VERSIONS[label],
                "archive_path_name": archives[label].name,
                "member_count": len(archive_bytes[label]),
            }
            for label in ("v31", "v4")
        },
        "engine_ref": evaluator.ENGINE_REF,
        "engine_sha256": engine_hashes,
        "snapshot_helper_git_blob": HELPER_GIT_BLOB,
        "snapshot_helper_sha256": digest(helper_path),
        "harness": harness,
        "evaluator_sha256": digest(evaluator_path),
        "loader_sha256": digest(loader_path),
        "launcher_sha256": digest(Path(__file__)),
        "python": sys.version,
        "platform": platform.platform(),
        "limits": {
            "action_rpc_seconds": args.action_timeout,
            "startup_seconds": args.startup_timeout,
            "game_seconds": args.game_timeout,
            "remaining_overage_time": 0,
        },
        "seeds": seeds,
        "seats": seats,
        "opponents": opponents,
        "agent_rng_seed": args.rng_seed,
        "opponent_receipts": opponent_receipts,
        "method": (
            "Evidence-only exact submitted archive comparison. V3.1 and V4 are "
            "SHA-allowlisted, freshly extracted per game, and never copied into "
            "the production runtime. The mutable kg tree is used only to acquire "
            "the #13388 declared harness/policy closure; all execution uses the "
            "authenticated snapshot. The official evaluator Actor/process model "
            "and interpreter are reused; this bridge adds tested-seat returned-"
            "action capture only. This is not hosted Kaggle timing."
        ),
    }
    write_json(args.output / "run.json", metadata)

    cells = []
    for opponent in opponents:
        for seed in seeds:
            for seat in seats:
                cell_id = f"{opponent}-s{seed}-p{seat}"
                order = (
                    ["v31", "v4"]
                    if len(cells) % 2 == 0
                    else ["v4", "v31"]
                )
                cell = {
                    "schema": SCHEMA,
                    "cell_id": cell_id,
                    "opponent": opponent,
                    "seed": seed,
                    "seat": seat,
                    "execution_order": order,
                    "games": {},
                }
                for label in order:
                    with tempfile.TemporaryDirectory(
                        prefix=f"{cell_id}-{label}-", dir=args.output
                    ) as temp:
                        directory = Path(temp)
                        payload = directory / "payload"
                        extract_members(archive_bytes[label], payload)
                        adapter = directory / "adapter.py"
                        pack.write_adapter(adapter, payload / "main.py")
                        rival = str(runtime[opponent] / "adapter.py")
                        specs = (
                            [str(adapter), rival]
                            if seat == 0
                            else [rival, str(adapter)]
                        )
                        engine, _ = evaluator.get_engine(
                            args.engine_dir, loader_path
                        )
                        game = play_traced(
                            evaluator,
                            engine,
                            specs,
                            args.engine_dir,
                            loader_path,
                            seed,
                            seat,
                            rng_seed=args.rng_seed,
                            action_timeout=args.action_timeout,
                            startup_timeout=args.startup_timeout,
                            game_timeout=args.game_timeout,
                        )
                        game["version"] = label
                        game["opponent"] = opponent
                        game["archive_sha256"] = VERSIONS[label][
                            "archive_sha256"
                        ]
                        cell["games"][label] = game
                        write_json(
                            args.output / f"{cell_id}-{label}.json", game
                        )
                        print(
                            json.dumps(
                                {
                                    "cell_id": cell_id,
                                    "version": label,
                                    "status": game["status"],
                                    "steps": game["steps"],
                                    "scores": game["scores"],
                                    "failure": game["failure"],
                                    "tested_action_count": game[
                                        "tested_action_count"
                                    ],
                                    "tested_action_sha256": game[
                                        "tested_action_sha256"
                                    ],
                                    "wall_seconds": game["wall_seconds"],
                                }
                            ),
                            flush=True,
                        )

                v31_margin = margin(cell["games"]["v31"], seat)
                v4_margin = margin(cell["games"]["v4"], seat)
                complete = v31_margin is not None and v4_margin is not None
                cell["status"] = (
                    "complete_pair" if complete else "incomplete_pair"
                )
                cell["v31_margin"] = v31_margin
                cell["v4_margin"] = v4_margin
                cell["margin_delta_v31_minus_v4"] = (
                    v31_margin - v4_margin if complete else None
                )
                cell["first_returned_action_divergence"] = first_divergence(
                    cell["games"]["v31"]["tested_seat_actions"],
                    cell["games"]["v4"]["tested_seat_actions"],
                )
                write_json(args.output / f"{cell_id}.json", cell)
                cells.append(cell)
                write_json(
                    args.output / "report.json",
                    {
                        "run": metadata,
                        "summary": summarize(cells),
                        "cells": cells,
                    },
                )
                print(
                    "PAIR "
                    + json.dumps(
                        {
                            key: value
                            for key, value in cell.items()
                            if key != "games"
                        }
                    ),
                    flush=True,
                )

    print("SUMMARY " + json.dumps(summarize(cells)), flush=True)
    invalid = any(
        cell["status"] != "complete_pair"
        or cell["games"]["v31"]["tested_action_count"]
        != EXPECTED_CALLBACKS
        or cell["games"]["v4"]["tested_action_count"]
        != EXPECTED_CALLBACKS
        for cell in cells
    )
    return int(invalid)


if __name__ == "__main__":
    raise SystemExit(main())
