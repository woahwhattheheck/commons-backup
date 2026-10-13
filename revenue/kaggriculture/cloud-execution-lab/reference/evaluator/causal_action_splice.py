#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure a first returned-action edge with fail-closed hybrid interventions.

The evaluator discovers the first type-sensitive baseline/candidate action
change on one baseline-controlled trajectory, then executes that candidate
output under baseline continuation and the baseline output under candidate
continuation. Every hybrid must reproduce the full pre-world, both seat
observations, complete pretarget trace, both focal outputs, and target rival
output. Agents run from fresh private copies whose complete regular-file
closures are checked before and after each process.

These are hybrid output effects, not coherent integrated-policy effects: an
agent may commit internal state for the action it returned even when the other
action is executed. Results therefore diagnose an environment/output edge and
cannot by themselves nominate a source feature or predict hosted strength.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import time
from typing import Any, Callable

import evaluate as ev


SCHEMA_VERSION = 2
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 10_000
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_FILES = 10_000

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


def _encoded(value: Any) -> bytes:
    return ev.encoded(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _same(before: Any, after: Any) -> bool:
    """Canonical, type-sensitive equality."""
    try:
        return _encoded(before) == _encoded(after)
    except (TypeError, ValueError, OverflowError):
        return False


def differing_paths(before: Any, after: Any, path: str = "$") -> list[str]:
    """Return stable JSON-like paths whose typed leaf values differ."""
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        output: list[str] = []
        before_keys = set(before)
        after_keys = set(after)
        for key in sorted(
            before_keys | after_keys,
            key=lambda item: (type(item).__name__, repr(item)),
        ):
            child = f"{path}.{key}"
            if key not in before or key not in after:
                output.append(child)
            else:
                output.extend(differing_paths(before[key], after[key], child))
        return output
    if isinstance(before, list):
        output = []
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before) or index >= len(after):
                output.append(child)
            else:
                output.extend(differing_paths(before[index], after[index], child))
        return output
    return [] if _same(before, after) else [path]


def _inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _regular_manifest(root: Path) -> dict[str, Any]:
    """Hash every regular member and reject links/special files."""
    root = root.resolve(strict=True)
    rows: list[dict[str, Any]] = []
    total = 0
    for current, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in list(directories):
            candidate = current_path / name
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError(f"Non-directory snapshot member: {candidate}")
        for name in files:
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(
                metadata.st_mode
            ):
                raise ValueError(f"Non-regular snapshot member: {candidate}")
            relative = candidate.relative_to(root).as_posix()
            total += metadata.st_size
            rows.append(
                {
                    "path": relative,
                    "bytes": metadata.st_size,
                    "mode": stat.S_IMODE(metadata.st_mode),
                    "sha256": ev.sha256(candidate),
                }
            )
            if len(rows) > MAX_SNAPSHOT_FILES:
                raise ValueError("Snapshot exceeds file-count bound")
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError("Snapshot exceeds byte bound")
    if not rows:
        raise ValueError("Agent snapshot contains no regular files")
    closure = hashlib.sha256(_encoded(rows)).hexdigest()
    return {
        "files": len(rows),
        "bytes": total,
        "closure_sha256": closure,
        "members": rows,
    }


