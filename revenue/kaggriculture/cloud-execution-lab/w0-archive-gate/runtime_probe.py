#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute the packaged TITAN spatial capability contract in an isolated process.

This probe deliberately imports the candidate archive rather than a copied AST.  Its
JSON output is consumed by verify_archive.py; it is not a stand-alone promotion
verdict because archive identity and member custody are checked by the parent gate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import MISSING, fields
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import traceback
from typing import Any

CAPABILITIES = (
    "spatial_pathing",
    "spatial_tempo",
    "idle_fertilizer",
    "crop_release",
    "weed_continuation",
)


def _strict_json(path: Path) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key {key!r} in {path.name}")
            out[key] = value
        return out

    def constant(value):
        raise ValueError(f"non-finite JSON constant {value!r} in {path.name}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


def _feature_kwargs(Features, enabled: dict[str, bool]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields(Features):
        if field.default is not MISSING:
            value = deepcopy(field.default)
        elif field.default_factory is not MISSING:  # type: ignore[comparison-overlap]
            value = field.default_factory()  # type: ignore[misc]
        else:
            raise AssertionError(f"Features.{field.name} has no default")
        if type(value) is bool:
            value = False
        result[field.name] = value
    result.update(enabled)
    result["consumer"] = "frozen"
    if "budget_seconds" in result:
        result["budget_seconds"] = 1.0
    if "reserve_seconds" in result:
        result["reserve_seconds"] = 0.01
    if "history_hypotheses" in result:
        result["history_hypotheses"] = None
    return result


def _wrapper_identity(callable_obj: Any) -> str:
    return f"{getattr(callable_obj, '__module__', '')}.{getattr(callable_obj, '__qualname__', '')}"


def _matrix(titan_runtime) -> list[dict[str, Any]]:
    Features = titan_runtime.Features
    TitanAgent = titan_runtime.TitanAgent
    field_map = {field.name: field for field in fields(Features)}
    weed = field_map.get("weed_continuation")
    if weed is None:
        raise AssertionError("Features.weed_continuation is missing")
    if weed.default is not False or type(weed.default) is not bool:
        raise AssertionError("Features.weed_continuation must default to literal False")

    rows: list[dict[str, Any]] = []
    for mask in range(1 << len(CAPABILITIES)):
        enabled = {name: bool(mask & (1 << index))
                   for index, name in enumerate(CAPABILITIES)}
        feature = Features(**_feature_kwargs(Features, enabled))
        agent = TitanAgent(feature)
        agent._initialize()
        expected = any(enabled.values())
        actual = agent.spatial is not None
        if actual != expected:
            raise AssertionError(
                f"capability mask {mask:02d} expected spatial={expected}, got {actual}")
        wrapper = _wrapper_identity(agent.controller.act)
        if not expected and "spatial" in wrapper.lower():
            raise AssertionError(f"all-off controller is still spatial-wrapped: {wrapper}")
        attrs = None
        if actual:
            attrs = {}
            spatial_attributes = {
                "spatial_pathing": "pathing",
                "spatial_tempo": "tempo",
                "idle_fertilizer": "idle_fertilizer",
                "crop_release": "crop_release",
                "weed_continuation": "weed_continuation",
            }
            for name, expected_value in enabled.items():
                attribute = spatial_attributes[name]
                value = getattr(agent.spatial, attribute, MISSING)
                if value is MISSING:
                    raise AssertionError(f"SpatialTempo.{attribute} is missing under mask {mask:02d}")
                if value is not expected_value:
                    raise AssertionError(
                        f"SpatialTempo.{attribute}={value!r}, expected {expected_value!r} under mask {mask:02d}")
                attrs[name] = value
        rows.append({"mask": mask, "enabled": enabled, "spatial": actual,
                     "wrapper": wrapper, "attributes": attrs})
    return rows


def _minimal_observation() -> tuple[dict[str, Any], dict[str, Any], Any]:
    farm = {"farmer": [0, 0], "hands": [],
            "tiles": [[None for _ in range(10)] for _ in range(10)]}
    observation = {
        "step": 0,
        "day": 0,
        "player": 0,
        "farms": [deepcopy(farm), deepcopy(farm)],
        "private": {"inventories": [{}], "seeds": {}, "shed": {}},
        "market": {"inventory": {}, "params": {}},
    }
    selected = {"farmer": ["PASS"], "hands": [], "market": []}
    route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
    controller = SimpleNamespace(cur=0, R={0: route})
    return observation, selected, controller


def _reachability(spatial_tempo) -> list[dict[str, Any]]:
    SpatialTempo = spatial_tempo.SpatialTempo
    rows: list[dict[str, Any]] = []
    for weed in (False, True):
        for pathing in (False, True):
            for tempo in (False, True):
                spatial = SpatialTempo(
                    object(), pathing=pathing, tempo=tempo,
                    idle_fertilizer=False, crop_release=False,
                    weed_continuation=weed,
                )
                calls = {"weed": 0}

                def marker(*_args, **_kwargs):
                    calls["weed"] += 1
                    # W1 exits here; W0 must never reach this function.
                    return True

                spatial._continue_weed = marker
                spatial._deliver_idle_fertilizer = lambda *_args, **_kwargs: None
                spatial._collect_idle_fertilizer = lambda *_args, **_kwargs: None
                observation, selected, controller = _minimal_observation()
                returned = spatial.transform(observation, deepcopy(selected), controller)
                expected_calls = 1 if weed else 0
                if calls["weed"] != expected_calls:
                    raise AssertionError(
                        "_continue_weed reachability mismatch for "
                        f"P{int(pathing)}T{int(tempo)}W{int(weed)}: "
                        f"{calls['weed']} != {expected_calls}")
                if returned != selected:
                    raise AssertionError("reachability probe changed the selected action")
                rows.append({"pathing": pathing, "tempo": tempo, "weed": weed,
                             "weed_calls": calls["weed"]})
    return rows


def _has_weed_state(spatial: Any) -> list[str]:
    found: list[str] = []
    for label, plans in (("plans", getattr(spatial, "plans", {})),
                         ("committed.plans", (getattr(spatial, "_committed", None) or {}).get("plans", {}))):
        for worker, plan in plans.items():
            if isinstance(plan, dict) and plan.get("kind") == "weed_continuation":
                found.append(f"{label}[{worker!r}]")
    for label, events in (("events", getattr(spatial, "events", [])),
                          ("committed.events", (getattr(spatial, "_committed", None) or {}).get("events", []))):
        for index, event in enumerate(events):
            if isinstance(event, dict) and event.get("kind") == "weed_continuation":
                found.append(f"{label}[{index}]")
    return found


def _stale_w0_reinitialization(titan_runtime) -> dict[str, Any]:
    Features = titan_runtime.Features
    TitanAgent = titan_runtime.TitanAgent
    enabled = {name: False for name in CAPABILITIES}
    enabled["spatial_pathing"] = True
    agent = TitanAgent(Features(**_feature_kwargs(Features, enabled)))
    agent._initialize()
    spatial = agent.spatial
    if spatial is None:
        raise AssertionError("P1/W0 did not construct SpatialTempo")

    weed_plan = {
        "kind": "weed_continuation", "route": 0, "step": 1, "end": 4,
        "origin": (0, 0), "goal": (0, 0), "replacement": [["PLANT", "WHEAT"]],
        "obligation": ["PLANT", "WHEAT"],
    }
    idle_plan = {
        "kind": "idle_fertilizer", "route": 0, "step": 1, "end": 4,
        "origin": (0, 0), "goal": (0, 0), "replacement": [["PASS"]],
    }
    weed_event = {"kind": "weed_continuation", "worker": 0}
    idle_event = {"kind": "idle_fertilizer", "worker": 1}
    spatial.plans = {0: deepcopy(weed_plan), 1: deepcopy(idle_plan)}
    spatial.active = {0: 4, 1: 4}
    spatial.events = [deepcopy(weed_event), deepcopy(idle_event)]
    spatial._committed = {
        "patches": {(0, 1): {0: ["PLANT", "WHEAT"], 1: ["PASS"]}},
        "plans": {0: deepcopy(weed_plan), 1: deepcopy(idle_plan)},
        "events": [deepcopy(weed_event), deepcopy(idle_event)],
        "reserved": set(), "active": {0: 4, 1: 4}, "day": 0, "step": 0,
    }

    # Deadline recovery rebuilds the producer and reinstalls the retained spatial
    # object. W0 must scrub an impossible old weed plan before that wrapper can
    # restore patches or advertise seed demand; unrelated service state survives.
    agent.ready = False
    agent._initialize()
    leaked = _has_weed_state(spatial)
    if leaked:
        raise AssertionError(f"W0 retained stale weed state after reinstall: {leaked}")
    if 0 in getattr(spatial, "active", {}):
        raise AssertionError("W0 retained the stale weed worker in active state")
    demand = spatial.future_seed_requests(0)
    if demand.get("WHEAT", 0):
        raise AssertionError(f"W0 retained stale weed seed demand: {demand}")
    retained_idle = any(
        isinstance(plan, dict) and plan.get("kind") == "idle_fertilizer"
        for plan in getattr(spatial, "plans", {}).values())
    if not retained_idle:
        raise AssertionError("W0 cleanup erased unrelated idle-fertilizer state")
    return {"leaked": leaked, "seed_demand": demand,
            "retained_idle_fertilizer": retained_idle}


def _configured_default(root: Path, titan_runtime) -> dict[str, Any]:
    config = _strict_json(root / "TITAN-CONFIG.json")
    if not isinstance(config, dict):
        raise AssertionError("TITAN-CONFIG.json must contain an object")
    import main
    instance = main._new_instance(root, config)
    if instance.features.weed_continuation is not False:
        raise AssertionError("packaged default did not construct W0")
    instance._initialize()
    expected = any(bool(config.get(name, False)) for name in CAPABILITIES)
    actual = instance.spatial is not None
    if actual != expected:
        raise AssertionError(f"packaged default expected spatial={expected}, got {actual}")
    if actual and instance.spatial.weed_continuation is not False:
        raise AssertionError("packaged default constructed SpatialTempo with W1")
    return {"weed_continuation": config["weed_continuation"],
            "expected_spatial": expected, "actual_spatial": actual}


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"candidate root is not a directory: {root}")
    os.chdir(root)
    sys.path.insert(0, str(root))
    import titan_runtime
    import spatial_tempo
    return {
        "schema": 1,
        "ok": True,
        "capabilities": list(CAPABILITIES),
        "matrix": _matrix(titan_runtime),
        "reachability": _reachability(spatial_tempo),
        "stale_w0_reinitialization": _stale_w0_reinitialization(titan_runtime),
        "configured_default": _configured_default(root, titan_runtime),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: runtime_probe.py CANDIDATE_ROOT RESULT_JSON", file=sys.stderr)
        return 64
    root = Path(argv[1])
    result_path = Path(argv[2])
    try:
        result = run(root)
        code = 0
    except BaseException as exc:  # preserve a deterministic failure receipt
        result = {
            "schema": 1,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        code = 1
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
