# SPDX-License-Identifier: Apache-2.0
"""One official, process-isolated route arm game with compact causal receipts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / "cloud-execution-lab"
LOADER_PATH = LAB / "reference/evaluator/loader.py"
ENGINE_DIR = LAB / "reference/engine"
DIAGNOSTIC_KEY = "__titan_route_regret__"
DIAGNOSTIC_SCHEMA = "titan-route-regret-event/v1"


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"non-JSON value in evidence projection: {type(value).__name__}")


def digest(value) -> str:
    payload = json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def action_digest(action) -> str:
    return digest(action)


def world_digest(state, env) -> str:
    """Hash public engine state while excluding submitted action objects."""
    return digest(
        {
            "agents": [
                {
                    "observation": item.observation,
                    "status": item.status,
                    "reward": item.reward,
                }
                for item in state
            ],
            "done": env.done,
            "info": env.info,
        }
    )


def _clean_action(response, *, tested_seat: bool, step: int, player: int):
    action = response.get("action")
    if not isinstance(action, dict):
        raise TypeError("worker action is not an object")
    clean = deepcopy(action)
    marker = clean.pop(DIAGNOSTIC_KEY, None)
    if marker is not None and not tested_seat:
        raise ValueError("route-regret marker emitted by opponent")
    if marker is not None:
        if not isinstance(marker, dict):
            raise ValueError("route-regret marker is not an object")
        if marker.get("schema") != DIAGNOSTIC_SCHEMA:
            raise ValueError("route-regret diagnostic schema drift")
        if type(marker.get("step")) is not int or marker["step"] != step:
            raise ValueError("route-regret diagnostic step mismatch")
        if type(marker.get("player")) is not int or marker["player"] != player:
            raise ValueError("route-regret diagnostic player mismatch")
        checkpoint = marker.get("checkpoint")
        if type(checkpoint) is not int or checkpoint != step:
            raise ValueError("route-regret checkpoint mismatch")
        if marker.get("mode") not in {"auto", "force", "stay"}:
            raise ValueError("route-regret diagnostic mode drift")
        if not isinstance(marker.get("target"), str):
            raise ValueError("route-regret diagnostic target missing")
    return clean, marker


def _bank(state) -> list[float]:
    farms = state[0].observation.get("farms", [])
    return [float(farms[index]["money"]) for index in range(2)]


def play(
    evaluator,
    engine,
    specs,
    seed: int,
    tested_seat: int,
    *,
    arm: str,
    opponent: str,
    rng_seed: int,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
):
    if type(tested_seat) is not int or tested_seat not in (0, 1):
        raise ValueError("tested_seat must be literal integer 0 or 1")
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
    tested_actions = hashlib.sha256()
    opponent_actions = hashlib.sha256()
    worlds = hashlib.sha256()
    result = {
        "invocation_id": uuid.uuid4().hex,
        "seed": seed,
        "tested_seat": tested_seat,
        "arm": arm,
        "opponent": opponent,
        "status": "failed",
        "scores": None,
        "failure": None,
        "steps": 0,
        "episode_steps": int(cfg.episodeSteps),
        "checkpoint_receipts": [],
        "daily_bank": [],
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
                rng_seed + (seat != tested_seat),
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
                    tested_seat=(seat == tested_seat),
                    step=step,
                    player=seat,
                )
                if diagnostic is not None:
                    if marker is not None:
                        raise ValueError("multiple route-regret diagnostics in one step")
                    marker = diagnostic
                actions.append(clean)

            tested_hash = action_digest(actions[tested_seat])
            opponent_hash = action_digest(actions[1 - tested_seat])
            for seat in range(2):
                state[seat].action = actions[seat]
            engine.interpreter(state, env)
            post_world = world_digest(state, env)
            tested_actions.update(bytes.fromhex(tested_hash))
            opponent_actions.update(bytes.fromhex(opponent_hash))
            worlds.update(bytes.fromhex(pre_world) + bytes.fromhex(post_world))
            result["steps"] += 1
            if marker is not None:
                receipt = dict(marker)
                receipt.update(
                    pre_world_sha256=pre_world,
                    tested_action_sha256=tested_hash,
                    opponent_action_sha256=opponent_hash,
                    post_world_sha256=post_world,
                    diagnostic_sha256=digest(marker),
                )
                result["checkpoint_receipts"].append(receipt)
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
        result["tested_action_stream_sha256"] = tested_actions.hexdigest()
        result["opponent_action_stream_sha256"] = opponent_actions.hexdigest()
        result["world_stream_sha256"] = worlds.hexdigest()
        try:
            result["bank_snapshot"] = _bank(state)
        except Exception:
            result["bank_snapshot"] = None
    return result
