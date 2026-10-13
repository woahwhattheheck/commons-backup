#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Matched exact-V4 control vs WHEAT feed-stock-off games."""
from __future__ import annotations

import argparse
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

from feed_stock_ablation import (
    BASELINE_SHA256,
    RUNTIME_MEMBER,
    STOCK_MEMBER,
    action_trace_sha256,
    exact_v4_arms,
    extract_members,
    first_action_divergence,
    game_scores,
    git_blob_bytes,
    play_with_candidate_trace,
    sha256_bytes,
)

HELPER = "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
HELPER_GIT_BLOB = "719e3514d72bc7ea4c3e505836d16fcddae11019"
SCHEMA = "astra.v5.v4-feed-stock-ablation.v2"
ARMS = ("control", "feed_stock_off")
ENGINE_FILES = ("kaggriculture.py", "kaggriculture.json", "utils.py")


def capture_regular(path: Path) -> bytes:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"authority must be an ordinary file: {path}")
    return path.read_bytes()


def load_captured(raw: bytes, origin: Path, name: str):
    if type(raw) is not bytes:
        raise TypeError("captured source must be bytes")
    module = types.ModuleType(name)
    module.__file__ = str(origin)
    module.__package__ = ""
    sys.modules[name] = module
    code = compile(raw, str(origin), "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module


def capture_sha256(path: Path, expected: str) -> bytes:
    """Capture one ordinary harness file once and authenticate that buffer."""
    raw = capture_regular(path)
    actual = sha256_bytes(raw)
    if actual != expected:
        raise ValueError(f"snapshot member SHA256 mismatch; expected {expected}, got {actual}")
    return raw


def write_private_runtime_bytes(raw: bytes, path: Path, expected: str) -> Path:
    """Publish only already-authenticated bytes into private runtime custody."""
    if type(raw) is not bytes or sha256_bytes(raw) != expected:
        raise ValueError("private runtime bytes do not match authenticated SHA256")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    path.write_bytes(raw)
    if sha256_bytes(path.read_bytes()) != expected:
        raise ValueError("private runtime publication changed authenticated bytes")
    return path


def capture_private_engine(engine_dir: Path, evaluator, private_root: Path) -> tuple[Path, dict]:
    """Capture the exact official engine once and execute only its private copy."""
    engine_dir = Path(engine_dir)
    expected = getattr(evaluator, "ENGINE_BLOBS", None)
    if not isinstance(expected, dict) or set(expected) != set(ENGINE_FILES):
        raise ValueError("evaluator engine manifest changed")
    captured = {}
    receipt = {}
    for name in ENGINE_FILES:
        raw = capture_regular(engine_dir / name)
        actual_blob = git_blob_bytes(raw)
        if actual_blob != expected[name]:
            raise ValueError(
                f"Official source mismatch: {name}; expected blob {expected[name]}, got {actual_blob}"
            )
        captured[name] = raw
        receipt[name] = {
            "git_blob": actual_blob,
            "sha256": sha256_bytes(raw),
        }

    private_engine = Path(private_root) / "engine"
    private_engine.mkdir(parents=True, exist_ok=False)
    for name in ENGINE_FILES:
        write_private_runtime_bytes(
            captured[name], private_engine / name, receipt[name]["sha256"]
        )
    return private_engine, receipt


def write_json(path: Path, value) -> None:
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def summarize(cells: list[dict]) -> dict:
    result = {}
    for opponent in sorted({cell["opponent"] for cell in cells}):
        rows = [cell for cell in cells if cell["opponent"] == opponent]
        complete = [cell for cell in rows if cell["status"] == "complete_pair"]
        own = [cell["score_delta"]["own"] for cell in complete]
        rival = [cell["score_delta"]["rival"] for cell in complete]
        margin = [cell["score_delta"]["margin"] for cell in complete]
        result[opponent] = {
            "pairs": len(rows),
            "complete_pairs": len(complete),
            "engaged": sum(cell["engaged"] is True for cell in rows),
            "cold": sum(cell["engaged"] is False for cell in rows),
            "unknown_engagement": sum(cell["engaged"] is None for cell in rows),
            "mean_own_score_delta": statistics.mean(own) if own else None,
            "mean_rival_score_delta": statistics.mean(rival) if rival else None,
            "mean_margin_delta": statistics.mean(margin) if margin else None,
            "own_improved": sum(value > 0 for value in own),
            "own_unchanged": sum(value == 0 for value in own),
            "own_regressed": sum(value < 0 for value in own),
            "min_own_score_delta": min(own) if own else None,
            "max_own_score_delta": max(own) if own else None,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg-root", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Exact submitted V4 archive")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="2051966578,1209120226")
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
    if (not seeds or len(seeds) != len(set(seeds))
            or not seats or len(seats) != len(set(seats)) or not set(seats) <= {0, 1}
            or not opponents or len(opponents) != len(set(opponents))
            or not set(opponents) <= {"apex_v7", "arlene_v14"}):
        parser.error("Use distinct seeds, seats 0/1, opponents apex_v7/arlene_v14")
    if any(not math.isfinite(value) or value <= 0
           for value in (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("Timeouts must be finite and positive")

    root = args.kg_root.resolve(strict=True)
    engine_dir = args.engine_dir.resolve(strict=True)
    baseline_input = args.baseline
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output_parent = output.parent.resolve(strict=True)

    # Seal experiment inputs before any evidence output exists.
    baseline_raw = capture_regular(baseline_input)
    arms = exact_v4_arms(baseline_raw)
    helper_path = root / HELPER
    helper_raw = capture_regular(helper_path)
    if git_blob_bytes(helper_raw) != HELPER_GIT_BLOB:
        raise ValueError("joint-liquidity helper source drift")
    helper = load_captured(helper_raw, helper_path, "feed_stock_authenticated_helper")
    if getattr(helper, "BASELINE_SHA256", None) != BASELINE_SHA256:
        raise ValueError("helper baseline authority disagrees with this experiment")

    # Keep every executable artifact in private custody for the full panel.
    # Caller-visible paths receive evidence only and are never executed.
    with tempfile.TemporaryDirectory(
        prefix="feed-stock-private-runtime-", dir=output_parent
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
            loader_raw, private_root / "candidate-loader" / "evaluate.py", loader_expected
        )

        evaluator = load_captured(
            evaluator_raw, runtime_snapshot / evaluator_rel, "feed_stock_evaluator"
        )
        pack = load_captured(pack_raw, runtime_snapshot / pack_rel, "feed_stock_pack")
        bridge = load_captured(
            bridge_raw, runtime_snapshot / bridge_rel, "feed_stock_reference_bank"
        )

        # The caller-owned engine cache is ingestion-only. Capture and authenticate
        # the exact three pinned official sources before public output exists, then
        # execute only the private copy for the evaluator and all child workers.
        private_engine, engine_capture = capture_private_engine(
            engine_dir, evaluator, private_root
        )
        engine_hashes = evaluator.verify_sources(private_engine)
        expected_engine_hashes = {
            name: engine_capture[name]["sha256"] for name in ENGINE_FILES
        }
        if engine_hashes != expected_engine_hashes:
            raise ValueError("private engine verification disagrees with captured bytes")

        output.mkdir(parents=False, exist_ok=False)
        snapshot_root = output / ".harness-snapshot"
        shutil.copytree(runtime_snapshot, snapshot_root)

        runtime = {}
        opponent_receipts = {}
        expected_bridge = harness["repository_files"][bridge_rel]["sha256"]
        expected_registry = harness["repository_files"][
            helper.BANK + "/REFERENCE-POLICIES.json"
        ]["sha256"]
        for opponent in opponents:
            # reference_policies.prepare emits executable adapter/policy bytes.
            # Keep its destination private too; the public output tree must never
            # become an execution authority after authentication.
            runtime[opponent] = private_root / "opponents" / opponent
            receipt = bridge.prepare(opponent, runtime_snapshot, runtime[opponent])
            if (receipt.get("bridge_sha256") != expected_bridge
                    or receipt.get("source_registry_sha256") != expected_registry
                    or receipt.get("support_files") != harness["opponent_support_sha256"]):
                raise ValueError(f"opponent escaped authenticated harness: {opponent}")
            if Path(receipt.get("support_root", "")).resolve(strict=True) != runtime_snapshot:
                raise ValueError(f"opponent did not bind private runtime snapshot: {opponent}")
            opponent_receipts[opponent] = receipt

        identities = {
            arm: {
                "runtime_sha256": sha256_bytes(members[RUNTIME_MEMBER]),
                "runtime_git_blob": git_blob_bytes(members[RUNTIME_MEMBER]),
                "operating_stock_git_blob": git_blob_bytes(members[STOCK_MEMBER]),
                "member_count": len(members),
            }
            for arm, members in arms.items()
        }
        run = {
            "schema": SCHEMA,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "baseline_archive_sha256": sha256_bytes(baseline_raw),
            "baseline_capture": "single-read ordinary non-symlink file; no caller-path reopen",
            "changed_member_contract": [RUNTIME_MEMBER],
            "treatment": "Only TitanAgent._feed_stock_selected becomes identity; fertilizer operating-stock stays intact.",
            "arms": identities,
            "helper_git_blob": HELPER_GIT_BLOB,
            "helper_sha256": sha256_bytes(helper_raw),
            "helper_execution": "single-read authenticated captured bytes",
            "harness_execution": {
                "mode": "captured core modules + private authenticated runtime snapshot",
                "evaluator_sha256": sha256_bytes(evaluator_raw),
                "pack_sha256": sha256_bytes(pack_raw),
                "bridge_sha256": sha256_bytes(bridge_raw),
                "loader_sha256": sha256_bytes(loader_raw),
                "engine_runtime": "captured official source bytes in private engine cache only",
                "engine_files": engine_capture,
                "opponent_runtime": "private authenticated runtime only",
                "candidate_runtime": "private per-cell runtime only",
                "public_snapshot": ".harness-snapshot (evidence only; never executed)",
            },
            "harness": harness,
            "engine": engine_hashes,
            "opponent_receipts": opponent_receipts,
            "seeds": seeds,
            "seats": seats,
            "opponents": opponents,
            "rng_seed": args.rng_seed,
            "python": sys.version,
            "platform": platform.platform(),
            "limits": {
                "action_timeout": args.action_timeout,
                "startup_timeout": args.startup_timeout,
                "game_timeout": args.game_timeout,
            },
            "method": (
                "Exact submitted V4 control versus one-member titan_runtime.py source ablation. "
                "The baseline archive is captured once, SHA-authenticated, and parsed only from "
                "that captured buffer. The treatment is fail-closed on the exact V4 runtime Git "
                "blob and replaces only TitanAgent._feed_stock_selected with `return selected`; "
                "operating_stock.py and all other archive members remain byte-identical. The "
                "authenticated evaluator/packer/reference bridge execute from captured bytes; "
                "the candidate loader, exact official engine sources, generated opponent "
                "adapters/policies, candidate arm adapters/payloads, and opponent support root "
                "remain in private authenticated runtime custody for the full panel. The caller "
                "engine cache is ingestion-only and the public harness snapshot is evidence-only. "
                "Candidate returned actions are observed by a temporary in-process wrapper around "
                "the evaluator's Actor.act and the original method is restored after each game; "
                "agent/evaluator/engine bytes are not modified."
            ),
        }
        write_json(output / "run.json", run)

        cells: list[dict] = []
        for opponent in opponents:
            for seed in seeds:
                for seat in seats:
                    cell_id = f"{opponent}-s{seed}-p{seat}"
                    cell = {
                        "schema": SCHEMA,
                        "cell_id": cell_id,
                        "opponent": opponent,
                        "seed": seed,
                        "seat": seat,
                        "games": {},
                        "own_action_trace_sha256": {},
                    }
                    action_traces = {}
                    order = list(ARMS if len(cells) % 2 == 0 else reversed(ARMS))
                    cell["execution_order"] = order
                    for arm in order:
                        # Candidate payload/adapter are executable authority too;
                        # build and execute them under the same private runtime.
                        with tempfile.TemporaryDirectory(
                            prefix=f"{cell_id}-{arm}-", dir=private_root
                        ) as cell_temp:
                            directory = Path(cell_temp)
                            payload = directory / "payload"
                            extract_members(arms[arm], payload)
                            adapter = directory / "adapter.py"
                            pack.write_adapter(adapter, payload / "main.py")
                            candidate_spec = str(adapter)
                            rival_spec = str(runtime[opponent] / "adapter.py")
                            specs = ([candidate_spec, rival_spec] if seat == 0
                                     else [rival_spec, candidate_spec])
                            engine, _ = evaluator.get_engine(private_engine, loader)
                            game, actions = play_with_candidate_trace(
                                evaluator,
                                engine,
                                specs,
                                private_engine,
                                loader,
                                seed,
                                seat,
                                args.rng_seed,
                                args.action_timeout,
                                args.startup_timeout,
                                args.game_timeout,
                                candidate_spec=candidate_spec,
                            )
                            game["variant"] = arm
                            game["opponent"] = opponent
                            cell["games"][arm] = game
                            action_traces[arm] = actions
                            cell["own_action_trace_sha256"][arm] = action_trace_sha256(actions)
                            write_json(output / f"{cell_id}-{arm}.json", game)
                            print(json.dumps({
                                "cell_id": cell_id,
                                "variant": arm,
                                "status": game.get("status"),
                                "steps": game.get("steps"),
                                "scores": game.get("scores"),
                                "failure": game.get("failure"),
                            }), flush=True)

                    control_scores = game_scores(cell["games"]["control"], seat)
                    treatment_scores = game_scores(cell["games"]["feed_stock_off"], seat)
                    valid = control_scores is not None and treatment_scores is not None
                    cell["status"] = "complete_pair" if valid else "incomplete_pair"
                    if valid:
                        cell["scores"] = {
                            "control": control_scores,
                            "feed_stock_off": treatment_scores,
                        }
                        cell["score_delta"] = {
                            key: treatment_scores[key] - control_scores[key]
                            for key in ("own", "rival", "margin")
                        }
                        divergence = first_action_divergence(
                            action_traces["control"], action_traces["feed_stock_off"]
                        )
                        cell["engaged"] = divergence is not None
                        cell["first_action_divergence"] = divergence
                    else:
                        cell["scores"] = None
                        cell["score_delta"] = None
                        cell["engaged"] = None
                        cell["first_action_divergence"] = None
                    cell["action_calls"] = {arm: len(action_traces[arm]) for arm in ARMS}
                    write_json(output / f"{cell_id}.json", cell)
                    cells.append(cell)
                    write_json(output / "report.json", {
                        "run": run, "summary": summarize(cells), "cells": cells
                    })
                    print("PAIR " + json.dumps({
                        key: value for key, value in cell.items() if key != "games"
                    }, allow_nan=False), flush=True)

        summary = summarize(cells)
        write_json(output / "report.json", {"run": run, "summary": summary, "cells": cells})
        print("SUMMARY " + json.dumps(summary, allow_nan=False), flush=True)
        return int(any(cell["status"] != "complete_pair" for cell in cells))


if __name__ == "__main__":
    raise SystemExit(main())
