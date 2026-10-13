"""Pinned-evaluator opponent binding and action/state-separated gameplay."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any

import evidence
import panel_analysis

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise evidence.EvidenceError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def opponent_specs(items: list[str], runtime: Path) -> dict[str, dict[str, Any]]:
    """Resolve only archive-transitive or pinned official opponents."""
    runtime = runtime.resolve()
    output: dict[str, dict[str, Any]] = {}
    for item in items:
        label, separator, value = item.partition("=")
        if not separator or not label or label in output:
            raise evidence.EvidenceError(
                "Each opponent must be a unique LABEL=SPEC"
            )
        if value == "official_starter":
            output[label] = {
                "spec": value,
                "binding": "official-engine",
                "engine_ref": ENGINE_REF,
            }
            continue
        if not value.startswith("runtime:"):
            raise evidence.EvidenceError(
                "Opponent must be official_starter or runtime:PATH.py::callable"
            )
        relative = value.removeprefix("runtime:")
        path_text, call_separator, callable_name = relative.partition("::")
        if (
            not path_text
            or not call_separator
            or not callable_name.isidentifier()
        ):
            raise evidence.EvidenceError(
                "Runtime opponent requires PATH.py::callable"
            )
        unresolved = (runtime / path_text).resolve(strict=False)
        try:
            unresolved.relative_to(runtime)
        except ValueError as exc:
            raise evidence.EvidenceError(
                "Runtime opponent escapes immutable archive"
            ) from exc
        try:
            candidate = unresolved.resolve(strict=True)
        except OSError as exc:
            raise evidence.EvidenceError(
                f"Runtime opponent is missing: {path_text}"
            ) from exc
        try:
            candidate.relative_to(runtime)
        except ValueError as exc:
            raise evidence.EvidenceError(
                "Runtime opponent resolves outside immutable archive"
            ) from exc
        snap = evidence.snapshot(candidate, max_bytes=4 << 20)
        output[label] = {
            "spec": str(candidate) + "::" + callable_name,
            "path": candidate.relative_to(runtime).as_posix(),
            "callable": callable_name,
            "sha256": snap.sha256,
            "bytes": len(snap.data),
            "binding": "archive-transitive",
        }
    if not output:
        raise evidence.EvidenceError("At least one --opponent is required")
    return output


def _post_state_payload(state: list[Any]) -> list[dict[str, Any]]:
    """Exclude action bytes so state divergence is independent evidence."""
    return [
        {
            "status": seat.status,
            "reward": seat.reward,
            "observation": seat.observation,
        }
        for seat in state
    ]


def play_attributed(
    evaluator,
    engine,
    specs: list[str],
    cache: Path,
    loader: Path,
    seed: int,
    candidate_seat: int,
    rng_seed: int = 20260909,
    action_timeout: float = 1.0,
    startup_timeout: float = 10.0,
    game_timeout: float = 120.0,
    episode_steps: int | None = None,
) -> dict[str, Any]:
    """Mirror the pinned evaluator while separating action and state traces."""
    if candidate_seat not in (0, 1):
        raise evidence.EvidenceError("candidate_seat must be 0 or 1")
    if len(specs) != 2:
        raise evidence.EvidenceError("Exactly two agent specs are required")
    cfg = evaluator.Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    if episode_steps is not None:
        cfg.episodeSteps = episode_steps
    if (
        isinstance(cfg.episodeSteps, bool)
        or not isinstance(cfg.episodeSteps, int)
        or cfg.episodeSteps < 2
    ):
        raise evidence.EvidenceError(
            "episodeSteps must be an integer of at least 2"
        )
    cfg.seed = int(seed)
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [
        evaluator.Struct(
            observation=evaluator.Struct(),
            action={},
            status="ACTIVE",
            reward=0,
        )
        for _ in range(2)
    ]
    started = time.perf_counter()
    initial_cpu = time.process_time()
    actors: list[Any] = []
    action_trace = hashlib.sha256()
    state_trace = hashlib.sha256()
    step_digests: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "seed": int(seed),
        "candidate_seat": candidate_seat,
        "status": "failed",
        "scores": None,
        "failure": None,
        "steps": 0,
        "episode_steps": int(cfg.episodeSteps),
        "daily_bank": [],
        "step_digests": step_digests,
    }
    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise evidence.EvidenceError(
                "Environment seed must not be exposed to agents"
            )
        for seat, agent_spec in enumerate(specs):
            actor = evaluator.Actor(
                agent_spec,
                cache,
                loader,
                rng_seed + int(seat != candidate_seat),
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
            actions: list[dict[str, Any]] = []
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
                    state[seat].observation,
                    cfg,
                    min(action_timeout, remaining),
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
            for seat in range(2):
                state[seat].action = actions[seat]

            action_bytes = evaluator.encoded(actions[candidate_seat])
            action_sha = hashlib.sha256(action_bytes).hexdigest()
            action_trace.update(
                evaluator.encoded(
                    {"step": step, "candidate_action_sha256": action_sha}
                )
            )
            engine.interpreter(state, env)
            post_state_bytes = evaluator.encoded(_post_state_payload(state))
            post_state_sha = hashlib.sha256(post_state_bytes).hexdigest()
            state_trace.update(
                evaluator.encoded(
                    {"step": step, "post_state_sha256": post_state_sha}
                )
            )
            bank = [
                float(state[0].observation.farms[index]["money"])
                for index in range(2)
            ]
            step_digests.append(
                {
                    "step": step,
                    "candidate_action_sha256": action_sha,
                    "post_state_sha256": post_state_sha,
                    "bank": bank,
                }
            )
            result["steps"] += 1
            done = all(seat.status == "DONE" for seat in state)
            if (step + 1) % cfg.turnsPerDay == 0 or done:
                result["daily_bank"].append({"step": step, "bank": bank})
            if done:
                scores = [seat.reward for seat in state]
                if not all(panel_analysis.finite_number(value) for value in scores):
                    raise evidence.EvidenceError(
                        "Nonfinite or missing terminal score"
                    )
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
        farms = state[0].observation.get(
            "farms", [{"money": 0}, {"money": 0}]
        )
        result["bank_snapshot"] = [
            float(farms[index]["money"]) for index in range(2)
        ]
        result["candidate_action_trace_sha256"] = action_trace.hexdigest()
        result["post_state_trace_sha256"] = state_trace.hexdigest()
    return result
