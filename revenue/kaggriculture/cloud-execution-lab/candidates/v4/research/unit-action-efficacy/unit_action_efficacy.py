# SPDX-License-Identifier: Apache-2.0
"""Source-bound unit-action efficacy tracer for the TITAN V4 b567 native fixture.

This is an evidence tool. It never edits actions, runtime source, defaults, or
package bytes. One process traces one seed/seat so agent globals cannot leak
between cells. The complete native runtime is captured and authenticated once,
then execution occurs only from a private materialization of those exact bytes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath

ENGINE_REL = Path("checks/reference/engine/kaggriculture.py")
MAIN_REL = Path("main.py")
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
MAIN_GIT_BLOB = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
SOURCE_SHA256 = "e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2"
ARTIFACT_ID = 10175943272
INNER_TAR_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"

ONE_SHOT_TILE_OPS = frozenset({"CARE", "WATER", "COLLECT_FERTILIZER", "HARVEST"})


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runtime_member_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"unsafe runtime member: {name!r}")
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError(f"unsafe runtime member: {name!r}")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink runtime member forbidden: {name}")
    return current


def capture_runtime(package: Path):
    """Capture and authenticate SOURCE.json plus its exact declared runtime once."""
    package = Path(package)
    if package.is_symlink():
        raise ValueError("package root may not be a symlink")
    package = package.resolve(strict=True)
    source_path = package / "SOURCE.json"
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("SOURCE.json must be a regular non-symlink file")
    manifest_raw = source_path.read_bytes()
    manifest_sha256 = _sha256(manifest_raw)
    if manifest_sha256 != SOURCE_SHA256:
        raise ValueError(
            f"SOURCE.json SHA256 mismatch: expected {SOURCE_SHA256}, got {manifest_sha256}"
        )
    try:
        manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SOURCE.json is not valid UTF-8 JSON") from exc
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else None
    if not isinstance(runtime, dict) or not runtime:
        raise ValueError("SOURCE.json runtime must be a non-empty object")

    captured = {}
    for name, row in runtime.items():
        if not isinstance(row, dict):
            raise ValueError(f"invalid runtime row: {name!r}")
        expected_sha = row.get("sha256")
        expected_bytes = row.get("bytes")
        if (
            not isinstance(expected_sha, str)
            or len(expected_sha) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha)
            or type(expected_bytes) is not int
            or expected_bytes < 0
        ):
            raise ValueError(f"invalid runtime identity: {name!r}")
        path = _runtime_member_path(package, name)
        if not path.is_file():
            raise ValueError(f"missing runtime member: {name}")
        data = path.read_bytes()
        if len(data) != expected_bytes or _sha256(data) != expected_sha:
            raise ValueError(f"runtime member disagrees with SOURCE.json: {name}")
        captured[name] = data

    engine = captured.get(ENGINE_REL.as_posix())
    main = captured.get(MAIN_REL.as_posix())
    if engine is None or git_blob_sha(engine) != ENGINE_GIT_BLOB:
        raise ValueError("official engine Git blob mismatch")
    if main is None or git_blob_sha(main) != MAIN_GIT_BLOB:
        raise ValueError("native main.py Git blob mismatch")
    return manifest_raw, captured


def materialize_runtime(root: Path, manifest_raw: bytes, captured: dict[str, bytes]) -> None:
    """Materialize only authenticated captured bytes into a fresh private tree."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "SOURCE.json").write_bytes(manifest_raw)
    for name, data in captured.items():
        path = root / Path(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _imported(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import captured module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _system_import_paths(paths: list[str]) -> list[str]:
    roots = {Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()}
    result = []
    for value in paths:
        if not value:
            continue
        try:
            resolved = Path(value).resolve()
        except OSError:
            continue
        if any(_is_under(resolved, root) for root in roots):
            result.append(value)
    return result


def _reject_preloaded_runtime_modules(captured: dict[str, bytes]) -> None:
    """Reject every preloaded name that the frozen root runtime must own.

    ``sys.modules`` is consulted before ``sys.path``.  Origin strings therefore
    cannot establish custody: a third-party module installed under ``sys.prefix``
    (or one spoofing ``__file__`` there) would still bypass the frozen snapshot.
    The frozen tree has not been imported yet, so any existing captured root name
    is ambient by definition and must fail closed.
    """
    names = {
        PurePosixPath(member).stem
        for member in captured
        if "/" not in member and member.endswith(".py")
    }
    for name in sorted(names):
        module = sys.modules.get(name)
        if module is None:
            continue
        origin = getattr(module, "__file__", None)
        suffix = f" -> {origin}" if origin else ""
        raise ValueError(f"preloaded runtime module escapes frozen custody: {name}{suffix}")


class _FixtureCustody:
    def __init__(self, scratch, prior_path, source):
        self.scratch = scratch
        self.prior_path = list(prior_path)
        self.source = source

    def close(self):
        sys.path[:] = self.prior_path
        self.scratch.cleanup()


def effect_target(position, action):
    """Return a conservative semantic target used only for attribution.

    The four one-shot tile operations are intentionally narrow: a later no-op
    is attributed to a predecessor only when the earlier actor succeeded on the
    same tile with the same operation. Other no-ops remain unclassified.
    """
    if not isinstance(action, list) or not action:
        return None
    op = action[0]
    if op in ONE_SHOT_TILE_OPS:
        return ("tile", tuple(position), op)
    return None


def trace_unit_vector(engine, farm, private, action, *, step: int, cfg: dict):
    """Replay only the official unit phase on private copies and report effects."""
    farm = copy.deepcopy(farm)
    private = copy.deepcopy(private)
    farmer_action = action.get("farmer", ["PASS"]) if isinstance(action, dict) else ["PASS"]
    hands_actions = action.get("hands", []) if isinstance(action, dict) else []
    if not isinstance(hands_actions, list):
        hands_actions = []
    unit_actions = [farmer_action, *hands_actions]

    plant_demand = Counter()
    for cmd in unit_actions:
        if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "PLANT":
            plant_demand[cmd[1]] += 1
    seeds = private.get("seeds", {}) if isinstance(private, dict) else {}
    blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}

    positions = [tuple(farm["farmer"]), *[tuple(p) for p in farm["hands"]]]
    board_size = int(cfg.get("boardSize", 10))
    turns_per_day = max(1, int(cfg.get("turnsPerDay", 24)))
    shed_capacity = int(cfg.get("shedCapacity", 100))
    day = int(step) // turns_per_day

    successful_targets = {}
    rows = []
    for idx, raw in enumerate(unit_actions):
        if idx >= len(positions):
            break
        blocked_plant = (
            isinstance(raw, list) and len(raw) >= 2 and raw[0] == "PLANT" and raw[1] in blocked
        )
        cmd = ["PASS"] if blocked_plant else raw
        op = cmd[0] if isinstance(cmd, list) and cmd else "<MALFORMED>"
        before_farm, before_private = copy.deepcopy(farm), copy.deepcopy(private)
        engine._apply_unit_action(
            farm, private, idx, cmd, board_size, day, turns_per_day, shed_capacity
        )
        changed = farm != before_farm or private != before_private
        target = effect_target(positions[idx], cmd)
        predecessor = successful_targets.get(target) if target is not None and not changed else None
        if target is not None and changed:
            successful_targets.setdefault(target, idx)
        rows.append({
            "actor_index": idx,
            "position": list(positions[idx]),
            "raw_action": raw,
            "effective_action": cmd,
            "op": op,
            "changed": bool(changed),
            "atomic_plant_blocked": bool(blocked_plant),
            "same_target_successful_predecessor": predecessor,
        })
    return rows


def _load_captured_fixture(frozen: Path):
    """Load evaluator fixture and native entrypoint only from one frozen snapshot."""
    fixture = _imported(
        "unitwaste_captured_engine_semantics",
        frozen / "checks/test_engine_semantics.py",
    )
    fixture.EngineSemantics.setUpClass()
    main = _imported("unitwaste_captured_native_main", frozen / MAIN_REL)
    return fixture.EngineSemantics.engine, fixture.EngineSemantics.ev, main


def _load_fixture(package: Path):
    manifest_raw, captured = capture_runtime(package)
    scratch = tempfile.TemporaryDirectory(prefix="unitwaste-runtime-")
    frozen = Path(scratch.name) / "runtime"
    materialize_runtime(frozen, manifest_raw, captured)
    prior_path = list(sys.path)
    _reject_preloaded_runtime_modules(captured)
    sys.path[:] = [
        str(frozen),
        str(frozen / "checks"),
        *_system_import_paths(prior_path),
    ]
    try:
        engine, ev, main = _load_captured_fixture(frozen)
    except Exception:
        sys.path[:] = prior_path
        scratch.cleanup()
        raise
    source = {
        "artifact_id": ARTIFACT_ID,
        "inner_tar_sha256": INNER_TAR_SHA256,
        "source_manifest_sha256": _sha256(manifest_raw),
        "runtime_members": len(captured),
        "engine_git_blob": git_blob_sha(captured[ENGINE_REL.as_posix()]),
        "main_git_blob": git_blob_sha(captured[MAIN_REL.as_posix()]),
        "immutable_execution_snapshot": True,
    }
    return engine, ev, main, _FixtureCustody(scratch, prior_path, source)


def run_cell(package: Path, seed: int, seat: int):
    if seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    engine, ev, main, custody = _load_fixture(package)
    try:
        cfg = ev.Struct({
            k: (v.get("default") if isinstance(v, dict) else v)
            for k, v in engine.specification["configuration"].items()
        })
        cfg.seed = int(seed)
        env = ev.Struct(configuration=cfg, done=False, info={})
        state = [
            ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0)
            for _ in range(2)
        ]
        engine.interpreter(state, env)

        by_op = {}
        same_target = []
        callbacks = 0
        nonpass = 0
        for step in range(int(cfg.episodeSteps)):
            actions = []
            for player in range(2):
                state[player].observation.step = step
                state[player].observation.remainingOverageTime = 0
                if player == seat:
                    obs = state[player].observation
                    act = main.agent(copy.deepcopy(obs), cfg)
                    rows = trace_unit_vector(
                        engine, obs.farms[player], obs.private, act, step=step, cfg=dict(cfg)
                    )
                    callbacks += 1
                    for row in rows:
                        op = row["op"]
                        if op == "PASS":
                            continue
                        nonpass += 1
                        stat = by_op.setdefault(op, {"total": 0, "changed": 0, "noop": 0})
                        stat["total"] += 1
                        stat["changed"] += int(row["changed"])
                        stat["noop"] += int(not row["changed"])
                        if row["same_target_successful_predecessor"] is not None:
                            same_target.append({
                                "step": step,
                                "actor_index": row["actor_index"],
                                "predecessor_actor_index": row["same_target_successful_predecessor"],
                                "position": row["position"],
                                "op": op,
                                "raw_action": row["raw_action"],
                            })
                else:
                    act = engine.starter_agent(copy.deepcopy(state[player].observation))
                actions.append(act)
            for player, act in enumerate(actions):
                state[player].action = act
            engine.interpreter(state, env)
            if all(s.status == "DONE" for s in state):
                break

        return {
            "schema": "titan-v4-unit-action-efficacy-cell/v1",
            "source": dict(custody.source),
            "seed": int(seed),
            "seat": int(seat),
            "callbacks": callbacks,
            "nonpass_unit_actions": nonpass,
            "by_op": by_op,
            "same_target_predecessor_noops": same_target,
            "scores": [s.reward for s in state],
        }
    finally:
        custody.close()


def main_cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--seat", type=int, choices=(0, 1), required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = run_cell(args.package, args.seed, args.seat)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main_cli()
