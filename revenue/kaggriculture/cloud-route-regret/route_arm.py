# SPDX-License-Identifier: Apache-2.0
"""Instrumented exact-current-TITAN route checkpoint counterfactual arms."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from typing import Any, Callable

from source_contract import checkpoints, verify_source_contract

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / "cloud-execution-lab"
DIAGNOSTIC_KEY = "__titan_route_regret__"
SCHEMA = "titan-route-regret-event/v1"
CHECKPOINTS = {int(row[0]): tuple(row) for row in checkpoints()}
_BASE_MODULE = None
_SOURCE_RECEIPT = None


def _load_base():
    global _BASE_MODULE, _SOURCE_RECEIPT
    if _BASE_MODULE is not None:
        return _BASE_MODULE
    _SOURCE_RECEIPT = verify_source_contract()
    path = LAB / "main.py"
    name = "_sol_lever_route_regret_canonical_titan"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical TITAN base at {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(LAB))
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.path[:] = old_path
    _BASE_MODULE = module
    return module


def _step(observation) -> int:
    raw = observation.get("step")
    if raw is not None:
        return int(raw)
    return int(observation.get("day", 0)) * 24 + int(observation.get("hour", 0))


def _producer(instance):
    controller = None if instance is None else getattr(instance, "controller", None)
    if controller is None or not callable(getattr(controller, "act", None)):
        return None, None
    function = getattr(controller.act, "__func__", controller.act)
    namespace = getattr(function, "__globals__", None)
    if not isinstance(namespace, dict):
        return None, None
    return controller, namespace


def _diagnostics(instance) -> dict[str, Any]:
    raw = {} if instance is None else dict(getattr(instance, "diagnostics", {}) or {})
    keys = (
        "status",
        "fallback_stage",
        "inner_fallback_stage",
        "entrypoint_guard",
        "parent_calls",
        "elapsed_seconds",
        "act_cpu_seconds",
    )
    return {key: raw.get(key) for key in keys if raw.get(key) is not None}


def _validate_namespace(namespace: dict[str, Any]) -> None:
    observed = tuple(tuple(row) for row in namespace.get("DECISIONS", ()))
    expected = tuple(CHECKPOINTS[turn] for turn in sorted(CHECKPOINTS))
    if observed != expected:
        raise ValueError(f"producer decision table drift: expected {expected!r}, got {observed!r}")
    if not callable(namespace.get("_feature")):
        raise ValueError("producer feature reader is unavailable")


def _instrumented(
    observation,
    configuration,
    *,
    mode: str,
    checkpoint: int | None,
):
    if mode not in {"auto", "force", "stay"}:
        raise ValueError(f"unknown route arm mode: {mode}")
    if mode == "auto" and checkpoint is not None:
        raise ValueError("auto arm must not name a checkpoint")
    if mode != "auto" and checkpoint not in CHECKPOINTS:
        raise ValueError(f"unknown route checkpoint: {checkpoint}")

    base = _load_base()
    step = _step(observation)
    selected = CHECKPOINTS.get(step)
    should_emit = selected is not None and (mode == "auto" or step == checkpoint)
    instance = getattr(base, "_INSTANCE", None)
    controller, namespace = _producer(instance)
    patch = None
    event = None

    if should_emit:
        turn, feature_name, threshold, target = selected
        feature_value = None
        route_before = None
        switch_legal = False
        override_applied = mode == "auto"
        unavailable_reason = None
        natural_target = None
        if controller is None or namespace is None:
            unavailable_reason = "controller_unavailable_before_call"
        else:
            _validate_namespace(namespace)
            feature_value = namespace["_feature"](observation, feature_name)
            natural_target = bool(feature_value >= threshold)
            route_before = getattr(controller, "cur", None)
            switch_legal = bool(
                route_before != target and controller._switch_ok(target, turn)
            )
            if mode == "force":
                if switch_legal:
                    controller.cur = target
                    override_applied = True
                else:
                    unavailable_reason = "force_not_prefix_legal"
            elif mode == "stay":
                if switch_legal:
                    original = namespace["DECISIONS"]
                    namespace["DECISIONS"] = tuple(
                        row for row in original if int(row[0]) != turn
                    )
                    patch = (namespace, original)
                    override_applied = True
                else:
                    unavailable_reason = "stay_not_prefix_legal"
        event = {
            "schema": SCHEMA,
            "mode": mode,
            "checkpoint": turn,
            "step": step,
            "player": int(observation.get("player", -1)),
            "feature": feature_name,
            "feature_value": feature_value,
            "shipped_threshold": threshold,
            "target": target,
            "natural_target": natural_target,
            "route_before": route_before,
            "switch_legal": switch_legal,
            "override_applied": override_applied,
            "unavailable_reason": unavailable_reason,
        }

    try:
        output = base.agent(observation, configuration)
    finally:
        if patch is not None:
            namespace, original = patch
            namespace["DECISIONS"] = original

    if event is None:
        return output
    after = getattr(base, "_INSTANCE", None)
    after_controller, _ = _producer(after)
    event["route_after"] = (
        None if after_controller is None else getattr(after_controller, "cur", None)
    )
    event["runtime"] = _diagnostics(after)
    event["source_authored_base"] = (
        None if _SOURCE_RECEIPT is None else _SOURCE_RECEIPT["authored_base"]
    )
    marked = deepcopy(output)
    marked[DIAGNOSTIC_KEY] = event
    return marked


def agent(observation, configuration=None):
    """Submission-compatible untouched current TITAN entrypoint."""
    return _load_base().agent(observation, configuration)


def auto(observation, configuration=None):
    return _instrumented(observation, configuration, mode="auto", checkpoint=None)


def force_226(observation, configuration=None):
    return _instrumented(observation, configuration, mode="force", checkpoint=226)


def stay_226(observation, configuration=None):
    return _instrumented(observation, configuration, mode="stay", checkpoint=226)


def force_360(observation, configuration=None):
    return _instrumented(observation, configuration, mode="force", checkpoint=360)


def stay_360(observation, configuration=None):
    return _instrumented(observation, configuration, mode="stay", checkpoint=360)


def force_433(observation, configuration=None):
    return _instrumented(observation, configuration, mode="force", checkpoint=433)


def stay_433(observation, configuration=None):
    return _instrumented(observation, configuration, mode="stay", checkpoint=433)


ENTRYPOINTS: dict[str, Callable[..., Any]] = {
    "auto": auto,
    "force_226": force_226,
    "stay_226": stay_226,
    "force_360": force_360,
    "stay_360": stay_360,
    "force_433": force_433,
    "stay_433": stay_433,
}
