# SPDX-License-Identifier: Apache-2.0
"""One exact process-isolated game with action-excluding state receipts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from pathlib import Path
import time
import uuid

from realized_execution import action_digest, digest, world_digest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
LOADER_PATH = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"
DIAGNOSTIC_KEY = "__titan_market_prefix_realized__"


def _clean_action(response, *, tested_seat: bool, step: int, player: int):
    action = response.get("action")
    if not isinstance(action, dict):
        raise TypeError("worker action is not an object")
    clean = deepcopy(action)
    marker = clean.pop(DIAGNOSTIC_KEY, None)
    if marker is not None and not tested_seat:
        raise ValueError("diagnostic marker emitted by opponent")
    if marker is not None:
        if not isinstance(marker, dict):
            raise ValueError("candidate diagnostic is not an object")
        if marker.get("schema") != "titan-market-prefix-rescue/v2":
            raise ValueError("candidate diagnostic schema drift")
        if marker.get("syntactic_changed") is not True:
            raise ValueError("candidate diagnostic does not claim a syntactic edit")
        if type(marker.get("step")) is not int or marker["step"] != step:
            raise ValueError("candidate diagnostic step mismatch")
        if type(marker.get("player")) is not int or marker["player"] != player:
            raise ValueError("candidate diagnostic player mismatch")
        if marker.get("market_sha256_before") == marker.get("market_sha256_after"):
            raise ValueError("candidate diagnostic reports no market-byte change")
    return clean, marker


def _bank(state) -> list[float]:
    farms = state[0].observation.get("farms", [])
    return [float(farms[index]["money"]) for index in range(2)]


def play(
    evaluator,
    engine,
    specs,
    seed: int,
    candidate_seat: int,
    *,
    rng_seed: int,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
):
    if type(candidate_seat) is not int or candidate_seat not in (0, 1):
        raise ValueError("candidate_seat must be literal integer 0 or 1")
    cfg = evaluator.Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    if type(cfg.episodeSteps) is not int or cfg.episodeSteps < 2:
        raise ValueError("invalid official episodeSteps")
    cfg.seed = seed
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [
        evaluator.Struct(
            observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0
        )
        for _ in range(2)
    ]
    started = time.perf_counter()
    initial_cpu = time.process_time()
    actors = []
    action_stream = hashlib.sha256()
    world_stream = hashlib.sha256()
    diagnostics = []
    result = {
        "invocation_id": uuid.uuid4().hex,
        "seed": seed,
        "candidate_seat": candidate_seat,
        "status": "failed",
        "scores": None,
        "failure": None,
        "steps": 0,
        "episode_steps": int(cfg.episodeSteps),
        "step_receipts": [],
        "daily_bank": [],
        "syntactic_event_count": 0,
        "diagnostics": diagnostics,
    }
    try:
        engine.interpreter(state, env)
        if cfg.get("seed") is not None:
            raise ValueError("environment seed leaked to agents")
        for seat, spec in enumerate(specs):
            actor = evaluator.Actor(
                spec,
                ENGINE_DIR,
                LOADER_PATH,
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
            for seat in range(2):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
            pre_world = world_digest(state, env)
            actions = []
            marker = None
            for seat, actor in enumerate(actors):
                remaining = game_timeout - (time.perf_counter() - started)
                if remaining <= 0:
                    result["failure"] = {
                        "kind": "game_timeout",
                        "seat": None,
                        "step": step,
                    }
                    return result
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
                clean, diagnostic = _clean_action(
                    response,
                    tested_seat=(seat == candidate_seat),
                    step=step,
                    player=seat,
                )
                if diagnostic is not None:
                    if marker is not None:
                        raise ValueError("multiple candidate diagnostics in one step")
                    marker = diagnostic
                actions.append(clean)

            tested_hash = action_digest(actions[candidate_seat])
            opponent_hash = action_digest(actions[1 - candidate_seat])
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            post_world = world_digest(state, env)
            diagnostic_hash = digest(marker) if marker is not None else None
            receipt = {
                "step": step,
                "pre_world_sha256": pre_world,
                "tested_action_sha256": tested_hash,
                "opponent_action_sha256": opponent_hash,
                "post_world_sha256": post_world,
                "syntactic_event": marker is not None,
                "diagnostic_sha256": diagnostic_hash,
            }
            result["step_receipts"].append(receipt)
            result["steps"] += 1
            action_stream.update(
                bytes.fromhex(tested_hash) + bytes.fromhex(opponent_hash)
            )
            world_stream.update(bytes.fromhex(pre_world) + bytes.fromhex(post_world))
            if marker is not None:
                result["syntactic_event_count"] += 1
                if len(diagnostics) < 128:
                    diagnostics.append(marker)
            done = all(item.status == "DONE" for item in state)
            bank = _bank(state)
            if (step + 1) % int(cfg.turnsPerDay) == 0 or done:
                result["daily_bank"].append({"step": step, "bank": bank})
            if done:
                scores = [item.reward for item in state]
                if not all(
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(value)
                    for value in scores
                ):
                    raise ValueError("nonfinite or missing terminal score")
                if result["steps"] != cfg.episodeSteps - 1:
                    raise ValueError(
                        f"official lifecycle drift: {result['steps']} actions for "
                        f"{cfg.episodeSteps} configured steps"
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
            "kind": "runner_error",
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
        result["tested_action_stream_sha256"] = action_stream.hexdigest()
        result["world_stream_sha256"] = world_stream.hexdigest()
        result["diagnostics_truncated"] = max(
            0, result["syntactic_event_count"] - len(diagnostics)
        )
        try:
            result["bank_snapshot"] = _bank(state)
        except Exception:
            result["bank_snapshot"] = None
    return result