def _copy_regular_tree(source: Path, destination: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError(f"Agent source is not a directory: {source}")
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    destination.mkdir(parents=True)
    total = 0
    count = 0
    for current, directories, files in os.walk(
        source, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        target_directory = destination / relative
        target_directory.mkdir(parents=True, exist_ok=True)
        directories.sort()
        files.sort()
        for name in list(directories):
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(
                metadata.st_mode
            ):
                raise ValueError(f"Non-directory agent member: {candidate}")
        for name in files:
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(
                metadata.st_mode
            ):
                raise ValueError(f"Non-regular agent member: {candidate}")
            count += 1
            total += metadata.st_size
            if count > MAX_SNAPSHOT_FILES:
                raise ValueError("Agent source exceeds file-count bound")
            if (
                metadata.st_size > MAX_MEMBER_BYTES
                or total > MAX_SNAPSHOT_BYTES
            ):
                raise ValueError("Agent source exceeds byte bound")
            target = target_directory / name
            with (
                candidate.open("rb") as input_stream,
                target.open("xb") as output_stream,
            ):
                shutil.copyfileobj(
                    input_stream, output_stream, length=1024 * 1024
                )
            os.chmod(target, stat.S_IMODE(metadata.st_mode))
    return _regular_manifest(destination)


def _freeze_tree(root: Path) -> None:
    for current, directories, files in os.walk(
        root, topdown=False, followlinks=False
    ):
        current_path = Path(current)
        for name in files:
            os.chmod(current_path / name, 0o444)
        for name in directories:
            os.chmod(current_path / name, 0o555)
    os.chmod(root, 0o555)


def _thaw_tree(root: Path) -> None:
    if not root.exists():
        return
    for current, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        try:
            os.chmod(current_path, 0o755)
        except FileNotFoundError:
            continue
        for name in files:
            try:
                os.chmod(current_path / name, 0o644)
            except FileNotFoundError:
                pass
        for name in directories:
            try:
                os.chmod(current_path / name, 0o755)
            except FileNotFoundError:
                pass


def _archive_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"Invalid archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ValueError(f"Unsafe archive member name: {name!r}")
    normalized = path.as_posix()
    if normalized.startswith("/"):
        raise ValueError(f"Absolute archive member: {name!r}")
    return normalized


def extract_agent_archive(
    archive_path: Path, destination: Path
) -> dict[str, Any]:
    """Extract a bounded, duplicate-free regular-file archive."""
    archive_path = archive_path.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    destination.mkdir(parents=True)
    total = 0
    members = 0
    seen: set[str] = set()
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive:
            members += 1
            if members > MAX_MEMBERS:
                raise ValueError("Archive exceeds member-count bound")
            normalized = _archive_name(member.name)
            if normalized in seen:
                raise ValueError(
                    f"Duplicate normalized archive member: {normalized!r}"
                )
            seen.add(normalized)
            target = (destination / normalized).resolve()
            if not _inside(destination, target):
                raise ValueError(
                    f"Archive member escapes destination: {member.name!r}"
                )
            if member.isdir():
                target.mkdir(parents=True, exist_ok=False)
                continue
            if not member.isfile():
                raise ValueError(
                    f"Archive member is not a regular file: {member.name!r}"
                )
            if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise ValueError(
                    f"Archive member exceeds size bound: {member.name!r}"
                )
            total += member.size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("Archive exceeds extracted-size bound")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError(
                    f"Archive member aliases existing path: {member.name!r}"
                )
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(
                    f"Cannot read archive member: {member.name!r}"
                )
            with target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            if target.stat().st_size != member.size:
                raise ValueError(
                    f"Archive member size mismatch: {member.name!r}"
                )
    entry = destination / "main.py"
    if not entry.is_file() or entry.is_symlink():
        raise ValueError("Agent archive has no regular root main.py")
    manifest = _regular_manifest(destination)
    return {
        "archive_sha256": ev.sha256(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "members": members,
        "extracted_bytes": total,
        "entry_sha256": ev.sha256(entry),
        "closure_sha256": manifest["closure_sha256"],
        "closure_files": manifest["files"],
        "closure_bytes": manifest["bytes"],
    }


@dataclass(frozen=True)
class AgentBlueprint:
    label: str
    kind: str
    snapshot_root: Path | None
    relative_entry: str | None
    function: str
    receipt: dict[str, Any]
    literal_spec: str | None = None

    @classmethod
    def literal(cls, spec: str) -> "AgentBlueprint":
        return cls(
            spec,
            "literal",
            None,
            None,
            "agent",
            {"kind": "literal", "spec": spec},
            spec,
        )

    def materialize(
        self, run_root: Path, role: str
    ) -> "MaterializedAgent":
        if self.kind == "literal":
            assert self.literal_spec is not None
            return MaterializedAgent(self.literal_spec, None, None, None)
        assert self.snapshot_root is not None
        assert self.relative_entry is not None
        current_source = _regular_manifest(self.snapshot_root)
        expected = self.receipt["closure_sha256"]
        if current_source["closure_sha256"] != expected:
            raise ValueError(
                f"Authenticated source snapshot changed for {self.label}"
            )
        target = run_root / role
        before = _copy_regular_tree(self.snapshot_root, target)
        if before["closure_sha256"] != expected:
            raise ValueError(f"Private copy differs for {self.label}")
        _freeze_tree(target)
        before = _regular_manifest(target)
        entry = target / self.relative_entry
        if not entry.is_file():
            raise ValueError(f"Private entry missing for {self.label}")
        return MaterializedAgent(
            str(entry.resolve()) + "::" + self.function,
            target,
            before,
            expected,
        )


@dataclass
class MaterializedAgent:
    spec: str
    root: Path | None
    before: dict[str, Any] | None
    expected_closure: str | None

    def verify(self) -> dict[str, Any]:
        if self.root is None:
            return {"kind": "literal", "unchanged": True}
        try:
            after = _regular_manifest(self.root)
        except Exception as exc:
            return {
                "kind": "private_copy",
                "unchanged": False,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }
        unchanged = (
            self.before is not None
            and after["closure_sha256"] == self.before["closure_sha256"]
            and after["closure_sha256"] == self.expected_closure
        )
        return {
            "kind": "private_copy",
            "unchanged": unchanged,
            "before_closure_sha256": (
                None
                if self.before is None
                else self.before["closure_sha256"]
            ),
            "after_closure_sha256": after["closure_sha256"],
            "files": after["files"],
            "bytes": after["bytes"],
        }


def prepare_agent(value: str, store: Path, label: str) -> AgentBlueprint:
    """Create a private authenticated source snapshot never executed directly."""
    path_text, separator, _requested_function = value.partition("::")
    path = Path(path_text).expanduser()
    destination = store / label
    if path.exists() and path.is_file() and (
        path.name.endswith(".tar.gz") or path.suffix == ".tgz"
    ):
        if separator:
            raise ValueError("Archive inputs expose root main.py::agent")
        receipt = {
            "kind": "archive",
            "path": str(path.resolve()),
            **extract_agent_archive(path, destination),
        }
        _freeze_tree(destination)
        receipt["closure_sha256"] = _regular_manifest(destination)[
            "closure_sha256"
        ]
        return AgentBlueprint(
            label,
            "archive",
            destination,
            "main.py",
            "agent",
            receipt,
        )
    if path.exists() and path.is_dir():
        if separator:
            raise ValueError("Directory inputs expose main.py::agent")
        _copy_regular_tree(path, destination)
        if not (destination / "main.py").is_file():
            raise ValueError("Agent directory has no root main.py")
        entry_sha256 = ev.sha256(destination / "main.py")
        _freeze_tree(destination)
        manifest = _regular_manifest(destination)
        receipt = {
            "kind": "directory_snapshot",
            "path": str(path.resolve()),
            "entry_sha256": entry_sha256,
            **manifest,
        }
        return AgentBlueprint(
            label,
            "directory_snapshot",
            destination,
            "main.py",
            "agent",
            receipt,
        )

    resolved = ev.resolve_spec(value)
    resolved_path_text, separator, function = resolved.partition("::")
    if not separator:
        raise ValueError(
            f"Resolved entrypoint lacks function: {resolved!r}"
        )
    entry = Path(resolved_path_text).resolve(strict=True)
    root = entry.parent
    _copy_regular_tree(root, destination)
    relative = entry.relative_to(root).as_posix()
    entry_sha256 = ev.sha256(destination / relative)
    _freeze_tree(destination)
    manifest = _regular_manifest(destination)
    receipt = {
        "kind": "entrypoint_parent_snapshot",
        "path": str(entry),
        "function": function,
        "entry_sha256": entry_sha256,
        "dynamic_imports_outside_snapshot_not_attested": True,
        **manifest,
    }
    return AgentBlueprint(
        label,
        "entrypoint_parent_snapshot",
        destination,
        relative,
        function,
        receipt,
    )


def _configuration(
    engine: Any, seed: int, episode_steps: int | None
) -> Any:
    cfg = ev.Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    if episode_steps is not None:
        cfg.episodeSteps = episode_steps
    if (
        not isinstance(cfg.episodeSteps, int)
        or isinstance(cfg.episodeSteps, bool)
        or cfg.episodeSteps < 2
    ):
        raise ValueError("episodeSteps must be an integer at least 2")
    if (
        not isinstance(cfg.turnsPerDay, int)
        or isinstance(cfg.turnsPerDay, bool)
        or cfg.turnsPerDay < 1
    ):
        raise ValueError("turnsPerDay must be a positive integer")
    cfg.seed = seed
    return cfg


def _snapshot(state: list[Any], env: Any) -> dict[str, Any]:
    return {
        "agents": [
            {
                "observation": item.observation,
                "action": item.action,
                "status": item.status,
                "reward": item.reward,
            }
            for item in state
        ],
        "environment": {
            "configuration": env.configuration,
            "done": env.done,
            "info": env.info,
        },
    }


def _metric(
    result: dict[str, Any], seat: int
) -> dict[str, float] | None:
    scores = result.get("scores")
    if (
        result.get("status") != "complete"
        or not isinstance(scores, list)
        or len(scores) != 2
    ):
        return None
    own = float(scores[seat])
    rival = float(scores[1 - seat])
    return {
        "focal_score": own,
        "opponent_score": rival,
        "margin": own - rival,
    }


def _subtract(
    after: dict[str, float], before: dict[str, float]
) -> dict[str, float]:
    return {key: after[key] - before[key] for key in after}


def _outcome(
    metrics: dict[str, float], tolerance: float = 1e-9
) -> str:
    if metrics["margin"] > tolerance:
        return "W"
    if metrics["margin"] < -tolerance:
        return "L"
    return "T"


def _transition(
    before: dict[str, float], after: dict[str, float]
) -> dict[str, str]:
    left = _outcome(before)
    right = _outcome(after)
    return {
        "before": left,
        "after": right,
        "transition": f"{left}->{right}",
    }


def _pair_classification(
    first: float, second: float, tolerance: float = 1e-9
) -> str:
    if (
        first >= -tolerance
        and second >= -tolerance
        and (first > tolerance or second > tolerance)
    ):
        return "supported"
    if (
        first <= tolerance
        and second <= tolerance
        and (first < -tolerance or second < -tolerance)
    ):
        return "harmful"
    if abs(first) <= tolerance and abs(second) <= tolerance:
        return "neutral"
    return "mixed"


def _hybrid_classification(
    effects: dict[str, dict[str, float]],
    outcomes: dict[str, dict[str, str]],
) -> tuple[str, dict[str, str]]:
    treatment = effects["candidate_action_on_baseline"]
    ablation = effects["candidate_action_on_candidate"]
    metrics = {
        "focal_score": _pair_classification(
            treatment["focal_score"], ablation["focal_score"]
        ),
        "margin": _pair_classification(
            treatment["margin"], ablation["margin"]
        ),
        "opponent_score_reduction": _pair_classification(
            -treatment["opponent_score"], -ablation["opponent_score"]
        ),
    }
    rank = {"L": 0, "T": 1, "W": 2}
    degraded = any(
        rank[row["after"]] < rank[row["before"]]
        for row in outcomes.values()
    )
    if (
        metrics["focal_score"] == "supported"
        and metrics["margin"] != "harmful"
        and not degraded
    ):
        label = "hybrid_own_supported"
    elif metrics["focal_score"] == "harmful" or degraded:
        label = "hybrid_own_harmful"
    elif (
        metrics["focal_score"] == "neutral"
        and metrics["margin"] == "neutral"
    ):
        label = "hybrid_neutral"
    else:
        label = "hybrid_mixed"
    return label, metrics


def _action_response(
    actor: Any,
    observation: Any,
    configuration: Any,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    response = actor.act(observation, configuration, timeout)
    if response.get("kind") != "action":
        return None, response
    action = response.get("action")
    if not isinstance(action, dict):
        return None, {
            "kind": "protocol_error",
            "error": "Action is not an object",
        }
    try:
        _encoded(action)
    except (TypeError, ValueError, OverflowError) as exc:
        return None, {
            "kind": "protocol_error",
            "error": f"Action is not canonical: {exc}"[:1000],
        }
    return action, None


def _context_equal(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    keys = (
        "step",
        "preworld_sha256",
        "observation_sha256",
        "rival_observation_sha256",
        "prefix_trace_sha256",
        "rival_action_sha256",
    )
    return all(left.get(key) == right.get(key) for key in keys)


def run_variant(
    engine: Any,
    *,
    policy: AgentBlueprint,
    opponent: AgentBlueprint,
    cache: Path,
    loader: Path,
    workspace: Path,
    seed: int,
    focal_seat: int,
    rng_seed: int,
    shadow: AgentBlueprint | None = None,
    discover: bool = False,
    intervention_step: int | None = None,
    expected_context: dict[str, Any] | None = None,
    expected_policy_action: dict[str, Any] | None = None,
    expected_shadow_action: dict[str, Any] | None = None,
    capture_step: int | None = None,
    action_timeout: float = 1.0,
    startup_timeout: float = 10.0,
    game_timeout: float = 120.0,
    episode_steps: int | None = None,
    actor_factory: Callable[..., Any] = ev.Actor,
) -> dict[str, Any]:
    """Run one policy with an optional shadow and one output intervention."""
    if focal_seat not in (0, 1):
        raise ValueError("focal_seat must be 0 or 1")
    if intervention_step is not None and shadow is None:
        raise ValueError("An intervention requires a shadow policy")
    if intervention_step is not None and intervention_step < 0:
        raise ValueError("intervention_step must be nonnegative")
    if discover and shadow is None:
        raise ValueError("Discovery requires a shadow policy")
    if intervention_step is not None and expected_context is None:
        raise ValueError(
            "An intervention requires an authenticated target context"
        )

    cfg = _configuration(engine, seed, episode_steps)
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [
        ev.Struct(
            observation=ev.Struct(),
            action={},
            status="ACTIVE",
            reward=0,
        )
        for _ in range(2)
    ]
    trace = hashlib.sha256()
    actors: dict[str, Any] = {}
    materialized: dict[str, MaterializedAgent] = {}
    run_root = Path(
        tempfile.mkdtemp(prefix="splice-run-", dir=workspace)
    )
    started = time.perf_counter()
    result: dict[str, Any] = {
        "seed": seed,
        "focal_seat": focal_seat,
        "status": "failed",
        "failure": None,
        "scores": None,
        "steps": 0,
        "episode_steps": int(cfg.episodeSteps),
        "turns_per_day": int(cfg.turnsPerDay),
        "first_divergence": None,
        "target": None,
        "captured_action": None,
    }

    def fail(kind: str, **details: Any) -> None:
        if result["failure"] is None:
            result["failure"] = {"kind": kind, **details}
        result["status"] = "failed"

    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise ValueError("Environment seed must not be exposed to agents")
        initial = _snapshot(state, env)
        trace.update(_encoded({"phase": "initial", "state": initial}))

        blueprints = {"policy": policy, "opponent": opponent}
        if shadow is not None:
            blueprints["shadow"] = shadow
        for role, blueprint in blueprints.items():
            materialized[role] = blueprint.materialize(run_root, role)
        actors["policy"] = actor_factory(
            materialized["policy"].spec,
            cache,
            loader,
            rng_seed,
            startup_timeout,
        )
        actors["opponent"] = actor_factory(
            materialized["opponent"].spec,
            cache,
            loader,
            rng_seed + 1,
            startup_timeout,
        )
        if shadow is not None:
            actors["shadow"] = actor_factory(
                materialized["shadow"].spec,
                cache,
                loader,
                rng_seed,
                startup_timeout,
            )
        for role, actor in actors.items():
            ready = actor.ready
            if ready.get("kind") != "ready":
                fail("startup", role=role, response=ready)
                break

        if result["failure"] is None:
            for step in range(cfg.episodeSteps):
                remaining = game_timeout - (
                    time.perf_counter() - started
                )
                if remaining <= 0:
                    fail("game_timeout", step=step)
                    break
                focal_observation = state[focal_seat].observation
                rival_observation = state[1 - focal_seat].observation
                for observation in (
                    focal_observation,
                    rival_observation,
                ):
                    observation.step = step
                    observation.remainingOverageTime = 0
                try:
                    preworld = _snapshot(state, env)
                    context = {
                        "step": step,
                        "day": step // int(cfg.turnsPerDay),
                        "within_day": step % int(cfg.turnsPerDay),
                        "preworld_sha256": _digest(preworld),
                        "observation_sha256": _digest(
                            focal_observation
                        ),
                        "rival_observation_sha256": _digest(
                            rival_observation
                        ),
                        "prefix_trace_sha256": trace.hexdigest(),
                    }
                except (TypeError, ValueError, OverflowError) as exc:
                    fail(
                        "state_encoding",
                        step=step,
                        error=f"{type(exc).__name__}: {exc}"[:1000],
                    )
                    break

                policy_action, error = _action_response(
                    actors["policy"],
                    focal_observation,
                    cfg,
                    min(action_timeout, remaining),
                )
                if error is not None:
                    fail(
                        "action",
                        role="policy",
                        step=step,
                        response=error,
                    )
                    break

                need_shadow = shadow is not None and (
                    (
                        discover
                        and result["first_divergence"] is None
                    )
                    or (
                        intervention_step is not None
                        and step <= intervention_step
                    )
                )
                shadow_action = None
                if need_shadow:
                    remaining = game_timeout - (
                        time.perf_counter() - started
                    )
                    if remaining <= 0:
                        fail("game_timeout", step=step)
                        break
                    shadow_action, error = _action_response(
                        actors["shadow"],
                        focal_observation,
                        cfg,
                        min(action_timeout, remaining),
                    )
                    if error is not None:
                        fail(
                            "action",
                            role="shadow",
                            step=step,
                            response=error,
                        )
                        break

                remaining = game_timeout - (
                    time.perf_counter() - started
                )
                if remaining <= 0:
                    fail("game_timeout", step=step)
                    break
                rival_action, error = _action_response(
                    actors["opponent"],
                    rival_observation,
                    cfg,
                    min(action_timeout, remaining),
                )
                if error is not None:
                    fail(
                        "action",
                        role="opponent",
                        step=step,
                        response=error,
                    )
                    break
                context["rival_action_sha256"] = _digest(rival_action)

                if (
                    discover
                    and shadow_action is not None
                    and not _same(policy_action, shadow_action)
                ):
                    result["first_divergence"] = {
                        **context,
                        "policy_action": policy_action,
                        "shadow_action": shadow_action,
                        "rival_action": rival_action,
                        "policy_action_sha256": _digest(policy_action),
                        "shadow_action_sha256": _digest(
                            shadow_action
                        ),
                        "differing_paths": differing_paths(
                            policy_action, shadow_action
                        ),
                    }

                if (
                    intervention_step is not None
                    and step < intervention_step
                ):
                    if shadow_action is None or not _same(
                        policy_action, shadow_action
                    ):
                        fail(
                            "prefix_policy_mismatch",
                            step=step,
                            policy_action_sha256=_digest(
                                policy_action
                            ),
                            shadow_action_sha256=(
                                None
                                if shadow_action is None
                                else _digest(shadow_action)
                            ),
                        )
                        break

                executed_action = policy_action
                if (
                    intervention_step is not None
                    and step == intervention_step
                ):
                    if shadow_action is None:
                        fail("missing_shadow_action", step=step)
                        break
                    checks = {
                        "context": _context_equal(
                            context, expected_context or {}
                        ),
                        "policy_action": (
                            expected_policy_action is not None
                            and _same(
                                policy_action,
                                expected_policy_action,
                            )
                        ),
                        "shadow_action": (
                            expected_shadow_action is not None
                            and _same(
                                shadow_action,
                                expected_shadow_action,
                            )
                        ),
                    }
                    if not all(checks.values()):
                        fail(
                            "target_context_mismatch",
                            step=step,
                            checks=checks,
                            expected_context=expected_context,
                            actual_context=context,
                            expected_policy_action_sha256=(
                                None
                                if expected_policy_action is None
                                else _digest(expected_policy_action)
                            ),
                            actual_policy_action_sha256=_digest(
                                policy_action
                            ),
                            expected_shadow_action_sha256=(
                                None
                                if expected_shadow_action is None
                                else _digest(expected_shadow_action)
                            ),
                            actual_shadow_action_sha256=_digest(
                                shadow_action
                            ),
                        )
                        break
                    executed_action = shadow_action
                    result["target"] = {
                        **context,
                        "context_checks": checks,
                        "policy_action": policy_action,
                        "shadow_action": shadow_action,
                        "rival_action": rival_action,
                        "executed_action": executed_action,
                        "policy_action_sha256": _digest(
                            policy_action
                        ),
                        "shadow_action_sha256": _digest(
                            shadow_action
                        ),
                        "executed_action_sha256": _digest(
                            executed_action
                        ),
                        "differing_paths": differing_paths(
                            policy_action, shadow_action
                        ),
                    }

                if capture_step is not None and step == capture_step:
                    result["captured_action"] = {
                        **context,
                        "action": policy_action,
                        "rival_action": rival_action,
                        "action_sha256": _digest(policy_action),
                    }

                actions = [None, None]
                actions[focal_seat] = executed_action
                actions[1 - focal_seat] = rival_action
                for seat in range(2):
                    state[seat].action = actions[seat]
                engine.interpreter(state, env)
                result["steps"] += 1
                try:
                    postworld = _snapshot(state, env)
                    postworld_sha256 = _digest(postworld)
                    trace.update(
                        _encoded(
                            {
                                "step": step,
                                "preworld": preworld,
                                "actions": actions,
                                "postworld": postworld,
                            }
                        )
                    )
                except (TypeError, ValueError, OverflowError) as exc:
                    fail(
                        "state_encoding",
                        step=step,
                        error=f"{type(exc).__name__}: {exc}"[:1000],
                    )
                    break
                if (
                    result["target"] is not None
                    and result["target"]["step"] == step
                ):
                    result["target"][
                        "postworld_sha256"
                    ] = postworld_sha256
                done = all(item.status == "DONE" for item in state)
                if done:
                    scores = [item.reward for item in state]
                    if not all(
                        isinstance(score, (int, float))
                        and not isinstance(score, bool)
                        and math.isfinite(score)
                        for score in scores
                    ):
                        raise ValueError(
                            "Nonfinite, boolean, or missing terminal score"
                        )
                    result.update(status="complete", scores=scores)
                    env.done = True
                    break
            if (
                result["failure"] is None
                and result["status"] != "complete"
            ):
                fail("incomplete", step=result["steps"])
            if (
                intervention_step is not None
                and result["target"] is None
            ):
                fail(
                    "target_not_reached",
                    expected_step=intervention_step,
                    steps=result["steps"],
                )
    except Exception as exc:
        fail(
            "engine_error",
            step=result["steps"],
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
    finally:
        for actor in actors.values():
            actor.close()
        source_reports = {
            role: item.verify()
            for role, item in materialized.items()
        }
        if any(
            not report.get("unchanged", False)
            for report in source_reports.values()
        ):
            fail("source_mutation", source_reports=source_reports)
        result["actors"] = {
            role: actor.report() for role, actor in actors.items()
        }
        result["source_custody"] = source_reports
        result["wall_seconds"] = time.perf_counter() - started
        result["trace_sha256"] = trace.hexdigest()
        _thaw_tree(run_root)
        shutil.rmtree(run_root, ignore_errors=True)
    return result


def _capture_matches(
    capture: dict[str, Any] | None,
    divergence: dict[str, Any],
    expected_action: dict[str, Any],
) -> bool:
    return (
        capture is not None
        and _context_equal(capture, divergence)
        and _same(capture.get("action"), expected_action)
        and _same(
            capture.get("rival_action"),
            divergence.get("rival_action"),
        )
    )


def evaluate_cell(
    engine: Any,
    *,
    baseline: AgentBlueprint,
    candidate: AgentBlueprint,
    opponent: AgentBlueprint,
    cache: Path,
    loader: Path,
    workspace: Path,
    seed: int,
    focal_seat: int,
    rng_seed: int = 20260907,
    action_timeout: float = 1.0,
    startup_timeout: float = 10.0,
    game_timeout: float = 120.0,
    episode_steps: int | None = None,
    actor_factory: Callable[..., Any] = ev.Actor,
) -> dict[str, Any]:
    """Evaluate one seed/seat cell with replay, treatment, and ablation."""
    common = dict(
        engine=engine,
        opponent=opponent,
        cache=cache,
        loader=loader,
        workspace=workspace,
        seed=seed,
        focal_seat=focal_seat,
        rng_seed=rng_seed,
        action_timeout=action_timeout,
        startup_timeout=startup_timeout,
        game_timeout=game_timeout,
        episode_steps=episode_steps,
        actor_factory=actor_factory,
    )
    discovery = run_variant(
        policy=baseline,
        shadow=candidate,
        discover=True,
        **common,
    )
    cell: dict[str, Any] = {
        "seed": seed,
        "focal_seat": focal_seat,
        "classification": "failed",
        "metric_classifications": None,
        "divergence": discovery.get("first_divergence"),
        "runs": {"baseline_discovery": discovery},
        "effects": None,
        "outcomes": None,
        "replay": None,
    }
    if discovery["status"] != "complete":
        return cell

    divergence = discovery["first_divergence"]
    capture = None if divergence is None else int(divergence["step"])
    baseline_replay = run_variant(
        policy=baseline,
        capture_step=capture,
        **common,
    )
    cell["runs"]["baseline_replay"] = baseline_replay
    if baseline_replay["status"] != "complete":
        return cell
    baseline_trace_equal = (
        baseline_replay["trace_sha256"] == discovery["trace_sha256"]
    )
    baseline_scores_equal = _same(
        baseline_replay["scores"], discovery["scores"]
    )
    if not baseline_trace_equal or not baseline_scores_equal:
        cell["classification"] = "unstable"
        cell["replay"] = {
            "baseline_trace_equal": baseline_trace_equal,
            "baseline_scores_equal": baseline_scores_equal,
        }
        return cell

    if divergence is None:
        cell["classification"] = "dormant"
        cell["replay"] = {
            "baseline_trace_equal": True,
            "baseline_scores_equal": True,
        }
        return cell

    target_step = int(divergence["step"])
    baseline_action = divergence["policy_action"]
    candidate_action = divergence["shadow_action"]
    baseline_target_equal = _capture_matches(
        baseline_replay.get("captured_action"),
        divergence,
        baseline_action,
    )
    if not baseline_target_equal:
        cell["classification"] = "unstable"
        cell["replay"] = {
            "baseline_trace_equal": True,
            "baseline_scores_equal": True,
            "baseline_target_equal": False,
        }
        return cell

    candidate_native = run_variant(
        policy=candidate,
        capture_step=target_step,
        **common,
    )
    candidate_replay = run_variant(
        policy=candidate,
        capture_step=target_step,
        **common,
    )
    cell["runs"].update(
        candidate_native=candidate_native,
        candidate_replay=candidate_replay,
    )
    if (
        candidate_native["status"] != "complete"
        or candidate_replay["status"] != "complete"
    ):
        return cell
    candidate_trace_equal = (
        candidate_replay["trace_sha256"]
        == candidate_native["trace_sha256"]
    )
    candidate_scores_equal = _same(
        candidate_replay["scores"], candidate_native["scores"]
    )
    candidate_target_equal = _capture_matches(
        candidate_native.get("captured_action"),
        divergence,
        candidate_action,
    )
    candidate_replay_target_equal = _capture_matches(
        candidate_replay.get("captured_action"),
        divergence,
        candidate_action,
    )
    if not all(
        (
            candidate_trace_equal,
            candidate_scores_equal,
            candidate_target_equal,
            candidate_replay_target_equal,
        )
    ):
        cell["classification"] = "unstable"
        cell["replay"] = {
            "baseline_trace_equal": True,
            "baseline_scores_equal": True,
            "baseline_target_equal": True,
            "candidate_trace_equal": candidate_trace_equal,
            "candidate_scores_equal": candidate_scores_equal,
            "candidate_target_equal": candidate_target_equal,
            "candidate_replay_target_equal": (
                candidate_replay_target_equal
            ),
        }
        return cell

    context = {
        key: divergence[key]
        for key in (
            "step",
            "preworld_sha256",
            "observation_sha256",
            "rival_observation_sha256",
            "prefix_trace_sha256",
            "rival_action_sha256",
        )
    }
    injection = run_variant(
        policy=baseline,
        shadow=candidate,
        intervention_step=target_step,
        expected_context=context,
        expected_policy_action=baseline_action,
        expected_shadow_action=candidate_action,
        **common,
    )
    ablation = run_variant(
        policy=candidate,
        shadow=baseline,
        intervention_step=target_step,
        expected_context=context,
        expected_policy_action=candidate_action,
        expected_shadow_action=baseline_action,
        **common,
    )
    cell["runs"].update(
        candidate_action_on_baseline=injection,
        baseline_action_on_candidate=ablation,
    )
    if (
        injection["status"] != "complete"
        or ablation["status"] != "complete"
    ):
        return cell
    injection_target_equal = (
        injection.get("target") is not None
        and _context_equal(injection["target"], divergence)
    )
    ablation_target_equal = (
        ablation.get("target") is not None
        and _context_equal(ablation["target"], divergence)
    )
    all_context_checks = all(
        injection["target"]["context_checks"].values()
    ) and all(ablation["target"]["context_checks"].values())
    replay = {
        "baseline_trace_equal": True,
        "baseline_scores_equal": True,
        "baseline_target_equal": True,
        "candidate_trace_equal": True,
        "candidate_scores_equal": True,
        "candidate_target_equal": True,
        "candidate_replay_target_equal": True,
        "injection_target_equal": injection_target_equal,
        "ablation_target_equal": ablation_target_equal,
        "hybrid_context_checks": all_context_checks,
    }
    cell["replay"] = replay
    if not all(replay.values()):
        cell["classification"] = "unstable"
        return cell

    baseline_metrics = _metric(discovery, focal_seat)
    candidate_metrics = _metric(candidate_native, focal_seat)
    injection_metrics = _metric(injection, focal_seat)
    ablation_metrics = _metric(ablation, focal_seat)
    if any(
        item is None
        for item in (
            baseline_metrics,
            candidate_metrics,
            injection_metrics,
            ablation_metrics,
        )
    ):
        return cell
    assert baseline_metrics is not None
    assert candidate_metrics is not None
    assert injection_metrics is not None
    assert ablation_metrics is not None
    effects = {
        "candidate_native_minus_baseline": _subtract(
            candidate_metrics, baseline_metrics
        ),
        "candidate_action_on_baseline": _subtract(
            injection_metrics, baseline_metrics
        ),
        "candidate_action_on_candidate": _subtract(
            candidate_metrics, ablation_metrics
        ),
    }
    outcomes = {
        "candidate_native_minus_baseline": _transition(
            baseline_metrics, candidate_metrics
        ),
        "candidate_action_on_baseline": _transition(
            baseline_metrics, injection_metrics
        ),
        "candidate_action_on_candidate": _transition(
            ablation_metrics, candidate_metrics
        ),
    }
    classification, metric_classifications = _hybrid_classification(
        effects, outcomes
    )
    cell["effects"] = effects
    cell["outcomes"] = outcomes
    cell["metric_classifications"] = metric_classifications
    cell["classification"] = classification
    return cell


def summarize(cells: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(cell["classification"] for cell in cells)
    complete = [
        cell for cell in cells if cell.get("effects") is not None
    ]
    mean_effects: dict[str, dict[str, float]] = {}
    for name in (
        "candidate_native_minus_baseline",
        "candidate_action_on_baseline",
        "candidate_action_on_candidate",
    ):
        rows = [cell["effects"][name] for cell in complete]
        if rows:
            mean_effects[name] = {
                metric: sum(row[metric] for row in rows) / len(rows)
                for metric in (
                    "focal_score",
                    "opponent_score",
                    "margin",
                )
            }
    return {
        "scheduled": len(cells),
        "classifications": dict(sorted(counts.items())),
        "hybrid_cells": len(complete),
        "mean_effects": mean_effects,
    }


def _parse_ints(
    value: str, *, allowed: set[int] | None = None
) -> list[int]:
    parsed = [
        int(item.strip())
        for item in value.split(",")
        if item.strip()
    ]
    if not parsed or len(parsed) != len(set(parsed)):
        raise ValueError(
            "Values must be distinct comma-separated integers"
        )
    if allowed is not None and not set(parsed) <= allowed:
        raise ValueError(f"Values must be drawn from {sorted(allowed)}")
    return parsed


def _validate_output(
    path: Path, files: list[Path], roots: list[Path]
) -> Path:
    output = path.expanduser().absolute()
    resolved_parent = output.parent.resolve(strict=True)
    resolved = resolved_parent / output.name
    for root in roots:
        root_resolved = root.resolve(strict=True)
        if _inside(root_resolved, resolved):
            raise ValueError(
                "Output must be outside authenticated/executable root: "
                f"{root_resolved}"
            )
    for source in files:
        source_resolved = source.resolve(strict=True)
        if resolved == source_resolved:
            raise ValueError(
                f"Output aliases bound input: {source_resolved}"
            )
        if output.exists() and os.path.samefile(
            output, source_resolved
        ):
            raise ValueError(
                f"Output inode aliases bound input: {source_resolved}"
            )
    return resolved


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, delete=False
    ) as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-dir",
        type=Path,
        default=(
            Path(__file__).resolve().parent.parent / "engine"
        ),
    )
    parser.add_argument("--loader", type=Path, default=ev.LOADER)
    parser.add_argument(
        "--baseline",
        required=True,
        help="Archive, directory, or path.py::agent",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="Archive, directory, or path.py::agent",
    )
    parser.add_argument("--opponent", default="official_starter")
    parser.add_argument("--seeds", default="2027")
    parser.add_argument("--seats", default="0,1")
    parser.add_argument("--rng-seed", type=int, default=20260907)
    parser.add_argument("--action-timeout", type=float, default=1.0)
    parser.add_argument(
        "--startup-timeout", type=float, default=10.0
    )
    parser.add_argument("--game-timeout", type=float, default=120.0)
    parser.add_argument("--episode-steps", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    for value in (
        args.action_timeout,
        args.startup_timeout,
        args.game_timeout,
    ):
        if not math.isfinite(value) or value <= 0:
            parser.error("Timeouts must be finite and positive")
    try:
        seeds = _parse_ints(args.seeds)
        seats = _parse_ints(args.seats, allowed={0, 1})
    except ValueError as exc:
        parser.error(str(exc))

    engine, engine_hashes = ev.get_engine(
        args.engine_dir, args.loader
    )
    with tempfile.TemporaryDirectory(
        prefix="titan-causal-splice-",
        ignore_cleanup_errors=True,
    ) as directory:
        workspace = Path(directory)
        store = workspace / "authenticated-sources"
        store.mkdir()
        baseline = prepare_agent(
            args.baseline, store, "baseline"
        )
        candidate = prepare_agent(
            args.candidate, store, "candidate"
        )
        opponent = prepare_agent(
            args.opponent, store, "opponent"
        )
        source_files = [Path(__file__), args.loader]
        source_roots = [
            Path(__file__).resolve().parent,
            args.engine_dir,
        ]
        for blueprint in (baseline, candidate, opponent):
            path_value = blueprint.receipt.get("path")
            if path_value:
                source_path = Path(path_value)
                if source_path.is_file():
                    source_files.append(source_path)
                    source_roots.append(source_path.parent)
                elif source_path.is_dir():
                    source_roots.append(source_path)
        try:
            output = _validate_output(
                args.output, source_files, source_roots
            )
        except ValueError as exc:
            parser.error(str(exc))

        cells = []
        for seed in seeds:
            for seat in seats:
                cell = evaluate_cell(
                    engine,
                    baseline=baseline,
                    candidate=candidate,
                    opponent=opponent,
                    cache=args.engine_dir,
                    loader=args.loader,
                    workspace=workspace,
                    seed=seed,
                    focal_seat=seat,
                    rng_seed=args.rng_seed,
                    action_timeout=args.action_timeout,
                    startup_timeout=args.startup_timeout,
                    game_timeout=args.game_timeout,
                    episode_steps=args.episode_steps,
                )
                cells.append(cell)
                print(
                    json.dumps(
                        {
                            "seed": seed,
                            "focal_seat": seat,
                            "classification": cell[
                                "classification"
                            ],
                            "step": (
                                None
                                if cell["divergence"] is None
                                else cell["divergence"]["step"]
                            ),
                            "effects": cell["effects"],
                            "outcomes": cell["outcomes"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

        source_snapshot_final = {
            blueprint.label: _regular_manifest(
                blueprint.snapshot_root
            )
            for blueprint in (baseline, candidate, opponent)
            if blueprint.snapshot_root is not None
        }
        source_snapshots_unchanged = all(
            source_snapshot_final[blueprint.label][
                "closure_sha256"
            ]
            == blueprint.receipt["closure_sha256"]
            for blueprint in (baseline, candidate, opponent)
            if blueprint.snapshot_root is not None
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "method": (
                "First type-sensitive returned-action divergence on a "
                "full-state-authenticated shared prefix; fresh-copy baseline "
                "replay and candidate replay; candidate-output treatment "
                "under baseline-committed agent state; baseline-output "
                "ablation under candidate-committed agent state. These are "
                "hybrid output effects, not coherent integrated-policy or "
                "feature effects."
            ),
            "engine_ref": ev.ENGINE_REF,
            "engine_sha256": engine_hashes,
            "loader_sha256": ev.sha256(args.loader),
            "evaluator_sha256": ev.sha256(ev.__file__),
            "splice_evaluator_sha256": ev.sha256(__file__),
            "inputs": {
                "baseline": baseline.receipt,
                "candidate": candidate.receipt,
                "opponent": opponent.receipt,
            },
            "source_snapshots_unchanged": (
                source_snapshots_unchanged
            ),
            "seeds": seeds,
            "seats": seats,
            "agent_rng_seed": args.rng_seed,
            "limits": {
                "action_rpc_seconds": args.action_timeout,
                "startup_seconds": args.startup_timeout,
                "game_seconds": args.game_timeout,
                "episode_steps_override": args.episode_steps,
            },
            "summary": summarize(cells),
            "cells": cells,
        }
        if not source_snapshots_unchanged:
            raise RuntimeError(
                "Authenticated source snapshot changed during evaluation"
            )
        _write_json(output, report)
        print(
            "SUMMARY "
            + json.dumps(report["summary"], sort_keys=True),
            flush=True,
        )
        exit_code = int(
            any(
                cell["classification"] in {"failed", "unstable"}
                for cell in cells
            )
        )
        _thaw_tree(store)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
