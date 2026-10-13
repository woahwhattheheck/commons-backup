#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fresh matched current-V5 control vs selective-carrot cap4/cap12 games."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import statistics
import sys
import tarfile
import tempfile
import types


ARMS = ("control", "cap4", "cap12")
EXPECTED_SHARED_HELPER_GIT_BLOB = "719e3514d72bc7ea4c3e505836d16fcddae11019"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_authenticated_shared_helper(path: Path):
    """Authenticate the shared harness helper, then execute only captured bytes.

    The caller-selected checkout is never imported directly. A stable but modified
    helper therefore fails before any benchmark output directory is created.
    """
    if path.is_symlink() or not path.is_file():
        raise ValueError("shared harness helper must be a regular file")
    raw = path.read_bytes()
    actual_blob = git_blob_bytes(raw)
    if actual_blob != EXPECTED_SHARED_HELPER_GIT_BLOB:
        raise ValueError(
            "shared harness helper Git blob drift: "
            f"expected {EXPECTED_SHARED_HELPER_GIT_BLOB}, got {actual_blob}"
        )
    authority = {
        "git_blob": EXPECTED_SHARED_HELPER_GIT_BLOB,
        "sha256": sha256_bytes(raw),
    }
    name = "carrot_current_bench_helpers_pinned"
    module = types.ModuleType(name)
    module.__file__ = f"<authenticated:{path.name}@{EXPECTED_SHARED_HELPER_GIT_BLOB}>"
    module.__package__ = ""
    sys.modules[name] = module
    code = compile(raw, module.__file__, "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module, authority


def read_json_bytes(data: bytes):
    return json.loads(data.decode("utf-8"))


def archive_members_bytes(raw: bytes) -> dict[str, bytes]:
    """Parse one immutable canonical package snapshot without reopening disk."""
    data = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        for member in archive:
            rel = PurePosixPath(member.name)
            if (
                not member.name
                or "\\" in member.name
                or rel.is_absolute()
                or ".." in rel.parts
                or str(rel) != member.name.rstrip("/")
            ):
                raise ValueError(f"Invalid archive path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile() or member.name in data:
                raise ValueError(f"Non-file or duplicate member: {member.name}")
            if member.size > 100 * 1024**2:
                raise ValueError(f"Oversized member: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            with stream:
                data[member.name] = stream.read()
    if "main.py" not in data or "frozen_selected.py" not in data:
        raise ValueError("Expected canonical V5 flat archive layout")
    return data


def members(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)).replace("\\", "/"): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


def mean(values):
    rows = [value for value in values if value is not None]
    return None if not rows else statistics.fmean(rows)


def first_action_divergence(control, treatment):
    """Return the first exact returned-action difference, including stream end."""
    total = max(len(control), len(treatment))
    for step in range(total):
        left = control[step] if step < len(control) else {"_stream_end": True}
        right = treatment[step] if step < len(treatment) else {"_stream_end": True}
        if left != right:
            return {"step": step, "control": left, "treatment": right}
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kg-root", type=Path, required=True)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--seeds",
        required=True,
        help="comma-separated fresh seeds reserved for this lane",
    )
    p.add_argument("--seats", default="0,1")
    p.add_argument("--opponents", default="apex_v7,arlene_v14")
    args = p.parse_args(argv)

    if sys.platform != "linux":
        p.error("Use a Linux VM for this process-isolated benchmark")

    seeds = [int(value) for value in args.seeds.split(",") if value]
    seats = [int(value) for value in args.seats.split(",") if value]
    opponents = [value for value in args.opponents.split(",") if value]
    if not seeds or len(seeds) != len(set(seeds)):
        p.error("at least one distinct fresh seed is required")
    if not seats or len(seats) != len(set(seats)) or not set(seats) <= {0, 1}:
        p.error("use distinct supported seats 0 and/or 1")
    if (
        not opponents
        or len(opponents) != len(set(opponents))
        or not set(opponents) <= {"apex_v7", "arlene_v14"}
    ):
        p.error("use distinct supported opponents apex_v7 and/or arlene_v14")

    root = args.kg_root.resolve(strict=True)
    args.engine_dir = args.engine_dir.resolve(strict=True)
    args.output = args.output.resolve()
    output_parent = args.output.parent.resolve(strict=True)
    lab = root / "cloud-execution-lab"
    here = Path(__file__).resolve().parent
    helper_path = (
        root / "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
    )
    builder_path = here / "build_current.py"
    launcher_path = Path(__file__).resolve()

    # The shared helper is an external trust root. Authenticate its Git identity
    # before importing anything from caller-selected --kg-root, then execute only
    # the captured authenticated bytes. This happens before args.output exists.
    h, helper_authority = load_authenticated_shared_helper(helper_path)
    helper_sha256 = helper_authority["sha256"]

    # Bind the local branch sources before importing/executing them. Unlike the
    # shared helper, these are PR-owned files whose exact SHA256 is recorded here;
    # their deeper runtime/source authorities are enforced by their own contracts.
    builder_sha256 = sha256_bytes(builder_path.read_bytes())
    launcher_sha256 = sha256_bytes(launcher_path.read_bytes())
    builder = load(builder_path, "carrot_current_builder")
    if sha256_bytes(builder_path.read_bytes()) != builder_sha256:
        raise ValueError("candidate builder moved during import")
    if sha256_bytes(launcher_path.read_bytes()) != launcher_sha256:
        raise ValueError("launcher moved during startup")

    current_path = lab / "runtime/integrated-selected/CURRENT-ARCHIVE.json"
    current_manifest_bytes = current_path.read_bytes()
    current_manifest_sha256 = sha256_bytes(current_manifest_bytes)
    current = read_json_bytes(current_manifest_bytes)
    if current.get("path") != "exports/titan-current.tar.gz":
        raise ValueError("unexpected current V5 archive path")
    archive = lab / current["path"]
    archive_bytes = archive.read_bytes()
    archive_digest = sha256_bytes(archive_bytes)
    if archive_digest != current.get("sha256"):
        raise ValueError(
            "CURRENT-ARCHIVE sha256 does not match titan-current.tar.gz"
        )
    if len(archive_bytes) != current.get("bytes"):
        raise ValueError(
            "CURRENT-ARCHIVE byte count does not match titan-current.tar.gz"
        )
    # Freeze the exact control bytes in memory before any long-running work.
    baseline = archive_members_bytes(archive_bytes)

    # Acquire the mutable repository harness once, authenticate that closure,
    # then execute evaluator/packer/bridge/opponent support from the snapshot only.
    if args.output.exists():
        raise FileExistsError(args.output)
    with tempfile.TemporaryDirectory(
        prefix="titan-v5-current-carrot-snapshot-", dir=output_parent
    ) as temp:
        staged_snapshot = Path(temp) / "kg"
        harness = h.snapshot_harness(root, staged_snapshot, opponents)
        args.output.mkdir(parents=False, exist_ok=False)
        snapshot_root = args.output / ".harness-snapshot"
        os.replace(staged_snapshot, snapshot_root)

    evaluator_path = snapshot_root / h.EVALUATOR
    evaluator = load(evaluator_path, "carrot_current_evaluator")
    pack = load(snapshot_root / "cloud-pack/pack.py", "carrot_current_pack")
    bridge = load(
        snapshot_root / h.BANK / "reference_policies.py", "carrot_current_bank"
    )
    loader = snapshot_root / "20260907-offline-agent/evaluate.py"
    engine_hashes = evaluator.verify_sources(args.engine_dir)

    arm_members = {"control": baseline}
    build_receipts = {}
    with tempfile.TemporaryDirectory(
        prefix="titan-v5-current-carrot-build-", dir=args.output
    ) as temp:
        temp_root = Path(temp)
        control_root = temp_root / "control"
        h.extract_members(baseline, control_root)
        control_package_sha256 = builder.package_digest(control_root)
        for cap in (4, 12):
            out = temp_root / f"cap{cap}"
            receipt = builder.build_candidate(control_root, out, cap)
            label = f"cap{cap}"
            build_receipts[label] = receipt
            arm_members[label] = members(out)
            if receipt["control_package_sha256"] != control_package_sha256:
                raise ValueError("candidate receipt control identity mismatch")

    runtime = {}
    opponent_receipts = {}
    expected_bridge = harness["repository_files"][
        h.BANK + "/reference_policies.py"
    ]["sha256"]
    expected_registry = harness["repository_files"][
        h.BANK + "/REFERENCE-POLICIES.json"
    ]["sha256"]
    for opponent in opponents:
        runtime[opponent] = args.output / "opponents" / opponent
        receipt = bridge.prepare(opponent, snapshot_root, runtime[opponent])
        if (
            receipt.get("bridge_sha256") != expected_bridge
            or receipt.get("source_registry_sha256") != expected_registry
            or receipt.get("support_files") != harness["opponent_support_sha256"]
        ):
            raise ValueError(
                f"opponent preparation escaped authenticated harness: {opponent}"
            )
        support_root = Path(receipt.get("support_root", "")).resolve(strict=True)
        if support_root != snapshot_root.resolve(strict=True):
            raise ValueError(
                f"opponent preparation did not bind snapshot root: {opponent}"
            )
        opponent_receipts[opponent] = receipt

    # The PR-owned source modules are already loaded/frozen in this process.
    # Reject checkout movement before publishing their identities into the receipt.
    if sha256_bytes(builder_path.read_bytes()) != builder_sha256:
        raise ValueError("candidate builder moved after acquisition")
    if sha256_bytes(launcher_path.read_bytes()) != launcher_sha256:
        raise ValueError("launcher moved after acquisition")

    run = {
        "schema": "astra.v5.selective-carrot.current-paired.v5",
        "method": (
            "Fresh full official-interpreter games from one authenticated in-memory "
            "CURRENT archive snapshot. The shared joint-liquidity helper is externally "
            "Git-blob pinned before import and executed directly from its captured bytes; "
            "the mutable repository is then acquisition-only for the declared evaluator/"
            "packer/bridge/opponent closure. The copied harness is authenticated against "
            "its Git/manifest/registry pins and all game support executes from that snapshot. "
            "Local builder/launcher identities are captured before import/execution and "
            "rechecked before receipt publication. The interpreter wrapper records exact "
            "tested-seat returned-action stream hashes and first pairwise returned-action "
            "divergence separately from observed carrot plant outcomes. Same seed/seat/"
            "opponent across control, cap4 and cap12; deterministic rotating arm order. "
            "Linux 1.25s IPC action limit; canonical policy retains its own 1s deadline. "
            "Not hosted Kaggle rating."
        ),
        "current_archive": current,
        "current_archive_manifest_sha256": current_manifest_sha256,
        "archive_sha256": archive_digest,
        "control_package_sha256": control_package_sha256,
        "engine": engine_hashes,
        "harness": harness,
        "shared_helper": helper_authority,
        "helper_sha256": helper_sha256,
        "builder_sha256": builder_sha256,
        "launcher_sha256": launcher_sha256,
        "build_receipts": build_receipts,
        "candidate_members": {
            arm: {
                name: hashlib.sha256(data).hexdigest()
                for name, data in sorted(payload.items())
            }
            for arm, payload in arm_members.items()
            if arm != "control"
        },
        "opponents": opponent_receipts,
        "seeds": seeds,
        "seats": seats,
    }
    h.write_json(args.output / "run.json", run)

    rotations = (
        ("control", "cap4", "cap12"),
        ("cap12", "control", "cap4"),
        ("cap4", "cap12", "control"),
    )
    cells = []
    cell_index = 0
    summary = {}
    for opponent in opponents:
        for seed in seeds:
            for seat in seats:
                cell_id = f"{opponent}-s{seed}-p{seat}"
                cell = {
                    "cell_id": cell_id,
                    "opponent": opponent,
                    "seed": seed,
                    "seat": seat,
                    "games": {},
                }
                action_streams = {}
                order = rotations[cell_index % len(rotations)]
                cell["execution_order"] = list(order)
                cell_index += 1
                for arm in order:
                    with tempfile.TemporaryDirectory(
                        prefix=f"{cell_id}-{arm}-", dir=args.output
                    ) as temp:
                        directory = Path(temp)
                        payload = directory / "payload"
                        h.extract_members(arm_members[arm], payload)
                        adapter = directory / "adapter.py"
                        pack.write_adapter(adapter, payload / "main.py")
                        rival = runtime[opponent] / "adapter.py"
                        specs = (
                            [str(adapter), str(rival)]
                            if seat == 0
                            else [str(rival), str(adapter)]
                        )
                        engine, _ = evaluator.get_engine(
                            args.engine_dir, loader
                        )
                        interpret = engine.interpreter
                        plant_events = []
                        tested_actions = []
                        interpreter_calls = 0

                        def counted_interpreter(state, env):
                            nonlocal interpreter_calls
                            obs = state[0].observation
                            farms = obs.get("farms") or []
                            before = (
                                {
                                    (x, y): (
                                        tile.get("crop"),
                                        tile.get("planted_day"),
                                    )
                                    for y, row in enumerate(farms[seat]["tiles"])
                                    for x, tile in enumerate(row)
                                    if isinstance(tile, dict)
                                }
                                if farms
                                else {}
                            )
                            if interpreter_calls > 0:
                                tested_actions.append(copy.deepcopy(state[seat].action))
                            result = interpret(state, env)
                            interpreter_calls += 1
                            after_farms = state[0].observation.get("farms") or []
                            if farms and after_farms:
                                for y, row in enumerate(
                                    after_farms[seat]["tiles"]
                                ):
                                    for x, tile in enumerate(row):
                                        if (
                                            isinstance(tile, dict)
                                            and tile.get("crop") == "CARROT"
                                            and before.get((x, y))
                                            != (
                                                "CARROT",
                                                tile.get("planted_day"),
                                            )
                                        ):
                                            plant_events.append(
                                                {
                                                    "step": obs.get("step"),
                                                    "site": [x, y],
                                                    "planted_day": tile.get(
                                                        "planted_day"
                                                    ),
                                                }
                                            )
                            return result

                        engine.interpreter = counted_interpreter
                        game = evaluator.play(
                            engine,
                            specs,
                            args.engine_dir,
                            loader,
                            seed,
                            seat,
                            20260912,
                            1.25,
                            10.0,
                            900.0,
                        )
                        game["actual_carrot_plant_events"] = plant_events
                        game["tested_action_count"] = len(tested_actions)
                        game["tested_action_sha256"] = sha256_bytes(
                            evaluator.encoded(tested_actions)
                        )
                        action_streams[arm] = tested_actions
                    cell["games"][arm] = game
                    h.write_json(args.output / f"{cell_id}-{arm}.json", game)
                    print(
                        json.dumps(
                            {
                                "cell_id": cell_id,
                                "arm": arm,
                                "status": game["status"],
                                "steps": game["steps"],
                                "scores": game["scores"],
                                "tested_action_count": game["tested_action_count"],
                                "tested_action_sha256": game["tested_action_sha256"],
                                "carrot_plant_events": len(plant_events),
                            }
                        ),
                        flush=True,
                    )

                margins = {
                    arm: h.margin(cell["games"][arm], seat) for arm in ARMS
                }
                cell["margins"] = margins
                cell["delta_cap4_control"] = (
                    None
                    if margins["cap4"] is None or margins["control"] is None
                    else margins["cap4"] - margins["control"]
                )
                cell["delta_cap12_control"] = (
                    None
                    if margins["cap12"] is None or margins["control"] is None
                    else margins["cap12"] - margins["control"]
                )
                cell["delta_cap12_cap4"] = (
                    None
                    if margins["cap12"] is None or margins["cap4"] is None
                    else margins["cap12"] - margins["cap4"]
                )
                cell["returned_action_divergence"] = {
                    "cap4_control": first_action_divergence(
                        action_streams["control"], action_streams["cap4"]
                    ),
                    "cap12_control": first_action_divergence(
                        action_streams["control"], action_streams["cap12"]
                    ),
                    "cap12_cap4": first_action_divergence(
                        action_streams["cap4"], action_streams["cap12"]
                    ),
                }
                control_events = cell["games"]["control"].get(
                    "actual_carrot_plant_events", []
                )
                cell["plant_events"] = {
                    arm: len(
                        cell["games"][arm].get("actual_carrot_plant_events", [])
                    )
                    for arm in ARMS
                }
                cell["plant_outcome_diverged"] = {
                    "cap4": cell["games"]["cap4"].get(
                        "actual_carrot_plant_events", []
                    )
                    != control_events,
                    "cap12": cell["games"]["cap12"].get(
                        "actual_carrot_plant_events", []
                    )
                    != control_events,
                }
                cells.append(cell)

                summary = {
                    "cells": len(cells),
                    "complete_cells": sum(
                        all(item["margins"][arm] is not None for arm in ARMS)
                        for item in cells
                    ),
                    "mean_delta_cap4_control": mean(
                        item["delta_cap4_control"] for item in cells
                    ),
                    "mean_delta_cap12_control": mean(
                        item["delta_cap12_control"] for item in cells
                    ),
                    "mean_delta_cap12_cap4": mean(
                        item["delta_cap12_cap4"] for item in cells
                    ),
                    "returned_action_diverged_cells_cap4": sum(
                        item["returned_action_divergence"]["cap4_control"]
                        is not None
                        for item in cells
                    ),
                    "returned_action_diverged_cells_cap12": sum(
                        item["returned_action_divergence"]["cap12_control"]
                        is not None
                        for item in cells
                    ),
                    "plant_outcome_diverged_cells_cap4": sum(
                        item["plant_outcome_diverged"]["cap4"] for item in cells
                    ),
                    "plant_outcome_diverged_cells_cap12": sum(
                        item["plant_outcome_diverged"]["cap12"] for item in cells
                    ),
                    "regressed_cells_cap12_control": sum(
                        item["delta_cap12_control"] is not None
                        and item["delta_cap12_control"] < 0
                        for item in cells
                    ),
                }
                h.write_json(
                    args.output / "report.json",
                    {"run": run, "cells": cells, "summary": summary},
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

    print("SUMMARY " + json.dumps(summary, sort_keys=True), flush=True)
    return int(
        any(
            any(cell["margins"][arm] is None for arm in ARMS)
            for cell in cells
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
